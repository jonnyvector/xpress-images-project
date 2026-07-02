# Phase 2 spike results (M4)

Full sweep table: see `.plans/geometry-checks/m2-m3-report.md` (post-fix sweep).

## Assumption verdicts
- **A-001 FAIL**: 15/15 replica-vs-sample measurable after real-photo box
  fallback (was 0/15), but only 4/15 (27%) high confidence vs >=80% target.
  Low-confidence causes are honest: pale-wood margins, boundary-count
  disagreement, GEO-003 partials.
- **A-002 FAIL (premise wrong)**: variant geometry rejects measure at
  0.0005-0.0012 delta vs their own replicas — drift was INHERITED from
  rejected replicas (D-009), not variant-introduced. Synthetic 2-3% variant
  drift is detectable at high confidence; no real variant-vs-approved-replica
  drift exists in the miss set.

## Consequences (D-010)
- Variant-vs-replica = primary hard gate; replica-vs-sample = advisory.
- Transitive replica approval added (flagged), covers all 5 variant misses
  by production semantics.
- OpenCV declined — photo alignment no longer load-bearing.
- Original M4 acceptance criterion (>=4/5 variant misses by measurement)
  superseded; replaced by policy-level acceptance tests in Phase 3.

## Headline numbers (post-fix sweep)
- Replica-vs-sample measurable: 15/15 (4 high conf)
- Accept false drifts at high confidence: 1 (threshold artifact, M7 scope)
- Unmeasurable: 1 (honest GEO-002 on a labeled reject -> needs_human)
