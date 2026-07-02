# geometry-checks — Progress Report

> Auto-generated from implementation plan. This is the canonical source of
> truth for what is done and what remains. Update this file as features are
> implemented — never mark a milestone complete until every current-cutoff
> checkbox under it is checked.

> Current focus: Phase 2 — Measurement core + real-fixture spike

## Phase 0: Mechanism decomposition (no code)

### M0: Classify the misses
Source: `.plans/geometry-checks/implementation.md` (Phase 0), labels at `output/.qa/labels.json`, verdicts at `output/.qa/verdicts/812b52bc6ea6/`

- [x] Feature: side-by-side working copies of all 17 missed pairs exported to `.plans/geometry-checks/misses/` (originals untouched)
- [x] Feature: each miss classified by mechanism (aspect | frame-width | panel-position | boundary-count | profile/non-metric)
- [x] Feature: each miss classified by reference case (replica-vs-sample | variant-vs-replica)
- [x] Feature: `phase0-mechanisms.md` table committed with all 17 rows + addressable-subset percentage
- [x] Feature: counts recorded as plan-db decision; <60% addressable triggers STOP-and-surface to Jonathan

## Phase 1: Replica-anchor policy (D1)

### M1: replica_review policy flag
Source: `backend/qa/policy.py`, `scripts/qa_eval.py`, `backend/qa/policy_config.json`

- [x] Feature: `PolicyConfig.replica_review: bool = True` parsed from policy_config.json
- [x] Feature: `decide()` accepts `approved_keys: frozenset[str]` parameter (default empty)
- [x] Feature: replica + replica_review + not approved → needs_human with reason "replica review: geometry anchor" (test)
- [x] Feature: replica with accept label in approved_keys falls through to normal precedence (test)
- [x] Feature: replica_review=False reproduces pre-D1 behavior exactly (test)
- [x] Feature: qa_eval builds approved_keys from accept labels in the label store
- [x] Feature: eval output reports replica-review load as its own line, excluded from false-flag accounting (test)
- [x] Feature: all 35 pre-existing QA tests green; ruff clean; committed

## Phase 2: Measurement core + real-fixture spike

### M2: Style-class router
Source: `backend/styles/catalog.py`, new `backend/qa/styles_classes.py`

- [ ] Feature: explicit style→class dict covering all catalog keys (frame_standard | frame_narrow | excluded) with module comment
- [ ] Feature: shaker-family keys map to measurable classes; skinny-shaker maps to frame_narrow (test)
- [ ] Feature: slab/bevel, plank, louver, radius/arched, glass styles map to excluded (test)
- [ ] Feature: unknown/None door_style maps to excluded — fail-safe (test)

### M3: Synthetic measurement core
Source: new `backend/qa/geometry.py`, new `tests/qa/test_geometry.py`

- [ ] Feature: synthetic door fixture builder (exact ratios + grain-noise overlay + JPEG re-encode)
- [ ] Feature: load/grayscale at min(native, 1536) working width
- [ ] Feature: door-box detection with confidence checks (min_box_fraction, margin variance, aspect sanity)
- [ ] Feature: edge-energy profiles with two-scale peak persistence (grain suppression)
- [ ] Feature: sub-pixel parabolic peak refinement
- [ ] Feature: ratio recovery within ±0.005 at high confidence on noisy synthetic fixtures (test)
- [ ] Feature: 2% and 3% stile/rail distortions and panel shifts detected as drift with correct worst-measurement detail (test)
- [ ] Feature: order-preserving DP boundary matching; spurious peak does not cascade (test)
- [ ] Feature: unmatched strong boundary counted in unmatched_boundaries, not folded into max_delta (test)
- [ ] Feature: GEO-001 unreadable file → unmeasurable (test)
- [ ] Feature: GEO-002 box-confidence failure → unmeasurable with detail naming image+check (test)
- [ ] Feature: GEO-003 no interior peaks → partial measurement at low confidence (test)
- [ ] Feature: GEO-004 injected exception → unmeasurable, never raises (test)
- [ ] Feature: per-pair timing benchmark recorded (informational)

### M4: Real-fixture spike (A-001, A-002)
Source: `output/.qa/labels.json`, fixtures to `tests/qa/fixtures/geometry/`

- [ ] Feature: fixture working copies exported (17 missed pairs + style-matched accepts) with manifest.json
- [ ] Feature: measure() run across all fixtures; results table in phase2-spike.md
- [ ] Feature: A-001 validated in plan-db (high-confidence rate ≥80% on measurable replica-vs-sample) or failed with evidence
- [ ] Feature: A-002 validated in plan-db (selection-split sweep separates variant rejects from accepts) or failed with evidence
- [ ] Feature: committed acceptance test — ≥4/5 variant-miss fixtures detected, zero high-confidence false drifts on accepts
- [ ] Feature: on assumption failure: stage regressed, OQ-1 surfaced to Jonathan (only if triggered)

## Phase 3: Policy + eval integration

### M5: Policy composition
Source: `backend/qa/policy.py`, `backend/qa/policy_config.json`

- [ ] Feature: `decide(..., geometry: GeometryReport | None)` implements the 10-step precedence
- [ ] Feature: high-confidence drift overrides passing judge → regenerate (test)
- [ ] Feature: low-confidence drift → needs_human (test)
- [ ] Feature: unmeasurable → needs_human (test)
- [ ] Feature: judge-fail + unmeasurable → regenerate — asymmetry preserved (test)
- [ ] Feature: geometry=None leaves pre-geometry behavior byte-identical (test)
- [ ] Feature: PolicyConfig.geometry: GeometryConfig | None parsed from nested policy_config.json object; absent → disabled
- [ ] Feature: policy_config.json committed with per-class thresholds (placeholder values until M7)

### M6: Eval wiring + cache + attribution
Source: `scripts/qa_eval.py`

- [ ] Feature: style routing in eval (class → reference selection → measure)
- [ ] Feature: geometry cache at output/.qa/geometry/<config-hash>/<key>.json (test)
- [ ] Feature: config change busts cache via hash (test)
- [ ] Feature: unmeasurable results not cached — retryable, mirrors judge error rule (test)
- [ ] Feature: metrics output — geometry-only catches, geometry-added false flags, excluded-class counts, replica load (test)
- [ ] Feature: full train-split eval smoke run clean; lint; committed

## Phase 4: Threshold calibration + acceptance

### M7: Calibration + holdout
Source: `scripts/qa_eval.py`, selection split of labels

- [ ] Feature: per-class threshold sweep on selection split; curves + chosen values in phase4-calibration.md
- [ ] Feature: chosen thresholds committed to policy_config.json; frozen
- [ ] Feature: holdout eval run exactly once
- [ ] Feature: holdout verdict recorded — pass (recall ≥95%, false-flag ≤20%) or documented shortfall + stage regression
- [ ] Feature: replica-review load reported alongside holdout metrics

## Deferred follow-up

- [ ] Replica approval store (first-class, beyond label-accept) — deferred to bulk-orchestration plan (OQ-3)
- [ ] Variant-vs-replica consistency as standalone cheap check outside eval — revisit after Phase 4

## Superseded/obsolete checklist debt

(none)

## Summary
- Total features: 56
- Completed: 13
- Remaining: 43
- Current cutoff blockers: 43
- Accepted/deferred follow-up: 2
- Superseded/obsolete checklist debt: 0
