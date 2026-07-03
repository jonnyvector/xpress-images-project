# graduated-trust-pipeline — Implementation Plan

Source spec: `.plans/graduated-trust-pipeline/01_graduated-trust-generation-pipeline.rfc.md`
(RFC-01, revised after four-agent review; see `rfc-review.md`; archived — this plan is
self-contained, see Interface Specifications below).

## ⚠️ Execution Protocol

A progress report exists at `.plans/graduated-trust-pipeline/progress-report.md`. It
lists every user-facing feature for every milestone as a checkbox.

**Mandatory rules for all agents working on this plan:**

1. Before starting a milestone, run `plan-db check-progress --plan
   "graduated-trust-pipeline"` and read its section in the progress report — those
   current-cutoff checkboxes are your spec
2. Check each box as you complete the feature, not at the end
3. A milestone is NOT done until every current-cutoff checkbox under it is checked
4. If you find features missing from the report, add them first
5. Never declare a phase complete without updating the current focus marker and Summary
6. Deferred follow-up and superseded/obsolete checklist debt must not be counted as
   current blockers

## Architecture

The validated QA pipeline (vision judge + geometry checks) moves from offline scripts
into the live app as server-enforced trust gates. Trust is graduated:
<!-- D-004 --> Stage A (replica MUST be human-approved before any variants) →
Stage B (small batches of ≤5, human-reviewed) → Stage C (bulk 35–50, manually
unlocked). <!-- D-003 --> Graduation is a manual operator decision informed by a
reliability ledger; the system never auto-unlocks.

Everything rests on a new identity layer: <!-- D-006 --> every generated image
(replica or variant attempt) gets a stable `image_id` (uuid4 hex) at submission.
Approvals, QA verdicts, and ledger records key off image IDs — never positional
candidate keys, which are completion-ordered, wiped on re-learn, and collide across
re-learns (`{pid}:0:replica:-1` is reused). Each generation run persists a **run
manifest** (`output/.projects/<id>/runs/<run_id>.json`) holding planned selections,
attempt history, an atomic spend counter, a config snapshot, and status
(`running|done|truncated`).

QA runs on a dedicated async lane (2-worker executor) decoupled from generation
status; <!-- D-007 --> `error` is a first-class fourth verdict (gates as
`needs_human`, one automatic re-judge, never auto-regenerates, excluded from
agreement). Auto-regeneration of `regenerate` verdicts is bounded per wood slot
(<!-- D-005 --> max 2 retries) and by a per-run cost cap on **unconsented** spend
only; <!-- D-009 --> initial images are consented via a confirm dialog that shows a
worst-case band. <!-- D-008 --> Agreement statistics count only decisive verdicts
(pass/regenerate); deferrals are reported separately.

### Key Constraints

| Constraint | Impact |
|-----------|--------|
| `output/.projects/` is irreplaceable (signatures) | D0 migration MUST be non-destructive + backward-compatible; no file deletion anywhere in this plan |
| `output/.qa/labels.json` is frozen calibration ground truth | Approvals live in a separate store; no seeding from labels <!-- D-011 --> |
| Global Gemini concurrency cap = `_api_semaphore(4)` | QA tasks hold ONE slot per entire `judge()` call <!-- D-010 --> |
| Single-operator internal tool, localhost | No auth added; X-API-Key flows per-request, never persisted server-side |
| No new dependencies | stdlib + existing deps only (google-genai, pillow, numpy, fastapi, pytest) |
| Ruff line length 100, rules E,F,I,UP,B,SIM, py312 syntax | run `uv run ruff check backend scripts tests` before each commit |
| Existing tests must stay green at every gate | `uv run pytest` (tests/ + tests/qa/) |

### Boundaries

