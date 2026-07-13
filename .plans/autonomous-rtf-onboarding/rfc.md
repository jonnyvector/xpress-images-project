---
number: RFC-AUTO-ONBOARD
title: Autonomous RTF Door Onboarding
type: feature
status: Draft
author: jonny + Claude
date: 2026-07-03
---

# Autonomous RTF Door Onboarding

## Abstract

A batch driver that onboards new RTF cabinet doors from the local Decore
catalog with minimal operator involvement. For each door it creates a project,
uploads the source photo, learns a replica, and judges it. On a weak replica it
re-learns (regenerates) up to a bounded number of attempts, keeping the best.
When it has a judge-clean replica it **stops** and queues the replica for
operator approval — honoring the existing Stage-A human gate. The same
verdict→action loop is defined for the later variant phase (auto-accept judge
passes, loop on "regenerate", queue "needs_human"). First run: the next 5
uncovered thermofoil cabinet doors (FR556, KB732, DT223, DP8, AP768).

## Introduction

### Problem

Onboarding a new door today is manual: create the project, upload the sample,
click learn, eyeball the replica, retry by hand, approve, then generate. Across
many doors this is slow and it wastes operator attention on the cases the
pipeline can already judge. We want the machine to do the mechanical loop —
generate, judge, retry the ones the judge says to retry — and surface only what
genuinely needs a human.

### Scope

**In scope**
- A reusable driver that onboards a list of RTF doors from catalog source images.
- An autonomous **replica loop**: learn → judge → re-learn (≤ cap) → queue or escalate.
- A verdict→action policy shared by replica and (later) variant phases.
- Bounded cost: per-image attempt cap and a per-run spend ceiling.
- Running it on the next 5 uncovered thermofoil cabinet doors.

**Out of scope**
- Bypassing the Stage-A replica approval gate (explicitly retained — D-001).
- Bulk variant generation in this run (happens after operator approves replicas).
- Any new operator UI beyond the existing Review tab (the driver feeds it).
- Scraping decore.com (source images already exist locally).

### Motivation

The graduated-trust pipeline already judges images and auto-regenerates variant
"regenerate" verdicts. What's missing is (a) an onboarding loop that applies the
same discipline to **replicas** (which currently never auto-regenerate — they
always gate to the human), and (b) a batch driver so one command onboards N
doors. This closes the loop between "we have source images" and "replicas are
queued for approval."

## Terminology

The key words MUST, SHOULD, MAY are used per RFC 2119.

- **Onboard**: create project + upload source + produce a queued, judge-clean replica.
- **Replica loop**: the bounded learn→judge→re-learn cycle for one door.
- **Replica quality gate**: the numeric judge/geometry threshold that decides
  whether a freshly learned replica is queued for approval or regenerated. This
  is distinct from the **operator gate** (Stage-A human approval), which is never
  bypassed.
- **Escalate**: stop auto-retrying and mark the item for operator attention
  (needs_human) — it appears in the Review tab.
- **Attempt cap**: max regenerations per image before escalating (D-002: 5).
- **Run ceiling**: max total spend for a batch run; the driver stops submitting
  when reached.

## Design

### Call points (existing code the driver composes)

1. `ProjectStore.create(name, product_type, material_type)` → `ProjectState` (`state.py:266`).
2. `ProjectStore.update(pid, door_style=, corner_style=, style_notes=, selected_swatches=)` (`state.py:281`).
3. `ProjectStore.save_upload(pid, filename, bytes)` — writes `upload.bin`, the QA sample (`state.py:591`).
4. `worker.start_learning(store, project, api_key, upload_bytes, learn_in_maple=, aspect_ratio=)` (`worker.py:316`) — generates the replica, archives any prior, assigns a fresh `base_image_id`, clears results/verdicts, and **auto-enqueues the replica judge** (`kind="replica"`). Re-learn = call again.
5. Poll `project.qa_verdicts[project.base_image_id]` until `qa_status=="done"`, then read `scores` + `geometry`.
6. Queued replica auto-appears in `GET /qa/review-queue` (`replica.pending==true`) — no extra call.

### Replica quality gate (D-005)

Policy always gates a replica as `needs_human`, so the verdict string is not a
quality signal. The driver decides **queue-vs-relearn** on the numeric verdict:

- **queue-ready** ⟺ `min(scores.values()) >= min_score` (policy config = 3) AND `geometry != "drift"`.
- Otherwise **re-learn**, up to the attempt cap (D-002 = 5).
- Across attempts keep the **best by `sum(scores)`** (ties → latest), mirroring `_finalize_best`.
- At cap without a queue-ready replica: keep the best attempt, queue it but flag
  needs_human so the operator sees the closest try.

