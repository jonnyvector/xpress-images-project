# RFC Review: RFC-01 — Graduated-Trust Generation Pipeline

Reviewed 2026-07-03 by four agents: structural validator (script), internal consistency
(sonnet), codebase alignment (sonnet), adversarial (opus).

## Structural Validation

PASS — 0 errors, 0 warnings (after promoting Motivation to a top-level section).

## Internal Consistency (8 findings)

1. `error` verdict missing from the Terminology definition of Pipeline verdict
   (QaVerdict and GT-004 both use it).
2. D5 agreement math never scores `error` pipeline verdicts (falls to "otherwise
   disagreement" while D3 treats error as needs_human).
3. D4 auto-regen rule silent on `error` verdicts (retry or not?).
4. D1 "MUST NOT write labels→approvals or vice versa" contradicts OQ-1 option (b)
   (seeding approvals from accept-labels).
5. `GET /projects/{id}/approvals` has no corresponding ApprovalStore method
   (interface exposes only set/get/approved_keys).
6. D6 says approval+ledger write happens "atomically" then defines non-atomic
   semantics (no rollback on ledger failure).
7. Terminology points STAGE_A at the State Machine, but the trust-level machine only
   has STAGE_B/STAGE_C; Stage A behavior lives unlabeled in the project-version machine.
8. "style-class" is load-bearing throughout but never defined in Terminology.

## Codebase Alignment (5 findings; all factual claims otherwise VERIFIED)

1. `backend/qa/styles_classes.py` is a plain module (`STYLE_CLASSES` dict +
   `style_class()` fn), not a "router" as D2 calls it.
2. GT-002 / estimate ambiguity: gate counts raw `project.selected_swatches` or
   resolved `_build_selections()` output? They differ (resolver silently drops
   unresolvables) and `_build_selections` is private to worker.py.
3. D4 mechanism conflicts with the current concurrency model: inline retry+judge in
   the single-threaded `as_completed` drain loop serializes the 4-way batch; "keep
   best attempt" needs try-before-commit semantics `record_result`/`record_retry_result`
   don't have.
4. `generation_total` is set once pre-run; D4's live increments need a new locked
   store mutation that isn't specified.
5. (Out of RFC scope) CLAUDE.md's router description is stale — routers were split
   into projects_common/crud/generation/media/versions.

## Adversarial (14 findings: 5 high, 7 medium, 2 low)

1. [HIGH] Verdict-to-result-index binding unsound: `record_result` assigns index
   implicitly at append time (completion order) and returns only bool — worker can't
   bind a verdict (or a best-attempt replacement) to the right `result_N` under
   concurrency.
2. [HIGH] Cost cap unenforceable as specified: no atomic per-run image counter; 4
   threads race the cap check; boundary semantics unstated; Stage-C initial 50 images
   are uncapped by design.
3. [HIGH] Inline QA holds the run's "done" transition hostage to judge
   latency/availability (up to 3 votes × 3 retries per candidate through the shared
   semaphore); a judge outage silently degrades all verdicts to error→needs_human and
   disables auto-regen.
4. [HIGH] Verdict history destroyed on re-learn/archive: `qa_verdicts` lives on
   ProjectState; `_run_learn` wipes results; `archive_current_version` knows nothing
   of verdicts → ledger writes pipeline_verdict:null for archived-version approvals,
   silently biasing the bulk-unlock dataset.
5. [HIGH] No mid-run persistence: crash mid-bulk reloads as "done" with a partial,
   half-judged batch and no truncation signal.
6. [MED] needs_human/error + human-reject counted as "agreement" inflates the
   graduation metric exactly when the pipeline shows no discriminative skill.
7. [MED] Cost confirm under-quotes: estimate excludes auto-regen spend (worst case
   N×(1+max_auto_retries)).
8. [MED] trust_config re-read semantics racy mid-run; should snapshot at run start.
9. [MED] ApprovalStore thread-safety unstated; worker reads race API writes — needs a
   lock like ProjectStore (MUST, not implied).
10. [MED] "Capped at 4" depends on whether the whole judge() call wraps one semaphore
    acquire (latency) or per-call (violated today); RFC doesn't pin it down.
11. [MED] Approval revocation mid-run not honored; no cancel path — state the policy.
12. [LOW/MED] GT-003 injected into `project.errors` renders as a fake failed variant
    and skews the reload denominator.
13. [LOW] "Best attempt, ties → latest" is nondeterministic (completion order); use
    highest attempt K.
14. [LOW] Zero-selection run passes gates ("0 images ≈ $0.00 — proceed?"); validate
    non-empty.

**Cross-cutting root cause:** the trust layer reasons in candidate keys
(`{pid}:{version}:{kind}:{index}`) while storage is a mutable, completion-ordered,
wiped-on-relearn list. Findings A1, A4, A13 (and consistency 1–3's error-verdict
lifecycle) all fall out of the lack of a stable per-variant identity that survives
completion order, re-judge, and archive.

## Summary

- **Errors**: 0 structural
- **Inconsistencies**: 8
- **Alignment issues**: 4 substantive (all mechanism gaps, no factual errors)
- **Challenges**: 14 (5 high / 7 medium / 2 low)