| Module | Owns | Talks to |
|--------|------|----------|
| `backend/state.py` (`ResultRecord`, migration) | project persistence, record schema, archive | disk (`output/.projects/`) |
| `backend/runs.py` (new) | run manifests, spend counters, truncation detection | `output/.projects/<id>/runs/`, store lock |
| `backend/selections.py` (new; moved from worker) | swatch → resolved selection list | `backend/materials.py`, `swatches/` |
| `backend/qa/approvals.py` (new) | human verdicts, locked store | `output/.qa/approvals.json` |
| `backend/qa/reliability.py` (new) | ledger append + aggregation | `output/.qa/reliability.jsonl` |
| `backend/qa/qa_lane.py` (new) | async QA executor, verdict production, re-judge, auto-regen dispatch | `judge.py`, `geometry.py`, `policy.py`, `worker.py` executor, approval store |
| `backend/qa/trust_config.json` (new) | gate + cap configuration | read by router (gate time) + snapshotted into run manifests |
| `backend/routers/projects_generation.py` | gates GT-001/002/005/006, estimate endpoint | selections, approvals, runs, worker |
| `backend/routers/qa.py` (new) | approval + reliability endpoints | approvals, reliability |
| frontend | badges, approve/reject, confirm dialog, reliability panel, truncation banner | extended `ProjectResponse`/`GenerationStatusResponse` |

Candidate keys (`{pid}:{version}:{kind}:{index}`) remain ONLY in the offline eval
path; `scripts/qa_eval.py` gets an adapter mapping approved image IDs → candidate
keys. The two key spaces meet nowhere else. <!-- D-006 -->

New modules MUST carry module-level comments stating what they own and why they
exist (matches `backend/qa/` house style).

### Observability

Runtime behavior changes (background QA lane, auto-regen, cost caps), so
observability is part of the feature, not an afterthought:

- **Run manifests are the inspection surface**: every submission, attempt, verdict,
  cap event (GT-003), and truncation is a readable JSON record on disk; the UI
  surfaces manifest summaries (progress, truncation banner).
- **Structured verdict records**: `QaVerdict` carries `qa_status`
  (`pending|judging|done`), scores, geometry outcome, reason, timestamp — the UI
  hover shows the judge's reasoning verbatim.
- **Typed error codes** GT-001…GT-006 with defined channels (HTTP status vs run
  manifest vs log) — GT-003 lives on the manifest, never in `project.errors`.
- **Startup invariant**: `running` manifests flip to `truncated` on load; silent
  half-finished runs are structurally impossible.
- **Ledger is append-only JSONL** — auditable by eye, greppable, and the aggregate
  endpoint recomputes from the file (no hidden state).

---

## Assumptions

| Code | Assumption | Status | Impact if False |
|------|-----------|--------|-----------------|
| A-001 | Per-image judge cost/latency in the app path is acceptable (1–3 vision calls/image, seconds each) | deferred — measured via Phase 3 telemetry (RFC OQ-1) | Switch to batch judging or a cheaper judge model; QA lane isolation means no architecture change |

No spike stage: A-001 is intentionally deferred to live telemetry — the judge already
ran across the full 179-label corpus during calibration, so the risk is bounded and
its mitigation is config-level.

---

## Phases

### Phase 1: Identity foundation (D0)

**Goal:** Every image has a stable `image_id`, runs are persisted and
crash-detectable, and old projects load unchanged.

**Gate from previous:** none (first phase).

#### M1: ResultRecord + non-destructive migration

- **Dependencies:** none
- **Effort:** M
- **Tasks:**
  1. RED: tests for `ResultRecord` round-trip through `ProjectStore` save/load
     (image_id, wood_name, attempt, created_at preserved).
  2. RED: migration test — a fixture project in old tuple format loads with
     generated image_ids, `attempt=0`, and re-saves in new format **without touching
     signature bytes or image files** (assert bytes identical, no deletions).
  3. RED: replica receives an `image_id` at learn-store time.
  4. GREEN: implement `ResultRecord` in `backend/state.py`; loader migrates tuples;
     `record_result`/`record_retry_result` create records and **return the record**
     (not bool) so callers can bind verdicts to the image they stored.
  5. RED: `archive_current_version` carries records + `qa_verdicts` into
     `versions/vN/`; restore path round-trips them.
  6. GREEN: implement archive/restore carriage.
  7. REFACTOR: update existing tests/callers for the new return type; ruff clean.