For geometry-excluded styles (raised/slab/arched) `geometry` is `unmeasurable`/`None`,
which satisfies `!= "drift"` — the gate is scores-only, as intended.

### Re-learn variety ladder (D-006)

`learn_door_style` runs at **temperature 0.0** (deterministic): identical inputs
reproduce the same replica, so retries MUST change conditioning. Per-attempt ladder:

| Attempt | Conditioning change |
|---------|---------------------|
| 0 | native learn |
| 1 | `learn_in_maple=True` (different prompt → different signature) |
| 2 | native + corrective style-note targeting the lowest-scoring dimension |
| 3 | maple + corrective note |
| 4 | + small temperature bump (new optional `temperature` param on `learn_door_style`, driver-only; app path stays 0.0) |

### First-run door set (D-004) and per-door style

| Code | door_style | Geometry class | Notes (from catalog hero image) |
|------|-----------|----------------|----------------------------------|
| FR556 | raised_panel | excluded | Raised field, cove/ogee frame, square |
| KB732 | solid_plank | excluded | Beveled slab, single surface, wide chamfer |
| DT223 | recessed_panel | frame_standard | Flat recessed panel, thin inside-edge bevel |
| DP8 | raised_panel | excluded | Raised panel, **arched (cathedral) top** |
| AP768 | recessed_panel | excluded (arched) | Routed recessed panel, **arched top**, ogee inner |

All `corner_style="sharp"`, `material_type="rtf"`, `product_type="Cabinet Door"`,
`aspect_ratio="9:16"`. Per D-005/[[generate-all-swatches-always]] the full RTF
swatch palette is selected, but variants only generate after operator replica
approval (D-001).

### Verdict → Action policy

For every judged image the driver maps the pipeline verdict to an action:

| Verdict | Replica phase | Variant phase (later) |
|---------|---------------|------------------------|
| pass / clean | Queue for operator approval (Stage A) | **Auto-accept** (D-003) |
| regenerate (weak) | Re-learn, up to attempt cap; keep best | Auto-regen, up to attempt cap |
| needs_human / error | Escalate (leave for operator) | Escalate (leave for operator) |

Replicas are NEVER auto-accepted — a judge-clean replica is *queued*, not shipped
(D-001). Only the operator's approval unlocks that door's variants.

### Replica quality gate

Because policy gates every replica to the human, the driver needs its own
numeric signal to decide queue-vs-regenerate. _(Exact fields pending Explore
findings; candidate signal: all judge dimension scores ≥ threshold, especially
`profile_character_match`, plus advisory replica-vs-sample geometry within
tolerance.)_

## Error Handling

- **Generation/API error**: one automatic retry (mirrors QA lane). A second error
  escalates the door as needs_human; the driver moves to the next door.
- **No source image / bad upload**: skip the door, record the reason, continue.
- **Attempt cap reached without a clean replica**: keep the best-scoring attempt,
  queue it flagged as needs_human so the operator sees the closest try.
- **Run ceiling reached**: stop submitting new work, finish in-flight, report what
  completed and what remains.
- **Crash mid-run**: each door's state persists after every step (project + run
  manifest), so a re-run resumes from doors not yet onboarded.

## Security Considerations

- **Cost blast radius**: the attempt cap (per image) and run ceiling (per batch)
  bound spend; the driver MUST increment a spend counter before each API call and
  stop at the ceiling. Replica-only scope caps the first run near ~$3-5.
- **No destructive actions**: the driver only creates projects and generates
  images. It never deletes projects, signatures, or existing results (consistent
  with the standing never-delete rule).
- **Human gate preserved**: no path in the driver approves a replica or ships a
  variant that the operator hasn't seen when the judge is unsure — Stage A holds.
- **API key**: read from `.env`, never persisted server-side.

## Open Questions

_Both resolved during design:_

1. **Replica quality threshold** — RESOLVED (D-005): `min(scores) >= 3` and
   `geometry != "drift"`; keep best by `sum(scores)`.
2. **Driver location** — RESOLVED (D-007): tested backend module +
   `scripts/onboard_rtf.py` CLI; no new endpoints/UI.

Remaining empirical unknown (A-001): whether ≤5 attempts reliably reaches a
queue-ready replica for each door. Not a design blocker — the escalation path
handles misses; the run itself is the test.
