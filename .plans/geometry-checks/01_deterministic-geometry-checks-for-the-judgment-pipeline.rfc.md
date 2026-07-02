---
number: 01
title: "Deterministic Geometry Checks for the Judgment Pipeline"
type: feature
status: Draft
author: Jonathan Hicks / Claude
date: 2026-07-02
---

# RFC-01: Deterministic Geometry Checks for the Judgment Pipeline (v2)

> v2 incorporates the three-agent review of v1 (consistency, codebase
> alignment, adversarial) and empirical inspection of the actual missed
> rejects. Major changes: style-class routing, confidence-gated override,
> replica-anchor workflow, render-vs-render variant checks, per-class
> thresholds, and corrected arithmetic throughout.

## Abstract

The judgment pipeline's LLM vision judge misses roughly half of
human-labeled rejects; the dominant gap is `geometry_drift` (4 of 19 caught
on the train split). Inspection of the misses shows 12 of 17 are replicas
drifting from the sample photo and 5 are variants drifting from their
replica. This RFC specifies (a) a **replica-anchor workflow** — replicas
route to human review by default, closing the largest miss class by process
rather than code — and (b) a deterministic geometry-measurement module
(`backend/qa/geometry.py`) that runs only on rectangular framed door styles,
measures structural ratios at full working resolution, compares candidates
against both the sample photo and the approved replica, and feeds
confidence-qualified verdicts into the existing decision policy. All
thresholds are calibration outputs tuned by the existing eval harness on a
proper train/selection split.

## Introduction

**Problem.** The full-train eval (train split n=146 labels, 43 rejects; judge
config `812b52bc6ea6`, model `gemini-3.1-pro-preview`) measured reject
recall 48.8% (21 caught, 22 missed) and `geometry_drift` recall 4/19.
Missed rejects reach Shopify as product photos of doors the shop cannot
deliver. The judgment-pipeline spec (§4) explicitly gated this module on
that evidence.

**Empirical grounding (new in v2).** Direct inspection of the missed
geometry-tagged rejects (17 with cached judge verdicts): 12 replicas, 5
variants. Sample photos in this corpus are clean, near-frontal catalog-style
shots on neutral backgrounds — not adversarial customer snapshots. Observed
drift in inspected pairs is of the measurable kind: door aspect-ratio
changes and frame-width-ratio changes visible as clean structural
differences.

**Scope — in.** Replica-anchor routing in policy; a geometry measurement
module for framed rectangular styles; dual comparison (candidate-vs-sample
and variant-vs-replica); confidence-qualified verdicts; integration into
`backend/qa/policy.py` and `scripts/qa_eval.py`; per-style-class thresholds
calibrated on a selection split; fixtures from the real missed rejects.

**Scope — out.** No LLM judge prompt changes (separate track). No
regeneration loop or bulk orchestration (phase 2 of the parent project). No
Shopify export. No geometry attempt on excluded style classes (slab, plank,
louver, arched/radius, mitered-joint-specific checks) — the judge remains
the sole automated gate there. No material/color analysis.

## Terminology

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD
NOT, RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted
as described in RFC 2119.

- **Sample**: the uploaded reference photo of the real door (`upload.bin`).
- **Replica**: the generated base door image (`base_door.bin`) whose learned
  signature anchors all variants of a project.
- **Candidate**: any generated image under judgment (replica or variant).
- **Measurable class**: door styles with an axis-aligned rectangular frame
  (shaker families, recessed/raised rectangular panel, center-stile,
  drawer-front framed equivalents). Enumerated in config; derived from
  `backend/styles/catalog.py`.
- **Excluded class**: styles the measurement model does not fit — slab/bevel
  (no frame), solid plank, louver, radius/arched, glass/mullion. Geometry is
  not attempted; no geometry verdict exists for these.
- **Door box**: axis-aligned bounding box of the door face after background
  separation.
- **Edge-energy profile**: 1-D signal of summed gradient magnitude along
  rows/columns inside the door box.
- **Structural ratio**: a measurement expressed as a fraction of door-box
  width or height (scale-invariant).
- **Geometry delta**: absolute difference between the same structural ratio
  in two images.
