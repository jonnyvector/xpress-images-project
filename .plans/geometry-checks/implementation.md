# geometry-checks — Implementation Plan

## ⚠️ Execution Protocol

A progress report exists at `.plans/geometry-checks/progress-report.md`. It
lists every feature for every milestone as a checkbox.

**Mandatory rules for all agents working on this plan:**

1. Before starting a milestone, run `plan-db check-progress --plan
   "geometry-checks"` and read its section in the progress report — those
   current-cutoff checkboxes are your spec
2. Check each box as you complete the feature, not at the end
3. A milestone is NOT done until every current-cutoff checkbox under it is
   checked
4. If you find features missing from the report, add them first
5. Never declare a phase complete without updating the current focus marker
   and Summary
6. Deferred follow-up and superseded/obsolete checklist debt must not be
   counted as current blockers

## Architecture

The geometry-checks feature extends the existing `backend/qa/` judgment
pipeline with two additions specified in RFC-01 v2
(`.plans/geometry-checks/01_deterministic-geometry-checks-for-the-judgment-pipeline.rfc.md`):

1. <!-- D-002 --> **Replica-anchor workflow (D1)** — pure policy change:
   replica candidates route to `needs_human` unless label-approved, making
   the human-approved replica the geometry reference for its variants.
2. <!-- D-002 --> **Deterministic measurement module (D2/D3)** —
   `backend/qa/geometry.py`, numpy + Pillow only, running ONLY on
   measurable style classes, comparing candidates against sample and/or
   replica as structural ratios at full working resolution
   (min(native, 1536)px, sub-pixel peak localization), producing
   confidence-qualified `GeometryReport`s.

Data flow (additions in caps):

```
corpus.Candidate ──► STYLE ROUTER ──► geometry.measure() ──► GeometryReport ─┐
        │                 │ (excluded class → None)                          │
        │                 ▼                                                  ▼
        └──► judge.VisionJudge ──► JudgeResult ──────────────► policy.decide(result,
                                                                candidate, config,
                                                                GEOMETRY=report)
                                                                     │
                                              pass / regenerate / needs_human
```

### Key Constraints

| Constraint | Impact |
|-----------|--------|
| No new dependencies (numpy, Pillow only) | OpenCV only via OQ-1 escape hatch after Phase 2 data |
| `output/.projects/` strictly read-only | Fixtures are working copies under `tests/qa/fixtures/` |
| Ruff line 100, rules E,F,I,UP,B,SIM, py312 | Same as parent pipeline |
| Fail-safe invariant | No geometry path may silently pass; excluded classes yield `None` (judge-only), failures yield `unmeasurable` → needs_human |
| Threshold split discipline (D6) | Selection split ≠ gate fixtures ≠ holdout; holdout run once, shortfall blocks acceptance |
| Existing 35 QA tests must stay green | Additive changes only to policy/eval surfaces |

### Boundaries

- `backend/qa/geometry.py` — NEW. Owns everything from image bytes to
  `GeometryReport`. No knowledge of policy, judge, eval, or labels. Module
  comment: "Deterministic structural measurement of framed cabinet doors;
  compares candidate vs reference as scale-invariant ratios; fail-safe:
  every failure is `unmeasurable`, never an exception or silent pass."
- `backend/qa/policy.py` — MODIFIED. Gains `replica_review` flag, nested
  `geometry` config parsing, `geometry:` param in `decide()` with the
  RFC-01 v2 §D4 ten-step precedence. Owns verdict composition only.
- `scripts/qa_eval.py` — MODIFIED. Style routing, geometry cache
  (`output/.qa/geometry/<config-hash>/<key>.json`), attribution metrics.
- `backend/qa/styles_classes.py` — NEW, tiny. Maps door_style keys →
  measurable/excluded class + style-class name (from
  `backend/styles/catalog.py` keys). Kept separate so policy and eval share
  one routing truth. Module comment required.
