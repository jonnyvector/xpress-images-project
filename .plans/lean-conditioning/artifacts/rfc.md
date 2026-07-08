---
number: 01
title: "Lean Conditioning: Replica-Learn Conditioning Stack Redesign"
type: refactor
status: Review
author: Jonathan Hicks / Claude
date: 2026-07-08
---

# RFC-01: Lean Conditioning: Replica-Learn Conditioning Stack Redesign

## Abstract

The replica-learn pipeline conditions every generation attempt with an
additive stack of prose (style prompt, spec notes, profile facts, defect
correctives) assembled invisibly across four files — and the 2026-07-08
El Dorado investigation proved that this prose can actively sabotage the
door it describes, while the operator's bare "lean prompt" fixed the door
in four re-rolls. This RFC restructures the re-learn ladder around a
**fixed prose/lean split**: prose-carrying conditioning gets exactly two
attempts, and every later attempt re-rolls the lean prompt carrying
only the spec-file width note — the completed spike fixed the tail
composition: no profile anchor, no other prose (D-012). The RFC also adds prompt
observability (every assembled prompt logged), a prior-cueing audit of
the 38 style prompts, and decouples lean learning from the `door_style`
field so variant generation is unaffected. Scope ends with the
operator-gated rollout of the resistant door class (~20 mitered skinny
shakers plus remaining rejects).

## Introduction

### Problem

A learn attempt's prompt is assembled from layers across four files
(`backend/styles/catalog.py`, `backend/generator.py`,
`backend/onboarding.py`, `backend/wood_specs.py` via the driver), is never
logged, and only ever GROWS: every mechanism in the ladder adds prose,
none removes it. Evidence from 2026-07-07/08:

- El Dorado failed 16 attempts across three conditioning strategies. The
  `raised_panel` style prompt contains the phrase "bevel profile"; the
  facts note and defect correctives added more relief vocabulary; the
  operator-proven doctrine (white-RTF, 2026-07-03) is that words
  describing 3D relief CUE the prior they try to forbid.
- The operator's manual recipe — the lean prompt "Generate an exact
  replica of this door." with empty notes — produced a judge-clean
  replica on roll 4 of 5, matching his standing "good one within 4–5
  tries" experience.
- Temp-0 learning was verified NOT deterministic across calls (same
  inputs, same model, different draws), invalidating the assumption the
  current ladder's variety knobs (rising temperature) were built on.
- The lean prompt is currently reachable only by mutating a project's
  `door_style` to `rtf_minimal`, which corrupts the variant-phase hint.

### Why a fixed split (and not an adaptive trigger)

An earlier draft de-escalated when the identity judge flagged the same
region on two consecutive attempts. Review killed it: the judge runs at
52–62% catch / 10–19% false-fail (97-verdict calibration), and its errors
are systematic per door — a good door's false-fail repeats (forcing lean
while prose was working) while a resistant door's flags wander across
regions (never triggering). A deterministic split spends the same
attempt budget without building a state machine on a noisy instrument.
<!-- D-008 -->

### Scope

IN: the re-learn ladder in `backend/onboarding.py`
(`learn_conditioning`, `onboard_replica`), a `lean` parameter on the
learn path (`backend/generator.py::learn_door_style`,
`backend/worker.py::start_learning/_run_learn`), per-attempt prompt
logging, a read-only audit of all 38 `learn_prompt`s with surgical
failure-driven edits (starting with `raised_panel`), reverting
El Dorado's `door_style` to `raised_panel`, the lean-tail spike, and the
operator-gated rollout.

OUT: the QA side (profile-spec extraction, identity judge, rubric judge,
geometry checks) is unchanged — the drawing keeps feeding extraction and
the judge unconditionally, and the profile facts remain the judge's
acceptance criteria on every attempt. Variant generation
(`generate_variation`, `reference_image_path`) is untouched. Stage-A
(human replica approval) is untouched. The frozen calibration artifacts
(`output/.qa/labels.json`, the 97-verdict replica window) are untouched.

## Terminology

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD,
SHOULD NOT, RECOMMENDED, MAY, and OPTIONAL in this document are to be
interpreted as described in RFC 2119.