- **Measurement confidence**: `high` or `low`, from explicit checks (box
  margin quality, peak prominence, boundary-match residuals).
- **Geometry verdict**: `ok`, `drift`, or `unmeasurable` — only produced for
  measurable-class candidates.
- **False flag**: a human-labeled accept that policy routes to `regenerate`
  or `needs_human`. (Matches `EvalMetrics.false_flag_rate` in
  `backend/qa/eval.py`.)

## Motivation

Calibration data exists (179 labels, 50 rejects as of 2026-07-02; the
triggering eval snapshot was train n=146 with 43 rejects), the eval harness measures
any change in minutes, and geometry misses dominate the recall gap: 15 of
the 22 train-split misses carry the `geometry_drift` tag (some also carry
`profile_character`; reason buckets overlap and MUST NOT be summed).
Replica misses compound downstream — every variant generated from a drifted
replica inherits its geometry — which is why 12 of 17 inspected geometry
misses being replicas makes the replica-anchor workflow the single
highest-leverage change available, at near-zero engineering cost. The
measurement module then guards the remaining variant-drift class at zero
API cost per image.

## Design

### D1. Replica-anchor workflow (policy change, no new module)

`decide()` routes every **replica** candidate to `needs_human` with reason
"replica review: geometry anchor" unless the replica already carries an
accept label in the label store. Rationale: one replica per project
(~seconds of human time), eliminates the dominant miss class (12/17), and
an approved replica becomes a trustworthy geometry reference for hundreds
of variants. This routing MUST be a config flag (`replica_review`, default
`true`) so phase-2 orchestration can later integrate an approval queue.
Eval output MUST report replica-review load (count routed) separately from
false flags so the cost of this policy is visible, and the eval MUST treat
a labeled-accept replica as approved (not a false flag).

### D2. Geometry module: `backend/qa/geometry.py`

```python
@dataclass
class GeometryConfig:
    measurable_styles: list[str]      # style keys geometry runs on
    working_width: int = 1536         # min(native, this); no destructive downscale
    drift_thresholds: dict[str, float]   # per style-class, e.g. {"frame_standard": 0.03,
                                         #  "frame_narrow": 0.015}
    aspect_threshold: float = 0.04
    min_box_fraction: float = 0.40    # box must cover >= this of frame area
    min_peak_prominence: float = 0.15 # relative prominence for a boundary peak
    max_match_residual: float = 0.02  # mean matched-boundary residual gate

@dataclass
class GeometryReport:
    key: str
    status: str                    # "ok" | "drift" | "unmeasurable"
    confidence: str                # "high" | "low"
    reference: str                 # "sample" | "replica"
    aspect_delta: float
    stile_deltas: dict[str, float] # "left"/"right"
    rail_deltas: dict[str, float]  # "top"/"bottom"
    boundary_deltas: list[float]
    unmatched_boundaries: int      # strong peaks present in one image only
    max_delta: float
    detail: str

def measure(reference_path: Path, candidate_path: Path, key: str,
            config: GeometryConfig, style_class: str) -> GeometryReport
```

Pipeline (numpy + Pillow; OpenCV remains OQ-1, decided by Phase 2 data):

1. **Load + grayscale** at `min(native_width, working_width)` — the v1
   768px downscale is removed because the target signal (1–3% of a stile
   that is itself 5–10% of door width) sits near the pixel scale;
   measurement MUST use sub-pixel peak localization (parabolic
   interpolation around profile peaks).
2. **Door-box detection** with explicit confidence: gradient magnitude
   (Sobel), sustained-run row/column extents, plus checks — box area ≥
   `min_box_fraction` of frame, near-white or low-variance margin outside
   the box (renders), plausible aspect (0.2–5.0). Failing checks →
   `unmeasurable` (never a silent wrong frame).
3. **Profiles + peaks** with prominence threshold; sub-pixel refinement;
   grain-noise suppression by comparing peak persistence across two
   independent smoothing scales (a real frame boundary persists; grain
   streaks decorrelate). Peaks that fail persistence are dropped.
4. **Structural measurements**: aspect ratio; left/right stile and
   top/bottom rail width ratios; interior boundary position fractions.
