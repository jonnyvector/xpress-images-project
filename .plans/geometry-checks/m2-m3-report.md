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

---

# Addendum — real-fixture iteration (post-M4-spike fixes)

The M4 spike surfaced two failure modes on real fixtures. Both fixed in
`backend/qa/geometry.py`; all 62 prior tests green (none weakened), 11 new
tests (73 total), ruff clean.

## Fix 1 — full-bleed box fallback (Problem 1)

Real photographed samples are **full-bleed crops**: the door fills the frame,
there is no near-white background to find (border medians 0.00–0.88 vs render
backgrounds at 1.00 ± 0.003). `_detect_box` now has two regimes:

- near-white border → foreground-extent box (as before), with **adaptive
  coverage** (threshold = half the peak column/row coverage instead of a fixed
  50%) so a drawer occupying <50% of one dimension is still boxed;
- non-white border → **full-frame box** (`full_bleed=True`). A clearly
  door-toned border (< 0.70) is a clean full-bleed photo, eligible for high
  confidence; a border in the ambiguous 0.70–0.85 band, or a near-white but
  textured border where no door-sized foreground exists (pale maple filling
  the frame, e.g. 92e60a19), forces confidence low.

Consequence handled: a full-bleed box is the *photo crop*, not the door
outline, so its aspect is not evidence — humans accepted replicas with
aspect_delta ≈ 0.45 against square catalog crops while a rejected replica of
the same door showed 0.46 (indistinguishable). When either box is full-bleed
the aspect check is excluded from the drift rule and the detail string carries
"aspect_delta=... (unverified: full-bleed crop)". Replica-vs-sample safety is
preserved by D1 replica review; variant-vs-replica comparisons (render vs
render) keep the aspect gate.

GEO-002 semantics preserved: cluttered-margin product shots and blank images
still fail box confidence (regression-tested).

## Fix 2 — strong-peak floor + cross-energy check for unmatched (Problem 2)

`_boundaries` now returns per-peak strengths (per-pixel prominence) and the
smoothed per-pixel energy profile. An unmatched peak counts in
`unmatched_boundaries` only if:

1. **strength floor** — its strength ≥ 0.6 × the median matched-boundary
   strength of its own image (no matched structure → all count, fail-safe);
   and
2. **cross-energy check** — the OTHER image lacks comparable edge energy at
   that position (windowed range of its energy profile within ±0.04,
   requirement `max(0.03, min(0.5 × peak strength, 0.09))`). Rationale: wood
   tone changes how sharply the same edge renders (a 0.46-strength maple edge
   was a real 0.13-strength cherry edge); energy present in both images means
   shared structure, not drift. The cap (3× the absolute detection floor)
   keeps a "clearly real" edge sufficient regardless of the unmatched peak's
   own contrast.

Stile/rail width deltas now come from the outermost MATCHED pairs (not raw
first/last peaks), so a spurious peak near an edge cannot corrupt them.
Synthetic added-center-stile detection still works: the flat synthetic panel
carries only grain-level energy (~0.016 windowed) at the added stile position,
well under the 0.03 minimum.

## Spike sweep after fixes (all manifest fixtures; variant→replica primary, replica→sample)

Config: working_width 1536, thresholds frame_standard 0.015 / frame_narrow
0.02 (placeholders until M7), aspect 0.04.

