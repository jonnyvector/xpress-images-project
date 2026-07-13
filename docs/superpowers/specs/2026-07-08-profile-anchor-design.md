# Profile Anchor (Cross-Section Reference for Replica Learning)

**Date:** 2026-07-08
**Status:** APPROVED — ready for implementation planning.
**Relates to:** `2026-07-07-replica-identity-judge-design.md` (identity pipeline shipped
as re-roll assist; its live test produced the finding this design answers) and the
white-RTF reference-anchor fix on the variant path (2026-07-03).

## Problem

Some doors have profile geometry that text cannot force the image model to render.
El Dorado failed 10 learn attempts across two fact vocabularies: the identity judge
correctly named the defect every time (sample has a sharp vertical step up to the
raised field; replica renders a wide sloped bevel), but the generator's beveled-raise
prior never yielded. The ~20 mitered skinny shakers fail the same way on frame width
(Journey and Dylan resisted 6 attempts of emphatic narrow-frame notes).

Root cause: a door's profile — raise shape, step vs slope, true frame thickness — is
3D geometry that a front-facing hero photo encodes only as a few pixels of shading.
When the pixels underdetermine the geometry, the model resolves the ambiguity with its
prior, and re-rolls sample the same bad mode. Corrective prose does not help and can
actively hurt: words describing 3D relief CUE the wrong prior (verified on white-RTF,
2026-07-03). The judge shares the same limitation — its 62% catch ceiling
(calibration, 2026-07-07) is partly the same front-on ambiguity.

## Discovery

The Decore catalog ships `profile/3d-profile.jpg` for **159 of 166 wood door folders**:
a small (130–185px) clean line-render **cross-section of that door's actual edge,
frame, and panel profile viewed edge-on**. From that viewpoint the ambiguity does not
exist — a sharp step looks like a sharp step; a skinny frame is measurably skinny.
El Dorado's shows its raise profile; Journey's shows the thin flat frame.

## Decisions (made with operator, 2026-07-08)

1. **Anchor source: the door's own catalog cross-section** (`profile/3d-profile.jpg`).
   Alternatives rejected: a borrowed same-profile approved replica (library-dependent,
   color-leak risk, and the hard classes have no approved member) and a magnified hero
   crop (same viewpoint, same ambiguity).
2. **Generation trigger: escalation after the first disqualification.** The first
   learn attempt is byte-for-byte today's path — 62 replicas already succeed there.
   The moment the identity judge disqualifies an attempt, every retry carries the
   cross-section.
   El Dorado and the skinny shakers pick it up automatically; no roster to maintain.
3. **QA scope: both sides.** The cross-section also feeds profile-spec extraction
   (facts state true profile character from unambiguous evidence) and the identity
   judge (third image — check the replica's profile against the drawing, not photo
   shading). Zero extra calls; one small extra image part per call.
4. **Geometry stays in the image.** One framing line per prompt; no new geometry
   prose anywhere.

## Design

### 1. Generator — anchor slot (`backend/generator.py`)

`learn_door_style` gains `profile_image_path: Path | None = None`. When set:

- A second image part is appended at HIGH media resolution (the drawings are small;
  the model needs the pixels).
- One framing line joins the prompt: "The additional small drawing is a CROSS-SECTION
  of this door's edge, frame, and panel profile viewed edge-on. Reproduce this exact
  profile geometry. Do not copy the drawing's line-art rendering style."
- Nothing else in the learn prompt changes.

`start_learning` (`backend/worker.py`) passes the parameter through.

### 2. Onboarding loop — escalation trigger (`backend/onboarding.py`)

`onboard_replica` gains `profile_bytes: bytes | None = None`.

- First attempt (loop index 0): never attached (today's behavior exactly).
- Every retry (loop index ≥ 1, reached only after a disqualification): attached
  when available.
- Defect-note ladder, `learn_conditioning`, best-of ranking (`_attempt_rank`),
  spend guard, and Stage-A (human approval) are untouched.

### 3. QA side — same witness, always on when available

- **Extraction** (`backend/qa/profile_spec.py`): `extract_profile_spec` gains
  `profile_bytes: bytes | None = None`; when present the drawing is a second image
  part and the prompt gains a conditional block: the drawing is a cross-section of
  the same door — use it to state profile character (raise shape, step vs slope,
  frame thickness) precisely. Without it, the prompt is byte-identical to today.
- **Identity judge** (`backend/qa/judge.py`): `judge_replica_identity` gains
  `profile_bytes: bytes | None = None`; when present the drawing is a third image
  part and `IDENTITY_PROMPT` gains a conditional block: the drawing shows the SAMPLE
  door's true profile — use it to resolve profile-character questions; the REPLICA
  must match the drawing's geometry. Without it, byte-identical to today.
- Operator-corrected facts still override: `--force` without `--respec` preserves
  `profile_spec` and skips re-extraction, as today.

### 4. Driver (`scripts/onboard_wood.py`)

- `resolve_profile(name)` alongside `resolve()`: locates
  `<catalog>/<profile-folder>/<Door>/profile/3d-profile.jpg`, returns `Path | None`.
- Reads the bytes and passes them to `onboard_replica`; logs a one-line notice for
  the 7 doors without a drawing (they behave exactly as today).
- The resolved path string is stored on the project manifest as a new
  `profile_image_path: str | None` field on `ProjectState` (`backend/state.py`,
  saved/loaded like `profile_spec`) for traceability and eval reuse.

### 5. Re-calibration (`scripts/qa_replica_eval.py`)

- The eval resolves each door's cross-section and passes it to extraction and the
  judge, then re-runs against the frozen verdict window (≥ 2026-07-06T10:00,
  97 operator verdicts).
- Output: before/after catch and false-fail rates. The judge remains a re-roll
  ASSIST regardless of the result; any gate revisit is a separate future decision.
- The frozen 179-label variant calibration (`output/.qa/labels.json`) is not touched.

## Boundaries

- The variant path (`generate_variation` + `reference_image_path`, the white-RTF
  fix) is unchanged.
- No profile drawing → every code path behaves exactly as today; conditional prompt
  blocks appear only when the image is attached.
- The UI onboarding flow has no catalog access; it passes no profile bytes and is
  unaffected.
- Nothing under `output/.projects/` is deleted; signature bytes are never rewritten.

## Risks

- **Style leak:** the anchor is line art; the replica must not come out looking like
  a drawing. Mitigated by the framing line; validated on the first live door before
  any batch run.
- **Extraction-fact drift:** better extraction facts change attempt-1 conditioning
  for newly-onboarded doors. This is the facts pipeline working as designed
  (prevention was its biggest measured value); existing stored specs are reused, not
  re-extracted.

## Testing

- Unit: conditional prompt blocks present/absent for extraction, judge, and learn;
  learn parts assembly (anchor part present at attempt ≥ 1 only); `onboard_replica`
  attempt-gating with injected fakes; `resolve_profile` hit/miss.
- Live acceptance (in order, cheap first):
  1. **El Dorado** — the known 10-attempt failure whose drawing shows the sharp
     step. Success = identity-clean replica the operator approves, no style leak.
  2. **Journey, Dylan** — the two skinny shakers that resisted all text.
  3. The remaining mitered skinny-shaker class (~20 doors), then audit the
     ~26 remaining rejects for more members.
- Re-calibration table from `qa_replica_eval.py` reported for operator review.