5. **Compare** against the reference boundary set: monotonic
   order-preserving matching (dynamic programming, not nearest-neighbor —
   one spurious peak MUST NOT cascade), with unmatched strong peaks counted
   in `unmatched_boundaries` rather than folded into `max_delta`.
6. **Verdict + confidence.**
   - `drift` if `max_delta` > class threshold OR `aspect_delta` >
     `aspect_threshold` OR `unmatched_boundaries` > 0 with high confidence.
   - Confidence is `high` only when box checks passed in both images, mean
     match residual ≤ `max_match_residual`, and boundary counts agree
     within one.
   - `unmeasurable` when box/profile extraction fails on a
     measurable-class input.

### D3. Dual reference

- **Replica candidates** are measured against the **sample** (photo vs
  render — the harder case, mitigated by the clean-catalog nature of this
  corpus, validated as A-001).
- **Variant candidates** are measured against the **replica**
  (render vs render — clean, alignment-free) AND against the sample when
  available; the replica comparison is primary (tighter thresholds MAY
  apply), the sample comparison is a backstop. Under D1, variants are
  normally judged only after their replica is human-approved, so the
  replica reference is trustworthy.

### D4. Decision policy integration (`backend/qa/policy.py`)

`decide()` gains `geometry: GeometryReport | None = None`. `None` means
geometry was not attempted (excluded class, missing reference, or feature
disabled) and MUST leave existing behavior unchanged. Precedence:

1. Untrusted style → `needs_human` (unchanged)
2. No sample photo → `needs_human` (unchanged)
3. **Replica + `replica_review` and not label-approved → `needs_human`** (D1)
4. Judge error → `needs_human` (unchanged)
5. Judge fail / low scores → `regenerate` (unchanged)
6. **Geometry `drift` with `high` confidence → `regenerate`**, reason names
   the worst measurement. This override of a passing judge is the module's
   purpose, but it MUST require high measurement confidence.
7. **Geometry `drift` with `low` confidence → `needs_human`.**
8. **Geometry `unmeasurable` (measurable class only) → `needs_human`.**
9. Judge low confidence → `needs_human` (unchanged)
10. Pass.

`PolicyConfig` gains `replica_review: bool` and a `geometry:
GeometryConfig | None` field; `load_policy()` parses the nested `geometry`
object from `policy_config.json` (absent → geometry disabled).

### D5. Eval integration (`scripts/qa_eval.py`)

For each labeled candidate: resolve style class; if measurable and a
reference exists, run `measure()` with results cached to
`output/.qa/geometry/<config-hash>/<key>.json` (config-hash subdirectory,
exactly mirroring the judge cache pattern in `judge.py`). Pass the report
into `decide()`. Metrics output gains: geometry attribution per style
(rejects caught by geometry alone, geometry-added false flags), replica
review load (D1), and counts of excluded-class candidates (geometry not
attempted) so coverage is never silently overstated.

### D6. Fixtures and tests

- Synthetic fixtures (Pillow-rendered doors with exact known ratios):
  accuracy ±0.005 at high confidence **including additive grain-texture
  noise and JPEG re-encoding**, not clean rectangles only; injected 2% and
  3% stile/rail distortions and panel shifts MUST be detected at
  class-appropriate thresholds.
- Real fixtures: export the 17 missed geometry-tagged rejects (12 replica,
  5 variant) plus style-matched accepts into `tests/qa/fixtures/geometry/`
  as working copies (originals in `output/.projects/` are never touched).
- **Split discipline:** threshold *selection* MUST use a selection split of
  the labeled data disjoint from the gate fixtures; the project holdout
  split (`is_holdout`) is run once at Phase 4 and its result gates
  acceptance (see Implementation Plan). Fitting thresholds on the gate set
  is the failure mode this bullet exists to prohibit.

## State Machine

Per-candidate geometry evaluation (measurable classes only):

