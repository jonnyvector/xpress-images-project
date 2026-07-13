# Wood-Door Judgment: Species Matching Design

**Date:** 2026-07-06
**Status:** Design — not yet implemented (captured from a working discussion)
**Depends on:** the existing QA judgment pipeline (`docs/qa-pipeline.md`,
`backend/qa/`) and the graduated-trust pipeline.

## Problem

The judgment pipeline was built and calibrated on wood doors, then extended to
RTF. As we return to onboarding wood doors at scale, the judge's material check
is weak: it scores `swatch_fidelity` against a small (~2 inch) swatch chip. A
chip conveys color but almost nothing about how a species reads across a full
finished door, so "is this actually Red Oak Select and not maple-with-a-stain?"
is a question the swatch can't really answer at door scale.

## Decision: three orthogonal checks

Keep the judgment factored into three independent questions, each answered by
its own reference so they don't contaminate each other:

1. **Geometry / profile** — variant vs the door's own approved replica.
   Already exists (hard gate). **Unchanged.**
2. **Wood-type / species** — the part this design addresses.
3. **Realism** — artifacts, believable surface. Already exists. **Unchanged.**

## Wood-type check

**Color is the verdict; pore-texture is the tiebreaker; grain figure is free to
vary.**

- **Color / tone (primary).** Species + finish have a stable color signature
  (oak: light tan with a pink undertone; cherry: warm reddish-brown; maple: pale
  cream; walnut: chocolate). This holds across boards, so it is the reliable
  discriminator.
- **Pore / texture character (secondary).** Species-stable even though figure is
  not — oak is coarse and open-pored, maple smooth and tight, walnut in between.
  A soft check that catches wrong-species cases where the color happens to be
  close ("too glassy-smooth to be oak"). Sidekick, not lead.
- **Grain figure (ignore).** Cathedrals, streak layout, busyness vary enormously
  board-to-board within one species. Judging on figure would flag legitimate
  natural variation as errors, so the judge is told explicitly to allow it.

**Judge instruction must be material-only.** The reference door may have a
different profile; the judge is told to compare *only* species and finish and to
ignore door shape — the same discipline that keeps geometry prose out of RTF
material judgments. The question is "same species and finish family?", not "same
board?".

## References

Two references, two jobs:

- **Swatch** — the supplier's authoritative *intended* color. Kept.
- **Blessed canonical door per species** — one operator-blessed door that defines
  what the species looks like at door scale.

Because the wood-type check is orthogonal to profile, **one canonical door per
species covers the entire catalog** (all profiles × that species). Roughly one
blessed door per wood species (~40 from `swatches/wood_types.json`) covers
everything.

### Generated, not real-photo — because of lighting

The canonical door should be a **generated, approved** door, not a real
photograph. Color comparison is brutally sensitive to white balance: a real
photo (or a raw chip) shot under different light makes the same oak read warmer
or cooler for reasons that have nothing to do with the wood. A generated
canonical shares the variant's studio/white-background lighting, giving an
apples-to-apples color comparison. For color-matching, matched lighting beats
authenticity.

### Blessing mechanism

"Blessing" is a new operator act: a mutable flag marking one `image_id` as
canonical for species X (re-bless to replace when a better door appears). This
is the material twin of the replica-as-geometry-anchor: approving doors seeds a
per-species reference over time.

**Bootstrap:** until a species is blessed, fall back to swatch-only (today's
behavior). Bless a *textbook-representative* board — middle-of-the-road figure,
natural finish — not a showpiece or an outlier, so a single reference doesn't
become a straitjacket.

## Implementation guardrail

Wood is the **original calibrated domain**. The frozen ground truth in
`output/.qa/labels.json` (179 human labels, never modified) was built on wood
doors. Any change to what the judge sees — an added species reference, a new or
reweighted dimension — MUST be re-run against those labels to prove it doesn't
regress the recall/false-flag numbers that already pass. This is the one place
to be most careful; it is a gate, not a nicety.

## Open questions (defer to implementation)

- Does species matching become a **reweighting of the existing `swatch_fidelity`
  dimension**, or a **new dimension** (e.g. `species_match`)? Either way, both
  the swatch and the canonical door go into the judge prompt.
- How to phrase the color-vs-figure weighting so the judge reliably discounts
  figure without also discounting a genuine wrong-species tell.
- Whether pore-texture warrants its own sub-score or stays folded into the
  species judgment.
- Canonical-door curation UI: how the operator blesses/re-blesses.
