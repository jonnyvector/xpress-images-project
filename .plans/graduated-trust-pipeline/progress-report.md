# graduated-trust-pipeline — Progress Report

> Auto-generated from implementation plan. This is the canonical source of truth for
> what is done and what remains. Update this file as features are implemented — never
> mark a milestone complete until every current-cutoff checkbox under it is checked.

> Current focus: Phase 6 — Bulk unlock mechanics

## Phase 1: Identity foundation (D0)

### M1: ResultRecord + non-destructive migration
Source: `implementation.md` (M1), Interface Specifications § Data models; `backend/state.py`

- [x] Feature: `ResultRecord` (image_id, wood_name, attempt, created_at) round-trips through `ProjectStore` save/load
- [x] Feature: old tuple-format project loads with generated image_ids and `attempt=0`
- [x] Feature: migration re-save leaves signature bytes byte-identical
- [x] Feature: migration never deletes or renames existing image files
- [x] Feature: replica receives an `image_id` when `learn_door_style` result is stored
- [x] Feature: `record_result` returns the created record so callers can bind verdicts to the stored image
- [x] Feature: `record_retry_result` returns the created record
- [x] Feature: `archive_current_version` carries records + `qa_verdicts` into `versions/vN/`
- [x] Feature: version restore round-trips records + verdicts
- [x] Feature: existing callers/tests updated for new return type; full suite green

### M2: Run manifest module
Source: `implementation.md` (M2), Interface Specifications § Run manifest; new `backend/runs.py`

- [x] Feature: manifest created at run start with planned selections and config snapshot
- [x] Feature: attempt entries appended with image_id/wood_name/attempt/verdict/active
- [x] Feature: `images_submitted` incremented under the store lock before each API submission
- [x] Feature: `unconsented_images` counted separately from consented submissions
- [x] Feature: status transitions `running→done` when the run completes
- [x] Feature: manifest left `running` flips to `truncated` on store load
- [x] Feature: truncated state exposed on the project response
- [x] Feature: `_run_generation` creates, updates, and closes manifests
- [x] Feature: config snapshot is immutable for the run's duration (mid-run config edits don't apply)

### M3: Shared selection resolver
Source: `implementation.md` (M3); `backend/worker.py::_build_selections` → new `backend/selections.py`

- [x] Feature: `build_selections` moved to `backend/selections.py` with module-level comment
- [x] Feature: virtual swatch (`virtual:` prefix) resolution behavior preserved
- [x] Feature: silent drop of unresolvable swatches preserved
- [x] Feature: flat-panel description handling preserved
- [x] Feature: worker imports the shared resolver; private copy deleted; suite green

## Phase 2: Approval store + gates

### M4: ApprovalStore
Source: Interface Specifications § Data models; new `backend/qa/approvals.py`

- [x] Feature: `Approval` dataclass persists to `output/.qa/approvals.json` on every write
- [x] Feature: `set()` rejects verdicts outside approved|rejected
- [x] Feature: `set()` rejects reasons outside the REASONS vocabulary
- [x] Feature: `decided_at` stamped by the store (ISO 8601)
- [x] Feature: `get(image_id)` / `for_project(project_id)` / `approved_ids()` work after reload
- [x] Feature: internal lock proven by a concurrent reader-vs-writer test

### M5: Gates + endpoints
Source: Interface Specifications § Gate order, § API surface, § Error codes; `backend/routers/projects_generation.py`, new `backend/routers/qa.py`

- [x] Feature: `POST /generate` with unapproved replica → 409 GT-001
- [x] Feature: resolved selections > `small_batch_limit` while bulk locked → 422 GT-002
- [x] Feature: empty resolved selections → 400 GT-006
- [x] Feature: approved replica + within limit → run starts (existing behavior preserved)
- [x] Feature: `trust_config.json` parse error → conservative fallback (bulk locked, $10 cap)
- [x] Feature: `POST /projects/{id}/approvals` validates image-belongs-to-project (GT-005)
- [x] Feature: `POST /projects/{id}/approvals` persists and returns updated state
- [x] Feature: `GET /projects/{id}/approvals` lists the project's approvals
- [x] Feature: replica rejection mid-run does not cancel the run; next `POST /generate` is gated
- [x] Feature: `replica_approved` exposed on `ProjectResponse`/`GenerationStatusResponse`
- [x] Feature: migrated project (base_door.bin, no base_image_id) gets a replica id at load — approvable without re-learn

### M6: Minimal approval UI
Source: `implementation.md` (M6); `frontend/src/` (types.ts, api.ts, UploadStep/ProjectTab, SwatchGrid)

- [x] Feature: `types.ts` + `api.ts` support approvals and typed gate errors
- [x] Feature: replica Approve / Reject buttons render with current approval state
- [x] Feature: Reject opens the REASONS-vocabulary checklist
- [x] Feature: blocking banner "Variants locked — approve the replica first" while unapproved
- [x] Feature: GT-001 / GT-002 / GT-006 messages surface on the generate flow
- [x] Feature: `SwatchGrid` warns beyond 5 selections in Stage B (server stays authoritative)
- [x] Feature: variant Approve/Reject controls on each result card (Stage B review)
- [x] Feature: `base_image_id` + per-result `image_id` exposed on API responses
- [x] Feature: manual flow verified end-to-end: learn → blocked generate → approve → generate

## Phase 3: Async QA lane + badges

### M7: QA lane
Source: Interface Specifications § Data models (QaVerdict), § Invariants; new `backend/qa/qa_lane.py`