```
ROUTED        → LOADED        (on: style in measurable_styles and reference exists)
ROUTED        → NOT_ATTEMPTED (on: excluded class | no reference)          [terminal]
LOADED        → BOXED         (on: door-box checks pass in both images)
LOADED        → UNMEASURABLE  (on: decode failure | box confidence fail)   [terminal]
BOXED         → MEASURED      (on: profiles extracted; full or partial per GEO-003)
BOXED         → UNMEASURABLE  (on: no usable profiles in either image)     [terminal]
MEASURED      → OK            (on: all deltas within thresholds)           [terminal]
MEASURED      → DRIFT         (on: any threshold exceeded)                 [terminal]
MEASURED      → UNMEASURABLE  (on: exception during compare/verdict)       [terminal]
```

`NOT_ATTEMPTED` yields no `GeometryReport` (policy receives `None`).
Partial measurement (GEO-003) reaches MEASURED with the reduced measurement
set and forces `confidence="low"`. All exceptions anywhere inside
`measure()` are caught at its boundary and produce `UNMEASURABLE` with the
exception text in `detail` — including post-MEASURED comparison errors, per
the explicit `MEASURED → UNMEASURABLE` transition. Measurement is
synchronous local compute; no timeout states. (Performance is expected
around a second per pair at 1536px; Phase 1 includes a benchmark, and the
figure is informational, not normative.)

## Error Handling

- `GEO-001` unreadable/undecodable image (warning). Recovery:
  `unmeasurable` → policy step 8. Never raises out of `measure()`.
- `GEO-002` door-box confidence failure (info). Recovery: `unmeasurable`,
  detail names which image and which check failed.
- `GEO-003` no interior boundaries found in either image (info). Recovery:
  proceed with aspect + stile/rail measurements only, `confidence="low"`;
  if those are also unavailable → `unmeasurable`.
- `GEO-004` exception during measurement or comparison (warning). Recovery:
  caught at the `measure()` boundary → `unmeasurable`, exception text in
  `detail`.
- Fail-safe invariant: no geometry code path may cause a silent pass. Every
  failure resolves to `unmeasurable` (→ `needs_human` via policy step 8) or
  is absent entirely (`NOT_ATTEMPTED` → existing judge-only behavior).
  Note the deliberate asymmetry with judge failures: a judge-fail verdict at
  policy step 5 still resolves to `regenerate` even if geometry was
  unmeasurable — a confidently bad image goes back to generation, not to a
  human.

## Security Considerations

- **Trust boundaries.** Inputs are app-produced local files
  (`output/.projects/`, read-only). No network calls, no credentials.
- **Input validation.** Pillow decoding with failures caught (GEO-001);
  Pillow's default `MAX_IMAGE_PIXELS` decompression-bomb limit MUST remain
  enabled.
- **Blast radius.** Worst case is a wrong verdict. Fail-open (silent pass)
  is designed out per the fail-safe invariant; fail-noisy costs are bounded
  by policy routing (`needs_human`) and are visible in eval attribution
  (D5). Writes are confined to `output/.qa/`.
- **Data sensitivity.** Product images only; no PII, no secrets.

## Alternatives Considered

1. **OpenCV homography + SSIM.** Robust to perspective; heavyweight
   dependency against project policy. v2's clean-corpus evidence weakens
   the case for it further, but it remains the designated fallback if
   A-001 fails in Phase 2 (OQ-1).
2. **Judge prompt iteration as the primary fix.** Rejected as primary: the
   failure is perceptual (small metric changes), and 12/17 misses are
   addressed by D1 process routing anyway. Prompt iteration continues as a
   separate track targeting the false-flag rate.
3. **Fine-tuned vision model.** Rejected: ~50 rejects is far too little
   training data; cost unjustified against classical measurement.
4. **Nearest-neighbor boundary matching (v1).** Rejected in favor of
   order-preserving DP matching: one spurious grain peak must not cascade
   mismatches (review finding).
5. **Global single threshold (v1).** Rejected: a 0.03 ratio delta is more
   than half the stile on skinny-shaker styles and inside measurement noise
   on high-grain styles. Per-style-class thresholds replace it.
6. **Geometry for all styles with `unmeasurable → needs_human` (v1).**
   Rejected: floods human review with structurally unmeasurable classes
   (slab, louver, arched). Replaced by explicit class routing
   (`NOT_ATTEMPTED`).

## Implementation Plan

