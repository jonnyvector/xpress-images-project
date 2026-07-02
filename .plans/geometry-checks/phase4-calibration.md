# Phase 4 calibration (M7)

Selection split: 111 train labels (26 rejects) excluding the 35 fixture keys
used for design/spike. All decisions derived offline from cached judge
verdicts (config 812b52bc6ea6) + cached geometry measurements (deltas are
threshold-independent).

## Geometry threshold sweep (36 combos)
frame_standard ∈ {0.02..0.05} × frame_narrow ∈ {0.01..0.02} × aspect ∈ {0.03..0.06}:
**flat curve** — recall 100.0%, false-flag 43.5% at every combination.
Geometry thresholds are not the operative lever on this data (D1 + transitive
+ judge already catch all selection rejects; geometry flags are advisory or
threshold-independent). FROZEN at synthetic-evidence values:
frame_standard 0.03, frame_narrow 0.015, aspect 0.04 (synthetic tests prove
2-3% distortions detected at these levels).

## min_score sweep
| min_score | recall | false-flag |
|-----------|--------|------------|
| 2 | 100.0% | 30.6% |
| 3 | 100.0% | 30.6% |
| 4 | 100.0% | 42.4% |

FROZEN: min_score = 3 (conservative end of the equal-metric range).

## False-flag composition at frozen config (selection accepts, 85)
- judge low scores / fail verdicts: dominant remainder (~26)
- geometry advisory (sample-reference drift → human): 4
- geometry replica drift / low-conf: 2

## Honest expectation for holdout
- Reject recall: high (selection 100%, train incl. fixtures 97.7%)
- False-flag: ~30% — the ≤20% target is NOT reachable by calibration alone;
  the remainder is judge-rubric disagreement, explicitly deferred to the
  judge-prompt-iteration track (out of scope per RFC v2 / D-010).
Decision on how to run the one-shot holdout gate: Jonathan's (see plan-db).