- **Conditioning stack**: the set of text layers assembled into one
  learn call's prompt: style prompt, corner block, material block (RTF),
  dimensions block, maple override, the STRUCTURAL DETAILS notes (which
  aggregate three distinct sources: spec notes, facts note, defect
  corrective), and the anchor framing line. <!-- D-011 -->
- **Lean prompt**: the bare instruction "Generate an exact replica of
  this door." (the `rtf_minimal` style's `learn_prompt` text) in place of
  the style prompt; the generator's standard corner block, dimensions
  block, material block (when RTF), and image parts are all retained.
  <!-- D-011 -->
- **Lean tail**: all attempts from index 2 onward — conditioned with the
  lean prompt and `style_notes` set to the spec-file width note ONLY
  (`wood_specs.learn_notes` output; empty for doors without
  `frame_width_in`); no facts note, no defect note, no profile anchor.
  <!-- D-008, D-012 -->
- **Prose rungs**: attempts 0–1, which keep today's conditioning
  (including today's anchor-on-retry behavior). <!-- D-009 -->
- **Profile anchor**: the catalog cross-section drawing
  (`profile/3d-profile.jpg`) attached as an extra image to a learn call
  (built 2026-07-08, spec `docs/superpowers/specs/2026-07-08-profile-anchor-design.md`).
- **Re-roll**: repeating a learn call with unchanged conditioning; draws
  differ because temp-0 generation is non-deterministic (verified
  2026-07-08).

## Current State

`onboard_replica` (backend/onboarding.py) loops learn → identity-judge →
re-learn up to `attempt_cap`. Conditioning per attempt comes from
`learn_conditioning` (maple rung at attempt 1, corrective note targeting
the lowest-scoring dimension, rising temperature from attempt 4+ wood /
2+ RTF), plus `defect_note` (identity-judge defects quoted back), plus a
facts note (`profile_facts_note`) folded into every attempt's
`style_notes`, plus the driver's spec notes (`wood_specs.learn_notes`).
The profile anchor joins at every retry (attempt index ≥ 1). The final
assembled prompt is never recorded. `door_style` selects both the learn
prompt and the variant hint. El Dorado (project `141216d1`) currently
carries `door_style=rtf_minimal` as a workaround.

Pain points: additive-only prose (no lean rung), prior-cueing vocabulary
inside style prompts ("bevel profile" — present in `raised_panel` and
verbatim-duplicated in `raised_panel_radius` and the two drawer raised-
panel styles), zero prompt observability, a temperature schedule
justified by a disproven determinism assumption, and `door_style`
coupling two unrelated jobs.

## Proposed Changes

### 1. Lean flag on the learn path <!-- D-003 -->

`learn_door_style` MUST accept `lean: bool = False`. When `lean=True` it
MUST use the lean prompt text in place of `STYLES[door_style]["learn_prompt"]`
and MUST leave every other assembly step unchanged (corner block,
dimensions block, material block, image parts, optional
`profile_image_path`). `start_learning` and `_run_learn` MUST pass the
flag through. The ladder MUST NOT mutate `door_style` to reach the lean
prompt. El Dorado's `door_style` MUST be reverted to `raised_panel`;
its active replica and signature are untouched by the revert. (Watch
item: that replica was learned lean, so its variant runs use
`raised_panel`'s `variation_hint` — review the first variant batch with
this in mind. <!-- D-011 -->)

### 2. Fixed prose/lean split in the ladder <!-- D-008 -->

**Prose rungs (attempts 0–1):** unchanged from today, including the
anchor-on-retry behavior shipped 2026-07-08 (anchor attaches at attempt
index ≥ 1) and the defect-corrective mechanism. Attempt 0 = style prompt
+ spec notes + facts note; attempt 1 = maple rung (wood,
`allow_maple=True`) or native + corrective (RTF). <!-- D-009 -->

**Lean tail (attempts ≥ 2):** every attempt MUST run with `lean=True`
and `style_notes` set to exactly the spec-file width note
(`wood_specs.learn_notes`; empty string for doors without
`frame_width_in`) — facts note and defect notes dropped, and the
profile anchor MUST NOT be attached <!-- D-012 -->. Re-rolls provide
variety. The facts remain the identity judge's acceptance criteria on
every attempt; they leave the learn PROMPT only. With `attempt_cap ≤ 1`
the lean tail is unreachable; the driver default (`attempt_cap=5`, six
attempts) yields four lean-tail draws — matching the operator's
observed "good one within 4–5 tries" for lean draws.

**How the tail was fixed** <!-- D-009, D-012 -->: the composition was
resolved by the completed spike (§5) before implementation. A-001
passed — anchored lean draws were strictly worse (fattened Journey's
frames 3/3, leaked the drawing's 3/4 viewpoint into one render, induced
miters and a raised panel on Dylan): the anchor stays on prose rungs
only. A-002 failed — bare lean fattened Dylan's 2.25 in frame 3/3 while
lean + width note held it: hence the width-note-only rule above.

**Temperature** <!-- D-006 -->: all rungs run at temperature 0. The
rising-temperature schedule in `learn_conditioning` is REMOVED. The
maple rung stays.

### 3. Prompt observability <!-- D-005, D-010 -->

`learn_door_style` MUST return the fully assembled prompt on its result
(new `GenerationResult` field). An attempt label MUST thread from
`onboard_replica`'s loop through `learn_fn` → `start_learning` →
`_run_learn` (UI-initiated learns use the label `ui`). The worker MUST
write the prompt to
`output/.onboard/prompts/<project_id>/<label>-<utc-timestamp>.txt`
(timestamped so re-runs never overwrite prior forensics) and MUST emit
one log line naming the conditioning layers (style key or `lean`, notes
present or empty, anchor present). Failure to write the sidecar MUST NOT
fail the learn (log and continue). The pre-existing same-project
temp-file race in `_run_learn` is out of scope (noted, not worsened).

### 4. Style-prompt audit <!-- D-004 -->

A read-only audit sweeps all 38 `learn_prompt`s in
`backend/styles/catalog.py` for prior-cueing profile-character
vocabulary (bevel, sloped, raised, pillowy, cove, …) and produces an
operator-reviewed findings table (`docs/qa-style-prompt-audit.md`). The
table MUST list the three sibling styles that duplicate `raised_panel`'s
"bevel profile" phrasing. Only prompts implicated in actual failures are
edited now: `raised_panel`'s "bevel profile" phrase MUST be replaced
with neutral wording ("raise profile"). Other flagged prompts MUST NOT
be edited until their door class shows failures. <!-- D-011 -->

### 5. Spike: lean-tail composition — COMPLETE (2026-07-08) <!-- D-009, D-012 -->

Ran before the ladder phase, ~$2.01: Journey and Dylan, 3 bare-lean +
3 lean+anchor draws each, plus a Dylan follow-up arm (lean + width note
only). Operator's eye was the verdict (correctly — the judge
false-matched `stiles_rails` on all six of Dylan's fattened draws).
Outcome: A-001 pass, A-002 fail; tail = lean prompt + spec width note
only, no anchor (D-012). Full table:
`.plans/lean-conditioning/artifacts/spike-report.md`.

### 6. Rollout (operator-gated) <!-- D-007 -->

Final milestone: the ~20 mitered skinny shakers and remaining rejected
doors re-onboarded through the new ladder in batches under an
operator-approved spend ceiling. Stage-A approval remains the identity
gate for every replica.

## Migration Strategy

All changes are backward compatible; no data migration. The ladder
change is internal to `onboard_replica` (its signature keeps the same
defaults). UI-initiated learns see no behavior change beyond the sidecar
prompt log. One stored-state correction ships with the code: El Dorado's
`door_style` revert (a `store.update`, replica untouched). Rollback =
revert the branch; sidecar logs and audit doc are additive artifacts.

## Risk Assessment

- **Doors that prose was saving get only two prose attempts.** The
  skinny-shaker width note lifted Newbury/Sullivan 2→4 — and the spike
  confirmed the tail must keep it (bare lean fattened Dylan 3/3), so
  the tail carries the width note by rule (D-012). Residual risk is
  profile-character detail (Dylan's inside-edge miss); blast radius is
  re-roll spend, never data loss — Stage-A still gates every replica.
- **Lean-tail convergence generalized from small n.** The 4–5-draw
  experience is one door plus operator anecdote; some doors may exhaust
  four tail draws. Cap-hit behavior is unchanged (best-of by fewest
  defects, `needs_human`), and the spike adds three more doors of
  evidence before rollout.
- **Editing `raised_panel`'s prompt** perturbs a distribution that
  produced approved replicas. Mitigated: single surgical phrase edit,
  and the identity judge + Stage-A gate every future replica anyway.
- **Best-of under judge misses**: fewest-judged-defects can prefer a
  draw whose real defect the judge missed; more tail re-rolls buy more
  lottery tickets. Accepted: Stage-A reviews the winner regardless
  (pre-existing behavior, cost is operator attention).

## Security Considerations

No new trust boundaries. Sidecar prompt files contain only prompt text
already sent to the Gemini API (no keys, no PII) and live under the
gitignored `output/` tree. Catalog files are read-only inputs. The
GEMINI key continues to be read via `read_api_key()` from `.env`.
Nothing in this RFC touches approval authority: Stage-A human review
remains the sole replica gate, and nothing under `output/.projects/` is
ever deleted (signatures are irreplaceable).

## Testing Strategy

- Unit (pure, no API): lean prompt selection in `learn_door_style`
  (lean=True swaps only the style layer; corner/dimension/material
  blocks and image parts survive); the fixed split (attempts 0–1 carry
  today's conditioning INCLUDING anchor-on-retry — locked by the
  existing anchor gating test; attempts ≥ 2 are lean with the spec
  width note only and no anchor — D-012);
  temperature 0 on every rung; assembled prompt returned on
  `GenerationResult`; sidecar write path, label threading, and
  layer-summary line; audit script flags the known `raised_panel`
  phrase and its three sibling duplicates.
- Regression: existing `onboard_replica` tests (clean-first-attempt,
  defect-guided retry on attempt 1, cap finalization,
  extraction-failure fallback, anchor-at-retry-1) keep passing —
  attempts 0–1 are byte-compatible with today. Tests asserting prose
  conditioning on attempts ≥ 2 (temperature schedule) are updated to
  the new ladder, not deleted silently.
- Live acceptance (operator-gated): El Dorado re-verified through the
  new ladder (expected: reaches the lean tail at attempt 2 and lands a
  judge-clean draw within the tail, subject to draw luck); then the
  rollout batches.

## Implementation Plan

Phases (DECOMPOSE will detail milestones/tasks):

1. **Spike: lean-tail composition** — COMPLETE (§5; OQ-1/OQ-2 resolved,
   tail mix fixed as D-012).
2. **Lean flag + door_style revert** — generator/worker plumbing,
   El Dorado `store.update`.
3. **Ladder redesign** — fixed split, lean tail per spike outcome,
   temperature-schedule removal in `onboarding.py`.
4. **Prompt observability** — `GenerationResult` prompt field, label
   threading, sidecar writes + layer-summary log line.
5. **Style-prompt audit** — audit table doc + `raised_panel` surgical
   edit.
6. **Rollout** — resistant class re-onboarding in operator-approved
   batches.

## Open Questions

None. Both were resolved by the spike (2026-07-08, operator verdicts):

1. **OQ-1 (A-001) — RESOLVED: bare lean wins; the anchor stays out of
   the tail entirely** (it fattened frames, leaked the drawing's 3/4
   viewpoint, and induced construction the doors don't have). D-012.
2. **OQ-2 (A-002) — RESOLVED: the tail keeps ONLY the spec-file width
   note.** Bare lean fattened Dylan's 2.25 in frame 3/3; with the note,
   held (2/3 judge-clean, draw 1 visually exact). D-012.

## References

**Normative**
- `.plans/lean-conditioning/plan.db` decisions D-001…D-012 — the
  interview + review + spike ledger this RFC encodes (D-008 supersedes
  D-001; D-009 amends D-002; D-012 fixes the tail).
- `docs/superpowers/specs/2026-07-08-profile-anchor-design.md` — the
  anchor build whose lean-tail slotting the spike decided (excluded).

**Informative**
- `docs/superpowers/specs/2026-07-07-replica-identity-judge-design.md` —
  identity judge + calibration honesty (52–62% catch), why Stage-A stays
  the gate and why the adaptive trigger was rejected.
- Memory: `technique_minimal_learn_prompt.md` — lean-beats-prose
  doctrine, El Dorado proof, temp-0 non-determinism evidence.
- Memory: `technique_white_on_white_reference_anchor.md` — original
  "geometry prose backfires" finding (2026-07-03).
