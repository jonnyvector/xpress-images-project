# geometry-checks — Progress Report

> Auto-generated from implementation plan. This is the canonical source of
> truth for what is done and what remains. Update this file as features are
> implemented — never mark a milestone complete until every current-cutoff
> checkbox under it is checked.

> Current focus: Phase 4 — Threshold calibration + acceptance

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

- [x] Feature: explicit style→class dict covering all catalog keys (frame_standard | frame_narrow | excluded) with module comment
- [x] Feature: shaker-family keys map to measurable classes; skinny-shaker maps to frame_narrow (test)
- [x] Feature: slab/bevel, plank, louver, radius/arched, glass styles map to excluded (test)
- [x] Feature: unknown/None door_style maps to excluded — fail-safe (test)

### M3: Synthetic measurement core
Source: new `backend/qa/geometry.py`, new `tests/qa/test_geometry.py`

- [x] Feature: synthetic door fixture builder (exact ratios + grain-noise overlay + JPEG re-encode)
- [x] Feature: load/grayscale at min(native, 1536) working width
- [x] Feature: door-box detection with confidence checks (min_box_fraction, margin variance, aspect sanity)
- [x] Feature: edge-energy profiles with two-scale peak persistence (grain suppression)
- [x] Feature: sub-pixel parabolic peak refinement
- [x] Feature: ratio recovery within ±0.005 at high confidence on noisy synthetic fixtures (test)
- [x] Feature: 2% and 3% stile/rail distortions and panel shifts detected as drift with correct worst-measurement detail (test)
- [x] Feature: order-preserving DP boundary matching; spurious peak does not cascade (test)
- [x] Feature: unmatched strong boundary counted in unmatched_boundaries, not folded into max_delta (test)
- [x] Feature: GEO-001 unreadable file → unmeasurable (test)
- [x] Feature: GEO-002 box-confidence failure → unmeasurable with detail naming image+check (test)
- [x] Feature: GEO-003 no interior peaks → partial measurement at low confidence (test)
- [x] Feature: GEO-004 injected exception → unmeasurable, never raises (test)
- [x] Feature: per-pair timing benchmark recorded (informational)

### M4: Real-fixture spike (A-001, A-002)
Source: `output/.qa/labels.json`, fixtures to `tests/qa/fixtures/geometry/`

- [x] Feature: fixture working copies exported (17 missed pairs + 18 style-matched accepts) with manifest.json
- [x] Feature: measure() run across all fixtures; results in phase2-spike.md + m2-m3-report.md
- [x] Feature: A-001 recorded FAIL in plan-db with evidence (27% high-conf vs 80% target)
- [x] Feature: A-002 recorded FAIL in plan-db with evidence (drift inherited from rejected replicas, D-009)
- [ ] ~~Feature: committed acceptance test — ≥4/5 variant-miss fixtures detected, zero high-confidence false drifts on accepts~~ — superseded by D-009/D-010: variant misses are D1-transitive; replaced by M5 policy acceptance tests
- [x] Feature: assumption-failure handling — targeted plan reshape per D-010, OQ-1 surfaced (user AFK, recommended path adopted, reversible)

## Phase 3: Policy + eval integration

### M5: Policy composition
Source: `backend/qa/policy.py`, `backend/qa/policy_config.json`

- [x] Feature: `decide(..., geometry: GeometryReport | None, replica_approved: bool)` implements the reshaped 12-step precedence (D-010)
- [x] Feature: transitive replica approval — variant of unapproved replica → needs_human, behind transitive_replica_review flag (test)
- [x] Feature: sample-reference drift → needs_human regardless of confidence — advisory rule (test)
- [x] Feature: acceptance test on real fixtures — all 5 variant-miss keys route needs_human via transitive rule; accepts 2564359f variants measure ok/high
- [x] Feature: high-confidence drift overrides passing judge → regenerate (test)
- [x] Feature: low-confidence drift → needs_human (test)
- [x] Feature: unmeasurable → needs_human (test)
- [x] Feature: judge-fail + unmeasurable → regenerate — asymmetry preserved (test)
- [x] Feature: geometry=None leaves pre-geometry behavior byte-identical (test)
- [x] Feature: PolicyConfig.geometry: GeometryConfig | None parsed from nested policy_config.json object; absent → disabled
- [x] Feature: policy_config.json committed with per-class thresholds (placeholder values until M7)

### M6: Eval wiring + cache + attribution
Source: `scripts/qa_eval.py`

- [x] Feature: style routing in eval (class → reference selection → measure)
- [x] Feature: geometry cache at output/.qa/geometry/<config-hash>/<key>.json (test)
- [x] Feature: config change busts cache via hash (test)
- [x] Feature: unmeasurable results not cached — retryable, mirrors judge error rule (test)
- [x] Feature: metrics output — geometry-only catches, geometry-added false flags, excluded-class counts, replica load (test)
- [x] Feature: full train-split eval smoke run clean; lint; committed

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
- Total features: 58
- Completed: 53
- Remaining: 5
- Current cutoff blockers: 5
- Accepted/deferred follow-up: 2
- Superseded/obsolete checklist debt: 1