#### M2: Run manifest module

- **Dependencies:** M1
- **Effort:** M
- **Tasks:**
  1. RED: tests for `backend/runs.py` — create manifest (planned selections, config
     snapshot), append attempts, atomic counter increments under the store lock,
     status transitions `running→done`.
  2. RED: truncation test — a manifest left `running` flips to `truncated` on store
     load and is exposed on the project.
  3. GREEN: implement `RunManifest` (`output/.projects/<id>/runs/<run_id>.json`),
     increment-before-submit counter API, startup sweep.
  4. GREEN: wire `_run_generation` to create/update/close manifests.
  5. REFACTOR: worker progress fields derive from the manifest where applicable.

#### M3: Shared selection resolver

- **Dependencies:** none (parallel with M1)
- **Effort:** S
- **Tasks:**
  1. RED: move-tests — `backend/selections.py::build_selections` reproduces current
     `_build_selections` behavior (virtual swatches, silent drop of unresolvables,
     flat-panel descriptions).
  2. GREEN: move the function; worker imports it; export resolved-count helper.
  3. REFACTOR: delete the private copy; ruff clean.

### Gate 1→2

- [ ] All Phase 1 milestone tests pass; full suite green (`uv run pytest`)
- [ ] A real pre-existing project from `output/.projects/` loads, round-trips, and
      its signature bytes are byte-identical afterward
- [ ] `npm run lint` and `uv run ruff check backend tests` clean

### Phase 2: Approval store + gates (the money-saver)

**Goal:** Variant generation is impossible without an approved replica; the operator
can approve/reject from the UI.

**Gate from previous:** Gate 1→2 passed.

#### M4: ApprovalStore

- **Dependencies:** M1
- **Effort:** S
- **Tasks:**
  1. RED: tests — set/get/for_project/approved_ids round-trip; verdict enum +
     REASONS vocabulary validation; concurrent reader-vs-writer test proving the
     internal lock. <!-- D-010 -->
  2. GREEN: implement `backend/qa/approvals.py` (LabelStore pattern + `_lock`).
  3. REFACTOR: none expected.

#### M5: Gates + endpoints

- **Dependencies:** M4, M3, M2
- **Effort:** M
- **Tasks:**
  1. RED: gate tests on `POST /projects/{id}/generate` — unapproved replica → 409
     GT-001; resolved selections > 5 while bulk locked → 422 GT-002; empty resolved
     selections → 400 GT-006; approved replica + ≤5 → run starts.
  2. RED: trust_config parse-error test → conservative fallback (bulk locked, $10 cap).
  3. RED: approval endpoint tests — `POST /projects/{id}/approvals` validates
     image-belongs-to-project (GT-005), persists, returns updated state;
     `GET /projects/{id}/approvals` lists.
  4. GREEN: implement `trust_config.json` loader, gate checks in
     `projects_generation.py`, `backend/routers/qa.py` approval endpoints.
  5. RED: revocation-mid-run test — rejecting the replica during a running generation
     does not cancel it; next `POST /generate` is gated.
  6. GREEN/REFACTOR: response models gain `replica_approved`; ruff clean.

#### M6: Minimal approval UI

- **Dependencies:** M5
- **Effort:** M
- **Tasks:**
  1. Extend `types.ts` + `api.ts` for approvals and gate errors.
  2. Replica Approve/Reject buttons + reject-reason checklist (REASONS vocabulary)
     in `UploadStep`/`ProjectTab`; blocking banner "Variants locked — approve the
     replica first" while unapproved.
  3. Surface GT-001/GT-002/GT-006 messages on the generate flow; Stage-B warning in
     `SwatchGrid` beyond 5 selections (server remains authority).
  4. Verify by driving the real flow: learn → blocked generate → approve → generate.

