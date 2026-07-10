# Replica Identity Judge (Profile-Spec Pipeline)

**Date:** 2026-07-07
**Status:** SHIPPED as a re-roll ASSIST — the replace-the-gate calibration bar was
NOT met (see Calibration outcome below); operator approved shipping as assist.
**Relates to:** `2026-07-06-wood-onboarding-foundation-design.md` (Pillar 1 shipped;
this replaces the replica-phase quality gate that Pillar 1's onboarding runs exposed
as too loose).

## Calibration outcome (2026-07-07, operator sign-off)

Three full eval passes against 97 operator verdicts (29 rejects / 68 approves), plus
an ensemble simulation across all three runs:

| Pass | Catch | False-fail |
|---|---|---|
| Run 1 (baseline prompts) | 62% | 19% |
| Run 2 (+certainty rule) | 55% | 18% |
| Run 3 (+operator-calibrated edges-first + characterize-then-compare) | 52% | 10% |
| Union of 3 runs (simulated) | 74% | 36% |
| Majority 2-of-3 (simulated) | 37% | 14% |
| Run 3 + cross-section anchor (2026-07-10) | 53% | 21% |

### Cross-section anchor re-calibration (2026-07-10)

The profile-anchor build (spec `2026-07-08-profile-anchor-design.md`) added the
catalog cross-section drawing to BOTH extraction and the identity judge. This
re-run uses Run-3's exact prompts with the drawing attached — the only variable
is the image. Result: **catch flat (52%→53%), false-fails DOUBLED (10%→21%)** —
the 80/20 gate is still unreachable, and the drawing made the judge worse, not
better. Per-door diff over the 85 doors common to both reports: the anchor
flipped **10 wrong→right but 13 right→wrong (net −3)**, and 10 of the 13 it
broke were APPROVED doors newly false-failed — the line drawing gives the judge
more profile-character detail to nitpick and it over-flags. It even damaged the
two hardest rejects (El Dorado, Terracina flipped from a correct catch to a
miss). This mirrors the lean-conditioning spike, where the same drawing hurt
lean GENERATION. **Recommendation: drop the cross-section from the identity
judge** (returns to the better-calibrated 52/10 Run-3 state); extraction's use
is untested in isolation and may still help (Apache/isabella/indiana flipped
right), so keep it there pending a separate extraction-only run. The judge
remains a re-roll ASSIST; Stage-A stays the authority regardless, so the only
practical cost of the current (anchored) judge is extra re-rolls and spurious
cap-hits — which removing the anchor would reduce.

Findings:
- Each run catches a different, weakly-overlapping subset — per-door detection is at
  the model's visual-discrimination limit; no vote scheme reaches 80/20.
- Operator adjudication of the never-caught 8 identified the dominant failure mode:
  **9:16 side-cropping** (the model narrows a door by cropping side stiles/molding
  instead of narrowing members — Apache, Rhode Island, Ambassador) plus outer-edge
  profile misses (bullnose) and profile-CHARACTER misses (sharp-vs-gradual raise,
  fat-vs-fine molding). These are now named in both prompts (edges-first discipline),
  which lifted hard-8 catches from 0 to 3 and halved false-fails.
- Decision: the identity judge ships as built inside `onboard_replica` — facts guide
  generation from attempt 1, defects guide retries, disqualification triggers re-rolls
  — but it is an ASSIST, not an approval oracle. Stage-A (operator reviews every
  replica) remains the identity gate. Re-run `scripts/qa_replica_eval.py` against the
  frozen verdict window when a stronger vision model ships.

## Problem

Replicas are the geometry anchor: every variant inherits the replica's profile, so a
replica must be a near-perfect (~99%) representation of the source door. The current
judge asks "is this usable as a product photo of the SAME door design?" and scores
similarity 1–5 with a min-3 gate. That grades *style-category* resemblance, not
*identity*.