- `backend/qa/judge.py`, `corpus.py`, `labels.py`, `thumbs.py` — untouched.

### Contracts (normative, consolidated from RFC-01 v2)

```python
@dataclass
class GeometryConfig:
    measurable_styles: list[str]
    working_width: int = 1536              # min(native, this)
    drift_thresholds: dict[str, float]     # per style-class
    aspect_threshold: float = 0.04
    min_box_fraction: float = 0.40
    min_peak_prominence: float = 0.15
    max_match_residual: float = 0.02

@dataclass
class GeometryReport:
    key: str
    status: str        # "ok" | "drift" | "unmeasurable"
    confidence: str    # "high" | "low"
    reference: str     # "sample" | "replica"
    aspect_delta: float
    stile_deltas: dict[str, float]
    rail_deltas: dict[str, float]
    boundary_deltas: list[float]
    unmatched_boundaries: int
    max_delta: float
    detail: str

def measure(reference_path: Path, candidate_path: Path, key: str,
            config: GeometryConfig, style_class: str) -> GeometryReport
```

**Verdict rules:** `drift` iff `max_delta` > class threshold OR
`aspect_delta` > `aspect_threshold` OR `unmatched_boundaries` > 0 with high
confidence. Confidence `high` only when box checks passed in both images,
mean match residual ≤ `max_match_residual`, and boundary counts agree
within one. Partial measurement (GEO-003) forces `low` confidence.

**Decision precedence (`decide(result, candidate, config,
geometry=None, approved_keys=frozenset(), replica_approved=True)`):**

<!-- D-010 --> Reshaped after the M4 spike (A-001/A-002 failed as stated):

1. Untrusted style → needs_human
2. No sample photo → needs_human
3. Replica + `replica_review` and key not in approved_keys → needs_human
   ("replica review: geometry anchor")
4. Variant + `transitive_replica_review` and its replica not approved →
   needs_human ("replica not approved") — production semantics: variants
   of an unapproved replica never ship; false-flag impact measured in M6
5. Judge error → needs_human
6. Judge fail / low scores → regenerate
7. Geometry drift, high confidence, reference=replica → regenerate
   (names worst measurement) — the render-vs-render hard gate
8. Geometry drift, reference=sample (any confidence) → needs_human —
   photo comparison is advisory (A-001: only 27% high-confidence)
9. Geometry drift, low confidence → needs_human
10. Geometry unmeasurable (measurable class only) → needs_human
11. Judge low confidence → needs_human
12. Pass

`geometry=None` (excluded class / no reference / disabled) MUST leave
pre-geometry behavior byte-identical. Judge-fail beats unmeasurable
(step 5 before 8): confidently bad → regenerate, not human.

**Error codes:** GEO-001 unreadable image → unmeasurable; GEO-002 box
confidence fail → unmeasurable; GEO-003 no interior boundaries → partial
measurement, low confidence, or unmeasurable if aspect+frame also
unavailable; GEO-004 any exception at `measure()` boundary → unmeasurable.
No geometry path may silently pass or raise.

**Dual reference (D3, reshaped per D-010):** replicas measured vs sample
(ADVISORY — informs human review, never auto-regenerates); variants vs
replica (PRIMARY hard gate) with vs-sample as advisory backstop.
`PolicyConfig` gains `transitive_replica_review: bool = True`.

### Observability

- Every `GeometryReport` carries `detail` (human-readable) and full deltas;
  eval persists reports in the geometry cache (inspectable JSON per key).
- `scripts/qa_eval.py` prints per-style attribution: geometry-only catches,
  geometry-added false flags, replica-review load, excluded-class counts —
  the operator can always answer "which gate fired and why" from the run
  output plus cached artifacts.
- Phase 0 produces a mechanism table checked into the plan directory —
  the permanent record of what the misses actually were.

---

## Assumptions