### Gate 2→3

- [ ] Gated generate returns correct codes end-to-end (curl + UI)
- [ ] Approval round-trip works from the UI; revocation does not cancel in-flight work
- [ ] Full suite + lint green

### Phase 3: Async QA lane + badges

**Goal:** Every stored image gains a pipeline verdict asynchronously; the UI shows
verdicts without generation status ever waiting on the judge.

**Gate from previous:** Gate 2→3 passed.

#### M7: QA lane

- **Dependencies:** M1, M2, M4
- **Effort:** L
- **Tasks:**
  1. RED: tests with a fake judge client — image stored → QA task enqueued →
     `QaVerdict` persisted by image_id with `qa_status` transitions
     `pending→judging→done`; generation_status "done" unaffected by a slow judge.
  2. RED: single-semaphore-slot test — entire judge() call (3 votes) holds one slot.
     <!-- D-010 -->
  3. RED: error lifecycle — judge failure → one automatic re-judge → still failing →
     verdict `error`, gates as needs_human, never cached, never auto-regens.
     <!-- D-007 -->
  4. RED: policy composition — variant QA passes `replica_approved` +
     approvals-derived inputs into `backend/qa/policy.decide()`; replica QA uses
     sample-reference advisory path.
  5. GREEN: implement `backend/qa/qa_lane.py` (2-worker executor); hook into
     `_run_learn`, `_run_generation`, `_run_retry` after record storage.
  6. REFACTOR: manual "Re-judge" endpoint (`POST /projects/{id}/images/{image_id}/rejudge`).

#### M8: Verdict surfacing

- **Dependencies:** M7
- **Effort:** M
- **Tasks:**
  1. Extend `ProjectResponse`/`GenerationStatusResponse` with `qa_verdicts` and run
     manifest summary; adjust `usePollingTask` consumers.
  2. Badges on `ResultsGrid` + replica: pass / regenerate / needs-human / error /
     judging…, judge reason + scores on hover.
  3. Truncation banner from `truncated` manifests.
  4. Verify against a live generation run.

### Gate 3→4

- [ ] Live run produces verdicts on all images; UI badges update by polling
- [ ] Judge outage simulation (bad key) leaves generation usable, verdicts `error`
- [ ] Record observed per-image judge cost/latency → resolve A-001

### Phase 4: Reliability ledger + estimate + cost confirm

**Goal:** Every human verdict is compared to the pipeline's; spend is consented with
honest numbers.

**Gate from previous:** Gate 3→4 passed.

#### M9: Ledger

- **Dependencies:** M4, M7
- **Effort:** M
- **Tasks:**
  1. RED: ledger append on approval write (pipeline verdict captured at decision
     time; `null` when QA incomplete, excluded from rates).
  2. RED: agreement math — decisive-only agreement, deferral rate separate, splits
     by kind and style_class. <!-- D-008 -->
  3. GREEN: implement `backend/qa/reliability.py` + `GET /qa/reliability`.
  4. REFACTOR: ledger-append failure is logged, never blocks the approval (ordered
     writes, not atomic).

#### M10: Estimate + confirm + panel

- **Dependencies:** M9, M3
- **Effort:** M
- **Tasks:**
  1. RED: `GET /projects/{id}/generate/estimate` — resolved-selection count, stage,
     gate_ok/gate_reason, `est_cost_usd = N*c`, `worst_case_usd = N*c + cap`.
     <!-- D-009 -->
  2. GREEN: implement endpoint.
  3. Confirm dialog in the generate flow ("N images ≈ $X (worst case $Y) — proceed?");
     reliability panel (agreement %, deferral %, counts per kind/style-class).
  4. Verify by driving the real flow.

### Gate 4→5