- **Phase 0 — Mechanism decomposition (no code).** Classify all 17 missed
  geometry rejects by drift mechanism (aspect, frame widths, panel
  position, boundary count, non-metric/profile) and by reference case
  (replica-vs-sample / variant-vs-replica). Output: a table in the plan
  directory. Gate: the addressable-by-measurement subset is explicitly
  known before any code exists; if it is under 60% of misses, revisit
  scope with Jonathan before Phase 1.
- **Phase 1 — Replica-anchor policy (D1) + eval attribution.** Small,
  independent of the measurement module; ships first. Gate: eval shows
  replica routing catching the replica-miss class; replica review load
  reported; existing tests green.
- **Phase 2 — Measurement core + real-fixture spike.** `geometry.py` with
  synthetic tests (D6), then run against the real fixture set. Validates
  A-001 (sample photos measurable with high confidence ≥80% of measurable
  attempts) and A-002 (see Open Questions → now defined in Spike
  assumptions below). Gate: on the variant-miss fixtures (render vs
  render), ≥4/5 detected at selection-split-chosen thresholds with zero
  false drifts on matched accept fixtures at high confidence; on
  replica-vs-sample fixtures, measured confidence rate reported. Gate fail
  → regress to design, decide OQ-1 with data.
- **Phase 3 — Policy + eval integration (D4, D5)** with caching and
  attribution. Gate: full train-split eval runs clean; per-style
  attribution present; no regression in existing tests.
- **Phase 4 — Threshold calibration + acceptance.** Select thresholds on
  the selection split; freeze; run the `is_holdout` split ONCE. Gate
  (MUST): combined pipeline (D1 routing + judge + geometry) reject recall
  ≥95% on holdout rejects and false-flag rate ≤20% on holdout accepts,
  with replica-review load reported alongside. A holdout shortfall MUST
  block acceptance and return the plan to design — it MUST NOT be resolved
  by re-running holdout or adjusting thresholds post-hoc.

**Spike assumptions:**
- **A-001**: sample photos in this corpus are near-frontal and
  clean-background enough that door-box detection + profile measurement
  reaches high confidence on ≥80% of measurable-class samples. Impact if
  false: replica-vs-sample comparison demoted to low-confidence-only
  (needs_human), OQ-1 (OpenCV) decided.
- **A-002**: structural-ratio deltas measured at working resolution
  separate the labeled variant geometry rejects from matched accepts with
  a per-class threshold — i.e., the drift humans labeled is metric, not
  purely profile-shaped. Impact if false: the measurement module's scope
  shrinks to boundary-count/aspect checks and the recall target is
  re-negotiated with the label evidence in hand.

## Open Questions

1. **OQ-1: OpenCV (opencv-python-headless) as fallback dependency** if
   A-001 fails. Options: (a) numpy-only with demoted photo comparisons;
   (b) admit OpenCV for homography alignment. Needed: Phase 2 data.
   Decider: Jonathan.
2. **OQ-2: Unmatched strong boundary (extra/missing panel line).** v2
   default: `drift` when measurement confidence is high, `needs_human`
   when low (encoded in D2 verdict rules). Confirm against Phase 0
   decomposition. Decider: Phase 0 data + Jonathan on ties.
3. **OQ-3: Replica approval persistence.** D1 treats a labeled accept as
   approval; phase-2 orchestration will need a first-class approval store.
   Out of scope here — flag for the bulk-orchestration plan. Decider:
   deferred.

## References

- **Normative:**
  - `docs/superpowers/specs/2026-07-02-judgment-pipeline-design.md` §4 —
    parent mandate and conditional gate.
  - `backend/qa/policy.py`, `backend/qa/judge.py`, `backend/qa/eval.py`,
    `scripts/qa_eval.py` — integration surfaces.
  - `backend/styles/catalog.py` — style-class enumeration source.
  - `output/.qa/labels.json`, `output/.qa/eval_report.json` — calibration
    ground truth and the triggering eval.
- **Informative:**
  - `docs/superpowers/plans/2026-07-02-judgment-pipeline.md` — parent build.
  - `.plans/geometry-checks/` review findings (plan-db) — v1 → v2 rationale.