| key | kind | group | label | class | ref | status | conf | max_d | asp_d | unm | detail |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7efd9e3d:1:variant:2 | variant | miss | reject | frame_standard | replica | unmeasurable | low | 0.000 | 0.000 | 0 | GEO-002: candidate box check failed: box_fraction 0.324 < min |
| 27eef02f:10:replica:-1 | replica | miss | reject | excluded | sample | drift | high | 0.015 | 0.116 | 0 | drift; worst stile.left=0.015 (thr 0.015); aspect_delta=0.116 (unverified: full-bleed crop); unmatched=0 |
| 4ebf2d15:1:replica:-1 | replica | miss | reject | frame_standard | sample | ok | low | 0.005 | 0.461 | 0 | ok; worst stile.left=0.005 (thr 0.015); aspect_delta=0.461 (unverified: full-bleed crop); unmatched=0 |
| 58ad6f7f:1:replica:-1 | replica | miss | reject | frame_standard | sample | drift | low | 0.049 | 0.452 | 4 | drift; worst stile.right=0.049 (thr 0.015); aspect_delta=0.452 (unverified: full-bleed crop); unmatched=4 |
| 23d3dae0:1:replica:-1 | replica | miss | reject | frame_standard | sample | ok | high | 0.014 | 0.166 | 0 | ok; worst stile.left=0.014 (thr 0.015); aspect_delta=0.166 (unverified: full-bleed crop); unmatched=0 |
| 27eef02f:11:replica:-1 | replica | miss | reject | excluded | sample | drift | high | 0.026 | 0.077 | 0 | drift; worst stile.left=0.026 (thr 0.015); aspect_delta=0.077 (unverified: full-bleed crop); unmatched=0 |
| 571ae351:1:variant:0 | variant | miss | reject | frame_standard | replica | drift | low | 0.062 | 0.028 | 0 | drift; worst stile.left=0.062 (thr 0.015); aspect_delta=0.028 (unverified: full-bleed crop); unmatched=0 |
| 4ebf2d15:1:variant:0 | variant | miss | reject | frame_standard | replica | ok | low | 0.000 | 0.000 | 0 | ok; worst stile.right=0.000 (thr 0.015); aspect_delta=0.000; unmatched=0 |
| 92e60a19:2:replica:-1 | replica | miss | reject | frame_standard | sample | drift | low | 0.067 | 0.108 | 0 | drift; worst boundary.1=0.067 (thr 0.015); aspect_delta=0.108 (unverified: full-bleed crop); unmatched=0 |
| 58ad6f7f:2:replica:-1 | replica | miss | reject | frame_standard | sample | drift | high | 0.034 | 0.487 | 1 | drift; worst boundary.1=0.034 (thr 0.015); aspect_delta=0.487 (unverified: full-bleed crop); unmatched=1 |
| 098e0626:3:replica:-1 | replica | miss | reject | excluded | sample | drift | low | 0.043 | 0.319 | 0 | drift; worst boundary.1=0.043 (thr 0.015); aspect_delta=0.319 (unverified: full-bleed crop); unmatched=0 |
| 571ae351:2:replica:-1 | replica | miss | reject | frame_standard | sample | drift | low | 0.073 | 0.078 | 1 | drift; worst stile.right=0.073 (thr 0.015); aspect_delta=0.078 (unverified: full-bleed crop); unmatched=1 |
| 4ebf2d15:1:variant:1 | variant | miss | reject | frame_standard | replica | ok | low | 0.001 | 0.000 | 0 | ok; worst stile.left=0.001 (thr 0.015); aspect_delta=0.000; unmatched=0 |
| 92e60a19:1:replica:-1 | replica | miss | reject | frame_standard | sample | drift | low | 0.062 | 0.046 | 0 | drift; worst stile.left=0.062 (thr 0.015); aspect_delta=0.046 (unverified: full-bleed crop); unmatched=0 |
| 367b7b57:0:replica:-1 | replica | miss | reject | frame_standard | sample | drift | low | 0.081 | 0.066 | 0 | drift; worst boundary.1=0.081 (thr 0.015); aspect_delta=0.066 (unverified: full-bleed crop); unmatched=0 |
| 4962feb2:0:replica:-1 | replica | miss | reject | frame_standard | sample | drift | low | 0.050 | 0.029 | 0 | drift; worst stile.right=0.050 (thr 0.015); aspect_delta=0.029 (unverified: full-bleed crop); unmatched=0 |
| b684d34b:0:variant:0 | variant | miss | reject | excluded | replica | ok | low | 0.009 | 0.157 | 0 | ok; worst rail.bottom=0.009 (thr 0.015); aspect_delta=0.157 (unverified: full-bleed crop); unmatched=0 |
| 2564359f:0:replica:-1 | replica | accept | accept | frame_standard | sample | drift | low | 0.023 | 0.455 | 4 | drift; worst stile.left=0.023 (thr 0.015); aspect_delta=0.455 (unverified: full-bleed crop); unmatched=4 |
| 2564359f:0:variant:2 | variant | accept | accept | frame_standard | replica | ok | high | 0.006 | 0.006 | 0 | ok; worst stile.left=0.006 (thr 0.015); aspect_delta=0.006; unmatched=0 |
| 2564359f:0:variant:0 | variant | accept | accept | frame_standard | replica | ok | high | 0.004 | 0.004 | 0 | ok; worst boundary.1=0.004 (thr 0.015); aspect_delta=0.004; unmatched=0 |
| 44130ef4:0:replica:-1 | replica | accept | accept | excluded | sample | ok | low | 0.014 | 0.003 | 0 | ok; worst rail.bottom=0.014 (thr 0.015); aspect_delta=0.003 (unverified: full-bleed crop); unmatched=0 |
| 2a13631b:0:replica:-1 | replica | accept | accept | excluded | sample | ok | low | 0.000 | 0.000 | 0 | ok; worst rail.top=0.000 (thr 0.015); aspect_delta=0.000; unmatched=0 |
| 2a13631b:0:variant:0 | variant | accept | accept | excluded | replica | ok | low | 0.002 | 0.001 | 0 | ok; worst rail.top=0.002 (thr 0.015); aspect_delta=0.001; unmatched=0 |
| 571ae351:1:replica:-1 | replica | accept | accept | frame_standard | sample | ok | low | 0.001 | 0.000 | 0 | ok; worst rail.bottom=0.001 (thr 0.015); aspect_delta=0.000 (unverified: full-bleed crop); unmatched=0 |
| 92e60a19:11:replica:-1 | replica | accept | accept | frame_standard | sample | ok | low | 0.002 | 0.050 | 0 | ok; worst stile.right=0.002 (thr 0.015); aspect_delta=0.050 (unverified: full-bleed crop); unmatched=0 |
| 4ebf2d15:0:replica:-1 | replica | accept | accept | frame_standard | sample | drift | high | 0.019 | 0.448 | 0 | drift; worst rail.bottom=0.019 (thr 0.015); aspect_delta=0.448 (unverified: full-bleed crop); unmatched=0 |
| 40236826:0:replica:-1 | replica | accept | accept | frame_standard | sample | drift | low | 0.051 | 0.447 | 2 | drift; worst boundary.2=0.051 (thr 0.015); aspect_delta=0.447 (unverified: full-bleed crop); unmatched=2 |
| 571ae351:0:replica:-1 | replica | accept | accept | frame_standard | sample | ok | high | 0.000 | 0.000 | 0 | ok; worst stile.right=0.000 (thr 0.015); aspect_delta=0.000 (unverified: full-bleed crop); unmatched=0 |
| b684d34b:0:replica:-1 | replica | accept | accept | excluded | sample | ok | low | 0.001 | 0.000 | 0 | ok; worst rail.bottom=0.001 (thr 0.015); aspect_delta=0.000 (unverified: full-bleed crop); unmatched=0 |
| 4ebf2d15:0:variant:0 | variant | accept | accept | frame_standard | replica | ok | high | 0.000 | 0.001 | 0 | ok; worst stile.left=0.000 (thr 0.015); aspect_delta=0.001; unmatched=0 |
| 40236826:0:variant:0 | variant | accept | accept | frame_standard | replica | ok | high | 0.001 | 0.002 | 0 | ok; worst stile.left=0.001 (thr 0.015); aspect_delta=0.002; unmatched=0 |
| 7634b572:0:replica:-1 | replica | accept | accept | excluded | sample | ok | high | 0.000 | 0.000 | 0 | ok; worst boundary.2=0.000 (thr 0.015); aspect_delta=0.000; unmatched=0 |
| 571ae351:0:variant:0 | variant | accept | accept | frame_standard | replica | ok | high | 0.001 | 0.000 | 0 | ok; worst rail.top=0.001 (thr 0.015); aspect_delta=0.000 (unverified: full-bleed crop); unmatched=0 |
| 4ebf2d15:0:variant:1 | variant | accept | accept | frame_standard | replica | ok | high | 0.001 | 0.001 | 0 | ok; worst stile.right=0.001 (thr 0.015); aspect_delta=0.001; unmatched=0 |
| 40236826:0:variant:1 | variant | accept | accept | frame_standard | replica | ok | high | 0.003 | 0.002 | 0 | ok; worst stile.right=0.003 (thr 0.015); aspect_delta=0.002; unmatched=0 |