- [ ] Approving/rejecting from the UI appends correct ledger records
- [ ] Confirm dialog numbers match manifest reality after a run completes
- [ ] Full suite + lint green

### Phase 5: Auto-regeneration loop

**Goal:** `regenerate` verdicts trigger bounded, cost-capped automatic retries; the
best attempt wins deterministically.

**Gate from previous:** Gate 4→5 passed.

#### M11: Auto-regen

- **Dependencies:** M7, M2
- **Effort:** L
- **Tasks:**
  1. RED: regenerate verdict → new attempt submitted (fresh image_id, attempt K+1),
     re-judged, up to 2 retries per wood slot; needs_human/error never retry.
     <!-- D-005 --> <!-- D-007 -->
  2. RED: cap accounting — increment-before-submit on `unconsented_images`, rollback
     on cap breach, remaining retries cancelled, GT-003 recorded on the manifest
     (NOT in project.errors). <!-- D-009 -->
  3. RED: best-attempt selection — highest score sum wins; tie → highest attempt
     number; pointer update under the store lock; all attempt files retained
     (`result_N_attempt_K.bin`). <!-- D-012 -->
  4. RED: concurrency — two wood slots retrying simultaneously don't starve the
     4-way generation pool or misbind verdicts (records bind by image_id from M1).
  5. GREEN: implement in `qa_lane.py` + `runs.py`.
  6. REFACTOR: manifest attempt entries render in the UI (attempt count on badge).

### Gate 5→6

- [ ] Forced-regenerate simulation retries ≤2, keeps best deterministically,
      respects cap with GT-003 on the manifest
- [ ] Full suite + lint green

### Phase 6: Bulk unlock mechanics

**Goal:** Stage C exists, is operator-unlockable per style-class or globally, and is
revocable without restart.

**Gate from previous:** Gate 5→6 passed.

#### M12: Bulk unlock

- **Dependencies:** M5
- **Effort:** S
- **Tasks:**
  1. RED: style-class resolution — project's door_style → `style_class()` →
     `bulk_unlocked_style_classes` membership or global flag lifts GT-002.
  2. RED: revocation — config edit re-locks next request without restart; in-flight
     run unaffected (snapshot semantics). <!-- D-009 -->
  3. GREEN: implement; surface stage (A/B/C) in the estimate + UI.
  4. REFACTOR: eval-adapter — `scripts/qa_eval.py` maps approved image IDs →
     candidate keys so offline eval keeps working. <!-- D-006 -->

### Gate 6→done

- [ ] Full-workflow rehearsal on a real project: learn → approve replica → 5-batch →
      review → unlock style-class → bulk run with auto-regen → ledger populated
- [ ] Full suite + lint green; `docs/qa-pipeline.md` updated with the operator workflow

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation | Owner |
|------|----------|------------|------------|-------|
| Migration bug corrupts a real project manifest | high | low | Non-destructive loader (old files untouched until re-save); Gate 1→2 byte-identity check on a real project; signatures never rewritten | Phase 1 |
| Gate bug lets an ungated bulk run through | high | low | Server-side gates with dedicated tests per code; Stage-C locked by default; conservative config fallback | Phase 2 |
| Judge latency makes verdicts uselessly slow (A-001) | medium | medium | QA lane isolation; measure at Gate 3→4; fallback = cheaper judge model / batch judging (config-level) | Phase 3 |
| Cap accounting race overshoots spend | medium | low | Increment-before-submit under store lock; dedicated concurrency test in M11 | Phase 5 |
| Ledger biased by early deferral-heavy rounds | medium | medium | Decisive-only agreement + separate deferral rate (D-008); operator sees both before unlocking | Phase 4 |
| Frontend drift from extended response models | low | medium | types.ts updated in the same milestone as each model change; `npm run build` at every gate | all |

---

## Escape Hatches