| Code | Assumption | Status | Impact if False |
|------|-----------|--------|-----------------|
| A-001 | Sample photos are near-frontal/clean enough for high-confidence box+profile measurement on ≥80% of measurable-class samples | untested | Replica-vs-sample demoted to low-confidence-only; OQ-1 (OpenCV) decided with data |
| A-002 | Labeled variant geometry rejects separate from matched accepts via structural-ratio deltas at per-class thresholds | untested | Module scope shrinks to boundary-count/aspect checks; recall target renegotiated |

---

## Phases

### Phase 0: Mechanism decomposition (no code)

**Goal:** The addressable-by-measurement subset of the 17 missed
geometry-tagged rejects is explicitly known before any code exists.

**Gate from previous:** RFC-01 v2 accepted.

#### M0: Classify the misses

- **Dependencies:** none
- **Effort:** S
- **Tasks:**
  1. Export side-by-side working copies of all 17 missed pairs (reuse
     `export_thumb`, max_px=1024) into `.plans/geometry-checks/misses/`.
  2. Classify each by mechanism (aspect | frame-width | panel-position |
     boundary-count | profile/non-metric) and reference case
     (replica-vs-sample | variant-vs-replica). Vision inspection; record
     table to `.plans/geometry-checks/phase0-mechanisms.md`.
  3. Record counts as plan-db decision; if metric-addressable subset < 60%
     of misses, STOP and surface to Jonathan before Phase 1.

### Gate 0→1

- [ ] phase0-mechanisms.md exists with all 17 classified
- [ ] Addressable subset ≥ 60% OR explicit Jonathan sign-off to proceed

### Phase 1: Replica-anchor policy (D1)

**Goal:** Replica candidates route to human review unless label-approved;
eval reports replica-review load; the dominant miss class is closed by
process.

#### M1: replica_review policy flag

- **Dependencies:** M0
- **Effort:** S
- **Tasks:**
  1. RED: test — replica candidate + passing JudgeResult +
     `replica_review=True` + no accept label → `needs_human`, reason
     "replica review: geometry anchor".
  2. RED: test — same replica WITH accept label in provided approved-keys
     set → falls through to normal precedence (pass).
  3. RED: test — `replica_review=False` → unchanged v1 behavior.
  4. GREEN: extend `PolicyConfig` (`replica_review: bool = True`),
     `load_policy()`, and `decide(..., approved_keys: frozenset[str] =
     frozenset())` inserting step 3 of the RFC-01 v2 §D4 precedence.
  5. RED: eval-side test — metrics/attribution include replica-review load;
     labeled-accept replicas are treated as approved (not false flags).
  6. GREEN: `scripts/qa_eval.py` builds `approved_keys` from accept labels;
     eval output line added.
  7. REFACTOR: ensure all 35 existing tests green; ruff clean; commit.

### Gate 1→2

- [ ] Cached-verdict re-eval shows every replica miss routed needs_human
- [ ] Replica review load reported separately from false flags
- [ ] Existing tests green

### Phase 2: Measurement core + real-fixture spike (D2, D6, A-001, A-002)

**Goal:** `geometry.py` measures synthetic doors to ±0.005 under noise and
detects ≥4/5 real variant-miss fixtures with zero high-confidence false
drifts on matched accepts; A-001/A-002 validated or failed with data.

#### M2: Style-class router

- **Dependencies:** M0
- **Effort:** S
- **Tasks:**
  1. RED: tests — known catalog keys map to expected class
     (`shaker`→frame_standard measurable; `skinny_shaker`→frame_narrow;
     `bevel_slab`/`louver`/`raised_panel_radius`→excluded; unknown style →
     excluded (fail-safe)).
  2. GREEN: `backend/qa/styles_classes.py` with explicit dict + module
     comment; classes: `frame_standard`, `frame_narrow`, `excluded`.
  3. REFACTOR: lint, commit.

#### M3: Synthetic measurement core