measurable-class fixtures: 26
replica-vs-sample: 15 attempted, 15 measurable, 4 at high confidence
accepts: 13, high-conf false drifts: 1 ['4ebf2d15:0:replica:-1']
unmeasurable: 1
variant misses: 4, drift-detected: 1

### Headline numbers

| metric | before fixes | after fixes |
|---|---|---|
| replica-vs-sample measurable | 0/15 (all GEO-002) | **15/15** |
| ...at high confidence | 0/15 | 4/15 (rest low: forced-low ambiguous margins, boundary-count disagreement, GEO-003 partial) |
| accepts flagged drift at high confidence | 6/13 | **1/13** (4ebf2d15:0:replica — max_delta 0.019 rail vs placeholder threshold 0.015; M7 calibration) |
| unmeasurable (measurable classes) | 4 | 1 (7efd9e3d:1:variant:2 — candidate box_fraction 0.324 < configured 0.40 min; honest GEO-002 → needs_human; it is a labeled reject) |
| 2564359f:0:variant:0 / :2 | drift high (unm 1–2) | **ok high, unm 0** |

### Notes for M4/M7

- Synthetic accuracy unchanged: 600 measurements, mean err 0.00108, max
  0.00229, 0 misses; per-pair timing ~150 ms @1536px.
- A-001 signal: 15/15 measurable but only 4/15 replica-vs-sample at high
  confidence. Low-confidence causes are inspectable per pair (detail strings);
  most are real photo noise producing boundary-count disagreement or partial
  axes. A-001's ≥80% high-confidence target looks unlikely on this evidence —
  escape hatch 1 (low-confidence-only replica-vs-sample + D1 review) may apply.
- Variant-miss detection: 1/4 drift + 1/4 unmeasurable(→needs_human). The two
  "ok" misses (4ebf2d15:1 variants) are geometrically IDENTICAL to their
  replica (max_delta ≤ 0.001) — the v1 rejection was the replica itself being
  wrong vs sample. Variant-vs-replica consistency is the wrong reference for
  them; the D3 sample backstop (M6 eval wiring) is where they get caught.
- Fixtures under tests/qa/fixtures/geometry/ are referenced in-place by the
  new regression tests (skipif-guarded); committing them with the manifest
  remains an M4 deliverable.