1. **If the M1 migration proves riskier than expected on real data** (Gate 1→2
   byte-identity fails): fall back to a sidecar file
   (`records.json` alongside the untouched manifest) instead of upgrading the
   manifest in place; schema stays the same, only storage location changes.
2. **If A-001 fails at Gate 3→4** (judge too slow/expensive in-app): keep the QA
   lane but switch `DEFAULT_MODEL` for in-app judging to a cheaper/faster model and
   re-validate against the calibration labels before trusting its verdicts;
   worst case, in-app QA becomes badge-only (no auto-regen) until judged viable.
3. **If auto-regen (Phase 5) proves unstable**: ship Phases 1–4 without it —
   `regenerate` verdicts surface as badges and the operator uses the existing manual
   per-result retry. The trust workflow (gates + ledger) is intact without auto-regen.
4. **If bulk (Phase 6) is premature per the ledger**: nothing to do — Stage C ships
   locked; the operator simply doesn't unlock it. All value up to Stage B is live.

---

## Progress Report Accounting

The progress report is the implementation resume state. It must use normalized
accounting, not raw checkbox counts:

- current cutoff blockers count only active unchecked work
- accepted/deferred follow-up is excluded from current blockers
- superseded/obsolete checklist debt is struck through or moved out of current
  accounting with a decision/gate reference
- the current focus marker must match the first unchecked current-cutoff checkbox

Before resuming implementation or declaring convergence, run:

```bash
plan-db check-progress --plan "graduated-trust-pipeline"
```

---

## Validation Commands

```bash
uv run pytest                          # full backend suite (tests/ + tests/qa/)
uv run ruff check backend scripts tests
npm run lint                           # frontend eslint
npm run build                          # frontend type-check + build
npm run dev                            # drive the real flow (backend :8000, frontend :5173)
```

---

## Decisions

Canonical decisions are in the plan database
(`.plans/graduated-trust-pipeline/plan.db`). Query with:

```bash
npx tsx <planner-skill-dir>/scripts/plan-db.ts query-decisions --plan "graduated-trust-pipeline"
```

Key decisions referenced in this document use `<!-- D-NNN -->` markers:
D-002 (in-app), D-003 (manual graduation), D-004 (Stage A/B/C shape),
D-005 (2 retries), D-006 (image_id identity + run manifests), D-007 (async QA lane +
error lifecycle), D-008 (decisive-only agreement), D-009 (consented/unconsented spend,
snapshots, worst-case estimate), D-010 (locks + semaphore semantics + shared resolver),
D-011 (no labels seeding), D-012 (attempt retention + deterministic tie-break),
D-013 (re-judge endpoint).

---

## Interface Specifications

Normative interfaces consolidated from RFC-01 (archived at
`.plans/graduated-trust-pipeline/01_graduated-trust-generation-pipeline.rfc.md`).

### Data models

```python
@dataclass
class ResultRecord:                      # backend/state.py
    image_id: str        # uuid4 hex, assigned at submission
    wood_name: str
    attempt: int         # 0 = initial, 1..max_auto_retries = auto-regen attempts
    created_at: str      # ISO 8601
    # bytes on disk: active attempt keeps result_N.bin naming;
    # superseded attempts stored as result_N_attempt_K.bin — never deleted

@dataclass
class QaVerdict:                         # keyed by image_id on ProjectState
    verdict: str        # "pass" | "regenerate" | "needs_human" | "error"
    reason: str
    scores: dict[str, int]     # judge rubric scores
    geometry: str | None       # "ok" | "drift" | "unmeasurable" | None (excluded class)
    qa_status: str             # "pending" | "judging" | "done"
    judged_at: str             # ISO 8601

@dataclass
class Approval:                          # backend/qa/approvals.py
    image_id: str
    project_id: str
    kind: str          # "replica" | "variant"
    verdict: str       # "approved" | "rejected"
    reasons: list[str] = field(default_factory=list)  # REASONS vocab, rejects only
    note: str = ""
    decided_at: str = ""   # ISO 8601, set by the store
```

