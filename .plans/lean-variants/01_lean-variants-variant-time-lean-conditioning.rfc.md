---
number: 01
title: "Lean Variants: Variant-Time Lean Conditioning"
type: refactor
status: Review
author: Jonathan Hicks / Claude
date: 2026-07-11
---

# RFC-01: Lean Variants: Variant-Time Lean Conditioning

## Abstract

Variant generation conditions every draw with the door style's
`variation_hint` — prose describing the door — and the 2026-07-11 waves
proved this prose can contradict the door it describes: Mitchell's
`shaker_bevel` hint ordered a "barely visible" bevel and all 38 variants
obediently erased the door's defining BOLD bevel. A three-draw probe
(2 of 3 operator-approved; styled baseline 0/38) showed the signature
alone can carry the geometry when the hint goes bare. This RFC adds a
`lean` variant mode <!-- D-001, D-005 -->: a new truly-bare hint
("Preserve the exact door structure from before. Change only the wood
material."), applied ONLY to projects with `variant_hint_mode="lean"`
— five doors with proven styled-hint failures and five parked skinny
shakers <!-- D-006 -->. Styled hints stay the default and are untouched
for every other door. Gates are untouched <!-- D-003 -->. Rollout is
staged — a $1.21 probe, then one gate door, then waves; doors with
operator-approved variants are topped up, never reset <!-- D-007 -->.

## Introduction

### Problem

`generate_variation` derives its conditioning from
`STYLES[door_style]["variation_hint"]` (backend/generator.py:633-639).
For doors whose profile deviates from their style's stereotype, the hint
actively fights the thought signature:

- Mitchell (`shaker_bevel`, bold bevel): hint says "tiniest eased bevel —
  barely visible… NO visible inner border" → 38/38 variants judged
  profile-miss, operator-confirmed. The replica was fine — the lean
  learn ladder bypasses the style prompt; variants had no such bypass.
- Same failure signature on Fallbrook (0/38), Baldwin and Dylan (1/38
  each) — all `mitered_flat_panel` skinny frames whose styled hint
  claims "1 to 1.25 inch" frames their real doors contradict.
- Rhode Island (`recessed_panel`) landed 13/37 after operator review —
  a weaker, possibly per-draw pattern; it is a PROBE target, not a
  presumed hint-contradiction case <!-- D-007 -->.
- Probe evidence <!-- A-001 -->: three Mitchell draws with a bare hint
  off the same signature — maple and cherry operator-approved
  ("golden"), one per-draw miss (white oak). Styled baseline: 0/38.

### Scope

IN: a `lean` flag on `generate_variation` with a NEW bare-hint constant;
a persisted `variant_hint_mode` on `ProjectState`; worker plumbing
(batch, retry, and QA-lane regen paths resolve the mode per project);
mode-setting for the ten doors with ops hardening; width-note backfill
for Melbourne/Windsor/Fallbrook; a `--topup` capability in
`scripts/variant_wave.py`; the staged operator-gated rollout.

OUT: the judge, geometry drift check, auto-accept policy, and Stage-A
are all UNCHANGED — the drift check was vindicated 2026-07-11 (54
drift-flagged min-4 variants, all operator-rejected) and MUST NOT be
weakened <!-- D-003 -->. Styled doors' conditioning is unchanged on
every path including regens <!-- D-006 -->. The learn path is
untouched. The white-RTF near-white reference-image recipe (a
`reference_image` inside `generate_variation`, worker.py:519-524) and
`generate_variation_from_reference` are untouched — no RTF project gets
lean mode <!-- D-005 -->.

## Terminology

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD,
SHOULD NOT, RECOMMENDED, MAY, and OPTIONAL in this document are to be
interpreted as described in RFC 2119.

- **Styled hint**: `STYLES[door_style]["variation_hint"]` — today's
  behavior and the default.
- **Bare hint** <!-- D-005 -->: a new module constant
  `LEAN_VARIATION_HINT` in `backend/generator.py`: "Preserve the exact
  door structure from before. Change only the wood material." It makes
  NO geometry claims (deliberately unlike `STYLES["minimal"]`'s hint,
  whose "all stiles and rails must remain the same width" is false for
  non-uniform doors) and is NOT a catalog style.
- **`variant_hint_mode`**: persisted per-project: `"styled"` (default) |
  `"lean"`. Loaded with `data.get("variant_hint_mode", "styled")`
  <!-- D-008 -->; the worker treats any value other than `"lean"` as
  styled.
- **Top-up**: generating only the palette woods that lack an
  operator-approved variant, with `reset_existing=False` — approved
  variants are never destroyed <!-- D-007 -->.

## Current State

`_run_generation` / `_run_retry` (backend/worker.py) call
`_generate_for_selection` → `generate_variation`, which internally
selects the styled hint and appends `style_notes` as STRUCTURAL
DETAILS. `_generate_for_selection` also pre-computes a styled
`variation_hint` used ONLY by the `generate_variation_from_reference`
branch — that value and branch stay untouched. The QA lane's
`RegenContext` closure regenerates flagged variants with the same
conditioning as the original draw. No per-project hint mode exists.
There is no per-draw record of what conditioning a variant carried.

## Proposed Changes

### 1. Lean flag + bare hint on `generate_variation` <!-- D-001, D-005 -->

`generate_variation` MUST accept `lean: bool = False`. When `lean=True`
it MUST use `LEAN_VARIATION_HINT` in place of the styled hint and MUST
leave every other assembly step unchanged — `style_notes` still appends
as STRUCTURAL DETAILS (spec width notes ride along), swatch/reference
parts, temperature 0.3, signature-first part order. The
`generate_variation_from_reference` branch in `_generate_for_selection`
MUST ignore the flag. (Structurally parallel to
`learn_door_style(lean=…)`, though the learn flag is per-attempt
ladder-driven and swaps a different text — the parallel is the
doctrine, not the plumbing.)

### 2. Persisted mode <!-- D-001, D-008 -->

`ProjectState.variant_hint_mode: str = "styled"`, manifest key
`"variant_hint_mode"`, load explicitly as
`data.get("variant_hint_mode", "styled")` (NOT the `profile_spec`
idiom, which would yield `None` on old manifests).

### 3. Worker plumbing <!-- D-006 -->

`start_generation`/`_run_generation` and `_run_retry` resolve
`lean = (project.variant_hint_mode == "lean")` per project and thread
it through `_generate_for_selection` → `generate_variation`. The
`RegenContext` closure captures the SAME resolved value — lean doors
regen lean, styled doors regen styled. There is NO cross-mode
de-escalation.

**Observability** <!-- D-008 -->: every generation batch/retry/regen
emits one log line naming the resolved mode
(`[variants <pid>] hint=lean|styled notes=<present|empty>`), so a
clobbered or missing mode is visible in the run log, mirroring the
learn path's `layers:` line.

### 4. Setting the ten doors <!-- D-002, D-006, D-008 -->

`variant_hint_mode="lean"` for: Mitchell, Fallbrook, Baldwin, Dylan,
Rhode Island, Journey, Hamilton, Melbourne, Windsor, Finley — via a
one-off script that MUST run with the dev server DOWN (single-writer
rule) and MUST print `project_id + name + resolved mode` for all ten
for operator eyeball ack (lowercase/suffixed project names have
silently missed before). The same prep step backfills spec width notes
(`wood_specs.learn_notes`) into `style_notes` for Melbourne, Windsor,
and Fallbrook (currently empty), and verifies Fallbrook's
classification against its catalog source before any draw
<!-- D-007 -->.

### 5. Staged rollout (operator-gated) <!-- D-004, D-007 -->

- **Stage 1 — probe (~$1.21)**: 3 draws × 3 doors spanning the classes:
  Baldwin (skinny + width note), Windsor (skinny, backfilled note),
  Rhode Island (recessed). Maple/cherry/white-oak. Operator eye is the
  verdict.
- **Stage 2 — gate door**: one full lean palette on the strongest
  probe performer; wave rhythm review.
- **Stage 3 — waves**: remaining doors. Rhode Island (and any door with
  operator-approved variants) is topped up via `variant_wave.py
  --topup`; never `reset_existing` over approved work.
- Honest budget: ~$70-85 including QA-lane auto-regens (cap 2/variant,
  $10/run ceiling per door) <!-- D-007 -->. Single wave process at a
  time to FULL drain; approvals only via the live API when the dev
  server is up.

## Migration Strategy

Backward compatible; no data migration; old manifests load styled.
Rollback = revert branch; the mode field is inert without the plumbing.
`reset_variant_results` semantics are unchanged — this RFC only narrows
WHEN the rollout uses it (never over approved variants).

## Risk Assessment

- **Lean per-draw variance** (white-oak miss in the probe): expected;
  unchanged judge + drift check + Stage-A catch it; lean regens re-draw
  at temp 0.3. Blast radius = re-roll spend under existing caps.
- **frame_narrow lean pass rate unknown** (8 of 10 doors): that is what
  Stages 1–2 measure for ~$6 before the ~$60 tail is committed.
- **Bare hint on doors whose styled hint carried real corrections**:
  moot for styled doors (unchanged everywhere); for the ten lean doors
  the styled hints are the documented problem, and width facts ride in
  `style_notes`.
- **Best-of across mixed regimes**: `_finalize_best` compares judge
  score-sums only; a lean regen could outrank a styled original on a
  width-blind judge. Pre-existing behavior; within lean-mode doors all
  attempts share conditioning, so mixing only occurs on doors that
  changed mode between runs. Accepted, noted.

## Security Considerations

No new trust boundaries, no new inputs, no key-handling changes.
Stage-A human review remains the sole approval authority. Replicas and
signatures are never rewritten. Variant result records ARE replaced by
design when (and only when) a re-run without approved variants uses
`reset_existing` — approved variants are protected by the top-up rule
<!-- D-007 -->.

## Testing Strategy

- Unit (stubbed `_call_with_retry`/fake client, existing patterns):
  `generate_variation(lean=True)` uses `LEAN_VARIATION_HINT` and keeps
  style_notes/swatch branches; `lean=False` byte-identical to today;
  `variant_hint_mode` roundtrips and old manifests load `"styled"`;
  batch + retry + regen paths resolve the mode per project (lean door →
  lean regen; styled door → styled regen, locked by test); the
  reference-image branch ignores the flag; the observability line names
  the resolved mode; `variant_wave.py --topup` selects only unapproved
  woods and never passes `reset_existing=True` with approved variants
  present.
- Live acceptance (operator-gated): Stages 1–3 per §5.

## Implementation Plan

1. **M1**: `variant_hint_mode` field + `generate_variation(lean=…)` +
   `LEAN_VARIATION_HINT`.
2. **M2**: worker plumbing (batch/retry/regen, mode log line) +
   `variant_wave.py --topup`.
3. **M3**: prep (modes set + notes backfilled + Fallbrook verified,
   server down, eyeball ack) and the staged rollout (operator-gated).

## Open Questions

1. **OQ-1: lean pass rate on `frame_narrow` doors** — unmeasured (the
   probe was `shaker_bevel`). Resolved by Stage 1/2 before the wave
   spend; decider: operator, on his own verdicts.
2. **OQ-2: Fallbrook's true profile class** — RFC review flagged a
   discrepancy (described as multi-step molding; manifest says
   `mitered_flat_panel`, empty notes). Resolved in the M3 prep step by
   checking the catalog source photo; decider: operator if ambiguous.

## References

**Normative**
- `.plans/lean-variants/plan.db` D-001…D-008 (D-005 amends D-001;
  D-006 supersedes D-002's global de-escalation; D-007 amends D-004),
  A-001.
- Probe artifact: claude.ai/code/artifact/9834a1e5-3d26-4674-81f5-4ec7f635705f

**Informative**
- `.plans/lean-conditioning/` — the learn-path twin of this doctrine.
- Memory `technique_replica_identity_judge.md` — drift-check
  vindication (gates must not be weakened).
- Memory `ops_single_writer.md` — why mode-setting runs server-down and
  approvals go through the API.
