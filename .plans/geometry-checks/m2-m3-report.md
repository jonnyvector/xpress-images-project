# M2 + M3 Implementation Report — geometry-checks Phase 2

Status: **DONE**. Both milestones delivered strict-TDD (RED → GREEN), every
current-cutoff checkbox checked. All 62 QA tests green (39 pre-existing + 8 M2
+ 15 M3), ruff clean on `backend/qa` and `tests/qa`.

## M2 — Style-class router

`backend/qa/styles_classes.py` + `tests/qa/test_styles_classes.py`.

- Explicit `STYLE_CLASSES` dict mapping **all 38 catalog keys** to one of
  `frame_standard` (20), `frame_narrow` (3), `excluded` (15). Module docstring
  documents the three classes and the fail-safe contract.
- `style_class(door_style)` — unknown / `None` / empty → `excluded` (fail-safe).
- A test asserts `set(STYLE_CLASSES) == set(STYLES)`, so any future catalog key
  added without a mapping fails CI.

Classification rationale:
- **frame_standard** — rectangular recessed/flat-panel doors (shaker family,
  recessed_panel*, terracina, graham, hayes, mitered applied-molding, alpine,
  durango, routed, …).
- **frame_narrow** — skinny-shaker family (`mitered_flat_panel`,
  `rtf_drawer_shaker_skinny`, `drawer_journey`) — same geometry, smaller frame
  fraction, own threshold class.
- **excluded** — slabs (`solid_plank`, `vienna`, `drawer_solid_plank`), bevels
  (`rtf_drawer_bevel`), planks (`davenport`), louvers, radius/arched (`mission`,
  `*_radius`), raised/beveled panels (`raised_panel`, `drawer_raised_panel`),
  the raised-rounded `drawer_harmony`, and unknown/minimal test styles
  (`rtf_minimal`, `drawer_minimal`, …) — fail-safe to excluded when structure
  is ambiguous.

## M3 — Synthetic measurement core

`backend/qa/geometry.py` + `tests/qa/test_geometry.py`. numpy + Pillow only.

### Pipeline
1. **Load/grayscale** at `min(native, working_width)` (LANCZOS downscale).
2. **Sobel** gradients via a 3×3 numpy convolution (`_conv3`, edge-pad; no
   scipy/cv2). Cropping to the box first means edge-padding suppresses the outer
   door outline, so only interior frame/panel edges survive.
3. **Box detection** (`_detect_box`) — foreground extent (columns/rows whose
   coverage exceeds 50% of a near-white-relative darkness threshold) + three
   confidence checks: `min_box_fraction`, near-white/low-variance margin, aspect
   sanity 0.2–5.0. Any failure → GEO-002.
4. **Directional edge-energy profiles** — `|Gx|` summed over rows (vertical
   boundaries), `|Gy|` summed over columns (horizontal boundaries).
5. **Boundary detection** (`_boundaries`) — local maxima gated by three
   independent filters: **absolute** per-pixel edge strength (scale-invariant,
   0.03), **relative** prominence (0.15 of profile range), and **two-scale
   persistence** (the double-box-smoothed coarse profile must still carry a real
   energy bump within tolerance — grain spikes vanish, real edges persist).
   Positions refined to sub-pixel by parabolic interpolation (`_refine`).
6. **Comparison** — aspect delta (relative), order-preserving DP boundary
   matching per axis (`_match_boundaries`), stile/rail width deltas from the
   outermost boundaries, `max_delta`, `unmatched_boundaries`.
7. **Verdict/confidence** exactly per Contracts: drift iff `max_delta` > class
   threshold OR `aspect_delta` > `aspect_threshold` OR (`unmatched` > 0 AND high
   confidence); high confidence only when both boxes pass, mean match residual ≤
   `max_match_residual`, boundary counts agree within one, and not partial.

### Accuracy (the ±0.005 gate)
Independent verification sweep — 150 fixtures (30 seeds × 5 stile/rail configs),
600 boundary measurements, all noisy (grain + JPEG q85):

| metric | value |
|--------|-------|
| mean abs error | **0.00108** |
| max abs error | **0.00229** |
| all ≤ 0.005 | **yes** |
| box/boundary misses | **0** |

Committed test `test_recovers_ratios_within_tolerance` asserts ≤0.005 on all
four boundaries; `test_identical_geometry_is_ok_high_confidence` asserts
`status=ok, confidence=high, max_delta≤0.005`.

### Distortion detection
- `test_stile_widening_detected[0.02]` and `[0.03]` → drift, `max_delta>0.015`,
  detail names `stile`.
- `test_rail_widening_detected` (0.03) → drift, detail names `rail`.
- `test_panel_shift_detected` (0.03 shift) → drift, `max_delta>0.015`.

### DP matching / non-cascade
- `test_dp_spurious_peak_does_not_cascade` — spurious mid peak → `unmatched==1`,
  4 real boundaries still matched with `max delta ≤ 0.001` (no cascade).
- `test_dp_unmatched_strong_boundary_counted_separately` and
  `test_single_extra_boundary_high_confidence_is_drift` — unmatched counted, not
  folded into deltas.
- `test_added_center_boundary_is_unmatched_not_folded` — a rendered center stile
  (2 extra edges) is counted in `unmatched_boundaries`, not folded into
  `max_delta`, and never a confident clean pass. Note: 2 extra edges → count
  mismatch of 2 → low confidence per the normative rule, so it defers to the
  judge rather than auto-flagging; a single extra boundary stays high-confidence
  and would flag as drift.

### Error paths (measure() never raises)
- GEO-001 unreadable/corrupt file → unmeasurable.
- GEO-002 box-confidence failure (busy margin) → unmeasurable, detail names the
  image (`candidate`) and the failing check.
- GEO-003 no interior peaks (solid rectangle) → partial, low confidence, detail
  carries `GEO-003` (aspect still measured).
- GEO-004 injected exception (monkeypatched internal) → unmeasurable, detail
  carries `GEO-004`, no raise.

### Timing (informational)
Printed in test output. Per-pair `measure()`:

| working width | ms/pair |
|---------------|---------|
| 1024px | ~69 ms |
| 1536px | ~170–305 ms |

Well under any practical budget; dominated by the two Sobel convolutions.

## Algorithm notes / concerns
- **Grain suppression is layered**: the absolute per-pixel edge-strength gate
  (0.03) alone rejects grain by ~50× margin; two-scale persistence is the
  belt-and-suspenders required by the plan. Early moving-average coarse
  smoothing left ripples that fragmented the coarse prominence walk (dropped one
  real boundary at seed 0); switching the persistence check to a *windowed local
  range* on a **double-box-smoothed** coarse profile fixed it (0 misses across
  150 fixtures).
- `_MIN_EDGE_STRENGTH=0.03` is tuned to clean synthetic contrast (frame↔panel
  step ≈0.23 per-pixel). **Real sample photos (M4) may have lower-contrast
  recessed-panel shadows**; this floor is the most likely knob to revisit in the
  Phase 2 spike, and is exactly what A-001 will stress. It is a module constant,
  easily promoted to `GeometryConfig` if the spike demands per-class tuning.
- `measure()` gains a keyword-only `reference: str = "sample"` so the report's
  `reference` field can be set by the eval layer (D3 dual reference) without
  changing the normative positional signature.
- Nothing here touches policy/eval/judge or `output/.projects/` — geometry.py
  owns image-bytes → GeometryReport only, per the Boundaries section.

## Not in scope here
M4 (real-fixture spike, A-001/A-002), M5 (policy composition), M6 (eval wiring)
remain. This delivers the measurement core they build on.