- **Dependencies:** M2
- **Effort:** L
- **Tasks:**
  1. RED: synthetic fixture builder (Pillow: door renders with exact
     stile/rail/panel ratios + grain-noise overlay + JPEG re-encode) and
     test: `measure()` recovers ratios within ±0.005 at high confidence.
  2. GREEN: implement load/grayscale at min(native,1536), Sobel gradients,
     box detection with confidence checks (min_box_fraction, margin
     variance, aspect sanity), profiles, two-scale peak persistence,
     sub-pixel parabolic refinement, measurements.
  3. RED: distortion tests — 2% and 3% stile/rail widening, panel shift,
     added center boundary → `drift` with correct worst-measurement in
     detail; unmatched boundary counted, not folded into max_delta.
  4. GREEN: order-preserving DP boundary matching + verdict + confidence
     rules per RFC-01 v2 §D2 step 6.
  5. RED: failure-path tests — unreadable file → unmeasurable GEO-001;
     busy-background image failing box checks → unmeasurable GEO-002;
     no interior peaks → partial measurement, low confidence (GEO-003);
     injected exception → unmeasurable GEO-004, never raises.
  6. GREEN: boundary try/except + graduated GEO-003 path.
  7. REFACTOR: benchmark (informational) per-pair time at 1536px; lint;
     commit.

#### M4: Real-fixture spike (A-001, A-002)

- **Dependencies:** M3
- **Effort:** M
- **Tasks:**
  1. Export fixture working copies: 17 missed pairs + style-matched accept
     pairs (from labels) into `tests/qa/fixtures/geometry/` with a
     manifest.json (key, style_class, label, reference case).
  2. Run `measure()` across all fixtures; write results table to
     `.plans/geometry-checks/phase2-spike.md`.
  3. Validate A-001: high-confidence rate on measurable-class
     replica-vs-sample fixtures ≥80% → `plan-db validate-assumption A-001`.
  4. Validate A-002: selection-split threshold sweep separates variant
     rejects from accepts → `plan-db validate-assumption A-002`.
  5. Acceptance test (committed): ≥4/5 variant-miss fixtures detected,
     zero high-confidence false drifts on accept fixtures.
  6. If either assumption fails: STOP, record fail with evidence, regress
     stage to decompose, surface OQ-1 to Jonathan.

### Gate 2→3

- [ ] Synthetic accuracy ±0.005 under grain+JPEG noise
- [ ] A-001 and A-002 recorded pass (or plan regressed)
- [ ] Real-fixture acceptance test green at committed thresholds

### Phase 3: Policy + eval integration (D4, D5)

**Goal:** Geometry verdicts compose into decisions with full attribution in
eval output; caching mirrors the judge pattern.

#### M5: Policy composition

- **Dependencies:** M4
- **Effort:** M
- **Tasks:**
  1. RED: precedence tests — high-confidence drift overrides passing judge
     → regenerate; low-confidence drift → needs_human; unmeasurable →
     needs_human; judge-fail + unmeasurable → regenerate (asymmetry);
     `geometry=None` → v1 behavior byte-identical.
  2. GREEN: `decide(..., geometry: GeometryReport | None = None)` with
     RFC-01 v2 §D4 ten-step precedence; `PolicyConfig.geometry:
     GeometryConfig | None` parsing.
  3. REFACTOR: policy_config.json gains nested geometry object with
     per-class thresholds; lint; commit.

#### M6: Eval wiring + cache + attribution

- **Dependencies:** M5
- **Effort:** M
- **Tasks:**
  1. RED: cache test — geometry results cached under
     `output/.qa/geometry/<config-hash>/<key>.json`; config change busts
     cache; unmeasurable results NOT cached (mirror judge error rule).
  2. GREEN: cache layer (extract shared helper only if trivially reusable
     from judge.py — no premature abstraction).
  3. RED: attribution test — synthetic decisions produce metrics lines:
     geometry-only catches, geometry-added false flags, excluded-class
     count, replica load.
  4. GREEN: qa_eval.py routing (style class → reference selection →
     measure → decide) + metrics output.
  5. REFACTOR: full train-split eval smoke run; lint; commit.