Evidence from the 2026-07-06/07 onboarding wave: the operator rejected **29 replicas,
27 of them on `profile_character`** — nearly all of which the judge had scored min-4.
Example: the Talbot replica was a clean, correct-species louver door that the judge
loved, but it had ~13 loosely-spaced flat slats where the source has ~15 tightly-packed
rounded bullnose fins. A lovely louver door that is *not Talbot*.

The operator's bar: **identity, not similarity**. The judge should hunt for
*disqualifiers* — nameable geometric differences from the source — instead of scoring
quality.

## Decisions (made with operator)

1. **Disqualify bar: any visible geometric difference.** If the judge can NAME a
   geometric difference — element pitch/spacing, structural count, frame width, bevel
   depth or shape, molding/routing detail, arch geometry, panel raise/recess depth,
   artifacts, hardware, letterboxing — the replica is disqualified. Grain figure,
   lighting, shadow, and camera angle never disqualify.
2. **Defects feed the next attempt.** A named defect becomes a corrective line in the
   next learn attempt's conditioning. The re-learn ladder becomes defect-guided
   instead of generic.
3. **Mechanism: profile spec first, then verify** (approach B). One extraction call
   per door produces a reusable profile spec that BOTH guides generation (facts in the
   learn prompt from attempt 1) and powers verification (fact-by-fact check).
4. **Scale-invariance for 9:16.** Generated replicas are 9:16, usually taller than the
   catalog sample. Facts about repeating elements are expressed as pitch/profile,
   never absolute count.

## Design

### 1. Profile spec extraction — `backend/qa/profile_spec.py` (new)

One vision call per door (judge model, `gemini-3.1-pro-preview`), input = source photo
only. Output = a JSON list of short, individually verifiable geometric facts:

```json
{"facts": [
  "structural: single flat recessed panel, no center stile",
  "repeating: louver slats tightly stacked, gap ≈ 1/4 slat height, each a rounded bullnose fin",
  "frame: outer frame flat, ~2.25 inches wide, small inner step where it meets the slats",
  "corners: square, cope-and-stick joints (no 45° miter lines)"
]}
```

Extraction-prompt rules:
- **Walk the full door anatomy — one fact (or explicit "none/plain") per region:**
  1. **Outside edge** — the door's outer edge profile (square, eased, roundover, bevel)
  2. **Stiles & rails** — widths, equal or not, grain direction through them
  3. **Joints/corners** — miter (45° lines) vs cope-and-stick vs butt
  4. **Inside edge** — the frame-to-panel transition profile (sharp step, bevel, ogee,
     routed sticking)
  5. **Panel** — type (flat/raised/beadboard/plank/louver), raise profile or recess
     depth, surface texture
  6. **Trim / applied molding** — present or absent; profile if present
  7. **Top-rail / arch geometry** — square, cathedral, radius
  No region may be skipped: an unremarkable region gets a "plain/none" fact, which is
  itself verifiable (added trim where the source has none = defect).
- Countable/checkable facts only: structural counts, pitch/spacing ratios, widths (in
  inches where stated by the door spec, else relative to a repeating element),
  edge/bevel shapes, panel type and recess depth, joint type, arch geometry.
- **Structural counts are absolute** (panels, stiles, rails, mullions): fixed by the
  design at any door size.
- **Repeating patterns are pitch/profile, never count** (louver slats, beadboard
  grooves, plank boards): "the replica will be rendered at 9:16, likely taller than
  this sample — state pitch/spacing/profile relative to the elements themselves,
  never an absolute count."
- No prose about beauty, wood species, or grain. Grain/lighting never mentioned.
- Facts should be few and hard (typically 3–7); minimal-prose doctrine applies.

Stored via `store.update(profile_spec=...)` on the project manifest — extracted once,
reused across attempts and future re-onboards. Re-extraction only with an explicit
`--respec` flag on the driver.

### 2. Generation guidance — change in `backend/onboarding.py`

