# Phase 0 — Mechanism decomposition of the 17 missed geometry rejects

| # | key | kind | style | mechanism (primary) | secondary | measurable | notes |
|---|-----|------|-------|---------------------|-----------|------------|-------|
| 1 | 7efd9e3d:1:variant:2 | variant | recessed_panel | aspect | profile/non-metric | yes | replica is a wide landscape recessed drawer; candidate is a tall portrait raised-panel door — gross orientation/proportion swap. |
| 2 | 27eef02f:10:replica | replica | mission | profile/non-metric | — | no | cathedral arch curvature differs — candidate arch is broader/flatter with ogee shoulders vs sample's tighter arch. |
| 3 | 4ebf2d15:1:replica | replica | shaker | frame-width | — | yes | candidate top rail thin and bottom rail thick (unequal rails), wider stiles than the (zoomed) sample. |
| 4 | 58ad6f7f:1:replica | replica | recessed_panel_center_stile | frame-width | panel-position | yes | candidate outer stiles and top rail thicker, center stile wider; panels narrower/shifted vs sample. |
| 5 | 23d3dae0:1:replica | replica | recessed_panel | frame-width | — | yes | candidate frame border wider (panel smaller) than the tiny low-res sample; ogee reveal present in both. |
| 6 | 27eef02f:11:replica | replica | mission | profile/non-metric | — | no | arch curvature wrong — candidate crown lower and broader with S-shaped shoulders vs sample's peaked arch. |
| 7 | 571ae351:1:variant:0 | variant | drawer_durango_minimal | frame-width | — | yes | candidate frame much thicker relative to panel than the replica's near-cropped thin frame. |
| 8 | 4ebf2d15:1:variant:0 | variant | shaker | frame-width | — | yes | candidate (cherry) stiles wider and frame thicker than walnut replica; panel narrower. |
| 9 | 92e60a19:2:replica | replica | drawer_durango | frame-width | — | yes | candidate frame slightly wider/thicker than sample (same cherry-knot photo); panel smaller. |
| 10 | 58ad6f7f:2:replica | replica | recessed_panel_center_stile | frame-width | panel-position | yes | candidate top rail much thicker than bottom rail, wide stiles; panels pushed down vs uniform sample. |
| 11 | 098e0626:3:replica | replica | drawer_solid_plank | profile/non-metric | aspect | no | excluded class (slab/plank); candidate applied edge-molding profile differs and is more elongated, but no frame to measure. |
| 12 | 571ae351:2:replica | replica | drawer_durango_minimal | frame-width | — | yes | candidate outer border wider than sample's thin ogee-molded frame; panel smaller. |
| 13 | 4ebf2d15:1:variant:1 | variant | shaker | frame-width | — | yes | candidate (ash) frame wider with thick bottom rail vs walnut replica; panel narrower. |
| 14 | 92e60a19:1:replica | replica | drawer_durango | frame-width | panel-position | yes | candidate top rail far too thick, bottom rail thin; panel shifted down vs thin-top-rail sample. |
| 15 | 367b7b57:0:replica | replica | drawer_durango | frame-width | — | yes | candidate frame subtly wider/thicker than identical cherry-knot sample; borderline reject. |
| 16 | 4962feb2:0:replica | replica | drawer_durango | frame-width | — | yes | candidate frame slightly wider than identical cherry-knot sample; panel smaller; borderline. |
| 17 | b684d34b:0:variant:0 | variant | drawer_minimal | frame-width | — | yes | candidate (oak) stiles wider and panel narrower than maple replica; recess shadow flipped. |

## Rollup
- replica-vs-sample: 12 | variant-vs-replica: 5
- mechanisms: aspect 1, frame-width 13, panel-position 0, boundary-count 0, profile/non-metric 3
- measurable (addressable by ratio comparison): 14 of 17 (82%)
- measurable among variant misses specifically: 5 of 5
- Excluded-class entries: 1 (098e0626:3:replica:-1 — drawer_solid_plank)

## Observations
- Frame-width drift dominates: 13 of 17 misses are stile/rail width-ratio errors, almost always the candidate frame being too thick/wide (panel too small) — this is the highest-value target for a deterministic ratio check.
- The three drawer_durango cherry replicas (92e60a19:2, 367b7b57, 4962feb2) share the identical ground-truth photo (cherry recessed panel, two knots) and all fail the same way: a frame a few percent too wide. Two of them (367b7b57, 4962feb2) are subtle enough that I'd call the human reject borderline — a ratio check needs a sensible tolerance to catch these without over-firing.
- Several samples are very low-res or tightly cropped (23d3dae0 ~150px, 92e60a19:1 & 098e0626 ~400px, 4ebf2d15 replica zoomed so the frame is cut off), which plausibly explains why the LLM judge passed them and warns that per-image frame-ratio ground truth will be noisy.
- The two mission (27eef02f) misses are genuine profile/non-metric arch-curvature errors — not catchable by axis-aligned ratios and legitimately outside a metric module's scope. Same for the excluded slab (098e0626), whose defect is applied edge-molding character.
- The two recessed_panel_center_stile misses (58ad6f7f x1/x2) share a too-thick top rail + wide-stile pattern, echoing the prior memory note about center-stile uniform-width bugs; both also drift panel position downward.
- Only one true aspect failure (entry 1), but it is egregious — a landscape recessed drawer replica regenerated as a portrait raised-panel door — so an aspect-ratio gate is cheap insurance even though it fires rarely.