`ApprovalStore` API: `set(approval)`, `get(image_id)`, `for_project(project_id)`,
`approved_ids() -> frozenset[str]` — all guarded by an internal lock.

### Run manifest (`output/.projects/<id>/runs/<run_id>.json`)

```json
{
  "run_id": "...", "started_at": "...", "status": "running|done|truncated",
  "config_snapshot": { "...": "trust_config.json values at run start" },
  "planned": [{"wood_name": "...", "image_id": "..."}],
  "attempts": [{"image_id": "...", "wood_name": "...", "attempt": 1,
                "verdict": "regenerate", "active": false}],
  "images_submitted": 7, "unconsented_images": 2
}
```

Counters increment under the store lock **before** each API submission. `running`
manifests flip to `truncated` on store load.

### Configuration (`backend/qa/trust_config.json`)

```json
{
  "small_batch_limit": 5,
  "bulk_unlocked": false,
  "bulk_unlocked_style_classes": [],
  "max_auto_retries": 2,
  "run_cost_cap_usd": 10.0,
  "image_cost_usd": 0.134
}
```

Read at gate time per request; snapshotted into each run manifest at run start; parse
error → conservative fallback (bulk locked, cap $10). Cost cap bounds **unconsented**
spend (auto-retries) only.

### API surface

```
POST /projects/{id}/approvals            body: {image_id, verdict, reasons?, note?}
GET  /projects/{id}/approvals            → ApprovalStore.for_project(id)
POST /projects/{id}/images/{image_id}/rejudge   → re-enqueue QA for an image
GET  /qa/reliability                     → {agreement_rate, deferral_rate, counts,
                                            disagreements} split by kind + style_class
GET  /projects/{id}/generate/estimate    → {images: N, est_cost_usd: N*c,
                                            worst_case_usd: N*c + cap,
                                            stage: "A"|"B"|"C", gate_ok: bool,
                                            gate_reason: str|null}
```

`ProjectResponse`/`GenerationStatusResponse` gain `qa_verdicts` (by image_id),
`replica_approved: bool`, and the current run's manifest summary.

### Reliability ledger record (`output/.qa/reliability.jsonl`, append-only)

```json
{"image_id": "…", "project_id": "abc", "kind": "variant",
 "style_class": "frame_standard", "pipeline_verdict": "pass",
 "human_verdict": "rejected", "reasons": ["profile_character"],
 "at": "2026-07-03T10:22:00Z"}
```

Agreement counts only decisive verdicts: `pass`+approved / `regenerate`+rejected =
agreement; inverses = disagreement; `needs_human`/`error`/`null` = deferral bucket.

### Error codes

```
GT-001 (409)          Replica not approved → blocking banner, approve or re-learn
GT-002 (422)          Resolved selections > small_batch_limit while bulk locked
GT-003 (run manifest) Unconsented-spend cap hit; retries cancelled (never in project.errors)
GT-004 (logged)       QA error → one auto re-judge → verdict "error", gates as needs_human
GT-005 (400)          image_id invalid for project
GT-006 (400)          Resolved selection empty
```

### Gate order on POST /generate

1. Existing checks (signature, swatches, not already running)
2. GT-001 replica approval (current replica's image_id)
3. Resolve selections via `backend/selections.py::build_selections`
4. GT-006 empty → 400; GT-002 over-limit while bulk locked → 422
5. Start run: create manifest with config snapshot

Manual per-result retry (`/results/{idx}/retry`) is NOT gated. Approval revocation
mid-run never cancels in-flight work; it applies at the next gate check.

### Invariants (always true)

- Nothing under `output/.projects/` is ever deleted; signature bytes never rewritten
- `output/.qa/labels.json` is never written by any component in this plan
- Approvals/verdicts/ledger key off `image_id`; candidate keys only in offline eval
- One `_api_semaphore` slot spans one entire `judge()` call
- `generation_status` never waits on QA
