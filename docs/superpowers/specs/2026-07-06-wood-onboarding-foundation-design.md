# Wood Onboarding Foundation Fix

**Date:** 2026-07-06
**Status:** Design — approved, ready for implementation planning
**Supersedes/extends:** `2026-07-06-wood-door-judgment-design.md` (that doc's
species-matching design becomes Pillar 2 here, made concrete).

## Problem

The first wood onboarding batches got ~half the replicas rejected by the
operator despite the judge scoring them a clean min-4. Root-causing the
rejections exposed two independent foundation cracks:

1. **Style is mis-derived.** The wood driver set `door_style` from the Decore
   catalog folder (`raised-panel/` vs `inset-panel/`). But that folder groups by
   *frame construction, not panel type* — so it mixes planks, louvers,
   beadboard, shakers, and actual raised panels. Tacoma (a solid plank) and
   Talbot (a louver) were onboarded as raised panels: the wrong door entirely.
2. **The judge is blind to wood color/species.** Correctly-styled doors came
   back the wrong wood (Camden's maple rendered oak-toned, Sheffield's cherry
   washed out). The judge passed them on `swatch_fidelity`; the operator
   rejected them. A small swatch can't police species at door scale.

A third, related issue — the model widening narrow ("skinny shaker") frames —
turned out to be fixable with a *specific-fact* conditioning line, and Pillar 1
supplies that fact (the exact frame width) as a byproduct.

## Key insight

The catalog's `product.json` **descriptions are accurate and specific** and were
being ignored in favor of the folder. Examples:

- Tacoma — "sleek and simple **solid panel**"
- Talbot — "**louver-like detailing**... **2-1/4" wide frame**"
- Camden — "butt-joint frame surrounds a **beaded panel**"
- Sheffield — "miter joint... **raised panel**"
- Newbury — "miter frame **skinny shaker**... **2" frame width**"

The manufacturer states the style, the construction (miter/butt/cope), and often
the exact frame width. This is a far better source of truth than the folder and
richer than a vision guess.

## Design

Two pillars over five well-bounded pieces. Pillars share this spec; Pillar 1
lands first in practice (it unblocks onboarding), Pillar 2 matters at the
variant/bulk stage.

### Pillar 1 — Description-driven door specs (fixes style + proportions)

Stop deriving anything from the folder. A one-time **classifier pass** runs each
wood door through the model with its `product.json` description + hero image and
emits a validated structured record:

```json
"Newbury": {
  "door_style": "shaker",          // enum from backend/styles/catalog.STYLES
  "panel": "flat",                 // flat | raised | slab | louver | beadboard
  "frame_width_in": 2.0,           // parsed from "2\" frame width" when stated
  "joint": "miter",                // miter | butt | cope | null
  "arched": false,
  "notes": "skinny shaker, solid panel"
}
```

- **Output:** a checked-in `docs/sales/data/wood_door_specs.json` — the single
  source of truth for wood door structure. The operator reviews it once (~160
  rows), correcting any misreads. From then on the driver reads this, never the
  folder.
- **Fixes style:** Tacoma → `solid_plank`, Talbot → `louver`, Camden → beadboard,
  Newbury → `shaker`.
- **Fixes proportions:** `frame_width_in` becomes a *specific-fact* conditioning
  line ("the frame is exactly 2 inches wide — thin; do not widen it"), the form
  of instruction that beat the skinny-frame prior on Newbury. One hard number,
  not verbose prose (per the minimal-learn-prompt finding).
- **Scope:** classify ALL wood doors, so it also flags already-approved doors
  whose folder-derived style was wrong, for re-onboarding.

### Pillar 2 — Canonical-door species judge (fixes color/species)

Fires in the **variant phase** (rendering a door across the 38 wood species).
Adds a second reference to the judge — the **blessed canonical door** for that
species — and reframes the material question:

> "Is the variant the same wood species and finish as the swatch and the
> canonical door? Judge color and tone; allow natural grain-figure variation;
> ignore door shape and profile."

Color is the verdict, pore-texture the tiebreaker, grain figure is free to vary.

- **Canonical library:** one operator-blessed door per species (a *generated*
  door, so lighting matches variants), stored as a mutable `species → image_id`
  registry. Bootstrap: until a species is blessed, fall back to swatch-only
  (today's behavior).
- **Blessing:** a single control in the Review tab on any approved door ("make
  this the Red Oak reference").
- **Calibration gate (non-negotiable):** the reworked judge MUST be re-run
  against the frozen 179 labels in `output/.qa/labels.json` and hold its recall /
  false-flag numbers before it ships. Regression = it does not go live.

## Architecture / boundaries

Input-prep, isolated from the running pipeline:
1. **`scripts/classify_wood_doors.py`** — the one-time classifier (re-runnable).
   Reads catalog descriptions + images → writes the spec file. Touches nothing
   else.
2. **`docs/sales/data/wood_door_specs.json`** — version-controlled source of
   truth for wood door structure.

Runtime changes:
3. **`scripts/onboard_wood.py`** — reads the spec file instead of the
   folder→style rule; frame width becomes a conditioning fact. The hand-kept
   `OVERRIDES` dict is removed (the spec subsumes it).
4. **`backend/qa/canonical.py`** — a small `species → image_id` registry, sibling
   to `approvals.py`. One job: remember the blessed door per species.
5. **Judge extension** in `backend/qa/judge.py` — optional species-reference image
   input + the material-only species question. Behind the calibration gate.

Plus a thin **bless control**: one endpoint + a Review-tab button.

**Clean seams:** classifier and spec file are pure data prep — a wrong
classification is a one-line JSON fix, nothing else breaks. The canonical
registry is a lookup. The judge change is the only thing touching calibrated
behavior, so it's the only thing behind the re-validation gate. Each piece is
testable alone: classify without onboarding, bless without judging, judge against
the frozen labels without the rest.

## Testing

- **Classifier:** golden-set test — a handful of known doors (Tacoma=plank,
  Talbot=louver, Camden=beadboard, Sheffield=raised, Newbury=shaker) must
  classify correctly; frame widths parsed where stated.
- **Spec-driven driver:** unit test that `onboard_wood` reads a door_style +
  frame-width note from the spec file, with no folder lookup.
- **Canonical registry:** set/get/re-bless, per-species isolation.
- **Judge:** material-only prompt shape; species-reference image reaches the
  call; and the calibration re-run against the 179 labels as a gate (not a unit
  test — a release check).

## Open questions (resolve during implementation)

1. `swatch_fidelity` re-scoped vs a new `species_match` dimension — pick based on
   what the calibration re-run tolerates without busting recall.
2. Exact conditioning wording for `frame_width_in` (specific fact, minimal prose).
3. Whether the classifier also backfills RTF (out of scope now; RTF is complete).
4. Blessing UI placement in the Review tab.