- [x] Feature: QA task enqueued after image storage in `_run_learn`, `_run_generation`, and `_run_retry`
- [x] Feature: `QaVerdict` persisted by image_id with `qa_status` transitions pending→judging→done
- [x] Feature: `generation_status` "done" unaffected by slow/hung judge
- [x] Feature: one `_api_semaphore` slot held across an entire `judge()` call (votes + retries)
- [x] Feature: judge failure triggers exactly one automatic re-judge
- [x] Feature: persistent failure → verdict `error`, gates as needs_human
- [x] Feature: `error` verdicts never disk-cached and never trigger auto-regeneration
- [x] Feature: variant QA passes `replica_approved` + approvals-derived inputs into `policy.decide()`
- [x] Feature: replica QA uses the sample-reference advisory path
- [x] Feature: `POST /projects/{id}/images/{image_id}/rejudge` re-enqueues QA

### M8: Verdict surfacing
Source: Interface Specifications § API surface; `frontend/src/components/ResultsGrid.tsx`, polling hooks

- [x] Feature: `ProjectResponse`/`GenerationStatusResponse` carry `qa_verdicts` + run manifest summary
- [x] Feature: variant badges: pass / regenerate / needs-human / error / judging…
- [x] Feature: replica verdict badge
- [x] Feature: badge hover shows judge reason + rubric scores
- [x] Feature: truncation banner renders for `truncated` manifests
- [x] Feature: polling updates badges live during a real run

## Phase 4: Reliability ledger + estimate + cost confirm

### M9: Ledger
Source: Interface Specifications § Reliability ledger record; new `backend/qa/reliability.py`

- [x] Feature: ledger record appended on every approval-store write
- [x] Feature: pipeline verdict captured at decision time; `null` when QA incomplete
- [x] Feature: `null` verdicts excluded from rates
- [x] Feature: agreement computed over decisive verdicts only (pass+approved / regenerate+rejected)
- [x] Feature: deferral rate (needs_human/error) reported separately
- [x] Feature: aggregates split by kind (replica/variant) and by style_class
- [x] Feature: `GET /qa/reliability` recomputes from the JSONL file
- [x] Feature: ledger-append failure is logged and never blocks the approval write

### M10: Estimate + confirm + panel
Source: Interface Specifications § API surface; generate flow + new reliability panel in frontend

- [x] Feature: estimate returns resolved-selection count, stage (A/B/C), gate_ok, gate_reason
- [x] Feature: `est_cost_usd = N × image_cost`; `worst_case_usd = N × image_cost + run_cost_cap`
- [x] Feature: confirm dialog shows both numbers before `POST /generate`
- [x] Feature: `gate_ok: false` disables generation and renders the reason
- [x] Feature: reliability panel renders agreement %, deferral %, counts per kind/style-class
- [x] Feature: flow verified against a real run (dialog numbers match manifest afterward)

## Phase 5: Auto-regeneration loop

### M11: Auto-regen
Source: `implementation.md` (M11), Interface Specifications § Run manifest, § Error codes; `backend/qa/qa_lane.py` + `backend/runs.py`

- [x] Feature: `regenerate` verdict submits a new attempt (fresh image_id, attempt K+1)
- [x] Feature: new attempts are QA'd in turn; chain stops on `pass`
- [x] Feature: max 2 auto-retries per wood slot enforced
- [x] Feature: `needs_human` and `error` verdicts never auto-retry
- [x] Feature: increment-before-submit cap check on `unconsented_images` with rollback on breach
- [x] Feature: cap breach cancels remaining retries and records GT-003 on the manifest (never in `project.errors`)
- [x] Feature: best attempt = highest judge score sum; tie → highest attempt number
- [x] Feature: best-attempt pointer update under the store lock; all attempt files retained (`result_N_attempt_K.bin`)
- [x] Feature: concurrent retries across wood slots neither misbind verdicts nor starve the 4-way pool
- [x] Feature: attempt count visible on the variant badge

## Phase 6: Bulk unlock mechanics

### M12: Bulk unlock
Source: `implementation.md` (M12); `backend/qa/styles_classes.py::style_class`, trust_config

- [x] Feature: project's style-class membership in `bulk_unlocked_style_classes` (or global flag) lifts GT-002
- [x] Feature: config edit re-locks the next request without server restart
- [x] Feature: in-flight run unaffected by config edits (snapshot semantics)
- [x] Feature: stage (A/B/C) surfaced in the estimate response and UI
- [x] Feature: eval adapter maps approved image IDs → candidate keys; `scripts/qa_eval.py` works unchanged
- [ ] Feature: full-workflow rehearsal on a real project (learn → approve → 5-batch → review → unlock → bulk with auto-regen → ledger populated)
- [x] Feature: `docs/qa-pipeline.md` updated with the operator workflow

## Deferred follow-up

- [ ] Judge prompt iteration workstream (separate; runs against frozen calibration labels)
- [ ] Shopify/Matrixify CSV export (blocked on product/handle/SKU mapping — RFC OQ-2)
- [ ] Attempt-retention pruning policy at Stage C volumes (RFC OQ-3, D-012)
- [ ] A-001 judge cost/latency telemetry review at Gate 3→4 (deferred assumption)

## Superseded/obsolete checklist debt

(none)

## Summary
- Total features: 97
- Completed: 96
- Remaining: 1
- Current cutoff blockers: 1
- Accepted/deferred follow-up: 4
- Superseded/obsolete checklist debt: 0