`onboard_replica` extracts the spec before attempt 1 (if not already on the project)
and appends the facts to the learn conditioning, alongside existing `style_notes`
(frame-width note etc.). The model is told "slats tightly stacked, bullnose" *before*
it generates, not after it fails.

### 3. Identity judge — `judge_replica_identity()` in `backend/qa/judge.py` (new function)

The old rubric (`RUBRIC_PROMPT`, min-score) is untouched — it still governs variants.

Input = source photo + replica + the facts list. One call, two-step procedure:
1. **Verify each fact** against the replica → `{fact, holds, observed}` per fact.
2. **Region sweep (structured free hunt):** walk the same seven anatomy regions —
   outside edge, stiles & rails, joints/corners, inside edge, panel, trim/molding,
   top-rail/arch — and for EACH region state "matches" or name the difference. The
   sweep runs even where a region has a fact, so a difference the extraction missed
   still gets caught.

Verify-prompt rules:
- "The generated door is 9:16 and may be taller than the sample — repeating elements
  continuing at the same pitch (more slats on a taller door) is CORRECT. A different
  pitch, spacing ratio, or element profile IS a defect."
- Explicit carve-out: grain figure, lighting, shadow, camera angle never disqualify.

Output JSON: `{"fact_checks": [...], "region_sweep": {"outside_edge": "matches" |
"<difference>", ...}, "disqualified": bool, "defects": ["one-line defect", ...]}`.
Any failed fact or any region-sweep difference disqualifies.

### 4. Defect-guided re-learn — change in the `onboard_replica` loop

On disqualify, the next attempt's conditioning gains a corrective block built from the
defects: "Your previous attempt had loosely-spaced flat slats; the source has tightly
stacked rounded bullnose slats — match the source exactly." Loop until no disqualifier
or the attempt cap. Best-of picking switches from highest-min-score to
fewest-defects (ties broken by the old min-score, which still runs as a secondary
signal during rollout).

### 5. Calibration gate — `scripts/qa_replica_eval.py` (new)

The 2026-07-06/07 review session produced a real calibration set: **29
operator-rejected + 68 operator-approved replicas** (verdicts in
`output/.qa/approvals.json`, images in the projects). Before the identity judge
replaces the gate in the onboarding loop:

- Run extraction + identity judge over every replica in that set.
- **Acceptance: catches ≥ 80% of the operator's rejects AND false-fails ≤ 20% of the
  operator's approves.** Below either bar → iterate on the prompts, do not ship.
- The frozen 179-label calibration (`output/.qa/labels.json`) is NOT touched — it
  governs the variant judge, which this design does not change.

## Boundaries

- `profile_spec.py` is pure input-prep: extraction prompt, parse, validation. No
  store or generation knowledge.
- `judge_replica_identity` is a sibling of the existing judge function; shares the
  client/retry plumbing, owns only its prompt and result shape.
- `onboarding.py` orchestrates: extract → condition → generate → verify → feed
  defects back. All policy (attempt caps, spend) stays where it is today.
- Fallbacks: extraction fails → onboard proceeds today's way (no spec, generic
  ladder), logged. Judge call fails → existing retry/error path.

## Testing

- Unit: extraction/verify prompt builders and parsers (pure functions) — fact-list
  validation, fenced-JSON stripping, defect aggregation, scale-invariance wording
  present.
- Golden: Talbot's extraction must yield a repeating-pattern fact with pitch/profile
  (and no absolute slat count); a center-stile door's extraction must yield an
  absolute structural count.
- Release gate: the calibration eval above, reported as a small table (catch rate,
  false-fail rate, per-door verdicts) for operator sign-off.

## Open questions (resolve during implementation)

1. Whether `already-approved` replicas from the RTF era should be back-checked with
   the identity judge (out of scope for the first cut; RTF is complete and approved).
2. Exact defect-corrective wording — keep to one line per defect, minimal prose.
3. Whether fewest-defects best-of should weight structural defects over repeating-
   pattern defects when no attempt is clean.