### Gate 3→4

- [ ] Full train-split eval runs clean with attribution
- [ ] All prior tests green (35 + new)

### Phase 4: Threshold calibration + acceptance

**Goal:** Frozen thresholds; honest holdout verdict on the combined
pipeline.

#### M7: Calibration + holdout

- **Dependencies:** M6
- **Effort:** S
- **Tasks:**
  1. Sweep per-class thresholds on the selection split (train-split labels
     excluding gate fixtures); record chosen values + curves to
     `.plans/geometry-checks/phase4-calibration.md`; commit values to
     policy_config.json.
  2. Freeze. Run `uv run python scripts/qa_eval.py --holdout` ONCE.
  3. Gate (MUST): combined reject recall ≥95% AND false-flag ≤20% on
     holdout, replica-review load reported. Pass → record decision, plan
     complete. Fail → record shortfall with per-reason attribution,
     regress to decompose, surface to Jonathan. NO holdout re-runs, NO
     post-hoc threshold changes.

### Gate 4→done

- [ ] Holdout verdict recorded (pass, or documented shortfall + regression)
- [ ] All docs/config committed; progress report normalized

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation | Owner |
|------|----------|------------|------------|-------|
| A-001 fails (photos unmeasurable) | high | medium | Phase 2 spike before integration; escape hatch 1 | agent |
| A-002 fails (drift not metric) | high | medium | Phase 0 decomposition first; escape hatch 2 | agent |
| Grain defeats peak persistence | medium | medium | Two-scale persistence + synthetic grain gates in M3 | agent |
| Combined false flags exceed 20% | high | medium | Confidence-gated override; per-class thresholds; attribution makes source visible | agent |
| Replica review adds unwanted human load | low | low | ~1/project; flag can be disabled; load reported | Jonathan |
| n-small overfitting | medium | high | Selection/gate/holdout split discipline; holdout blocks acceptance | agent |

---

## Escape Hatches

1. **If A-001 fails (Gate 2→3):** replica-vs-sample measurement demoted to
   low-confidence-only; D1 replica human review carries that class alone;
   decide OQ-1 (OpenCV homography) with the spike data in front of
   Jonathan.
2. **If A-002 fails:** shrink module scope to aspect + boundary-count
   checks (cheap, robust), renegotiate the recall target against the
   Phase 0 mechanism table, and lean on judge prompt iteration for the
   profile-shaped remainder.
3. **If Phase 4 holdout fails:** no threshold tweaking; regress to
   decompose with per-reason attribution and decide between OpenCV,
   more labels, or accepting a pre-sort (non-gating) role for the module.

---

## Progress Report Accounting

The progress report is the implementation resume state. Normalized
accounting per the planner invariants; before resuming implementation or
declaring convergence run:

```bash
npx tsx <skill-dir>/scripts/plan-db.ts check-progress --plan "geometry-checks"
```

---

## Validation Commands

```bash
uv run pytest tests/qa -v                 # full QA suite (35 existing + new)
uv run ruff check backend/qa scripts tests/qa
uv run python scripts/qa_eval.py          # train-split eval with attribution
uv run python scripts/qa_eval.py --holdout  # Phase 4, ONCE
```

---

## Decisions

Canonical decisions are in `.plans/geometry-checks/plan.db`. Query:

```bash
npx tsx <skill-dir>/scripts/plan-db.ts query-decisions --plan "geometry-checks"
```

Key markers: <!-- D-002 --> v2 restructure (replica anchor, class routing,
confidence gating, split discipline); <!-- D-003 --> corrected arithmetic
(43/21/22 train rejects; 17 missed geometry-tagged, 12 replica / 5
variant); <!-- D-004 --> consistency fixes (GeometryConfig, aspect wiring,
state-machine completeness, cache hash path).
