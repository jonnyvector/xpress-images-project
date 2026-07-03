---
number: 01
title: "Graduated-Trust Generation Pipeline"
type: feature
status: Draft
author: Jonathan Hicks
date: 2026-07-03
---

# RFC-01: Graduated-Trust Generation Pipeline

## Abstract

Generating 35–50 wood variations off a bad replica wastes ~$5–7 of Gemini API spend per
project and floods the operator with unusable images. This RFC integrates the validated
QA judgment pipeline (vision judge + geometry checks, holdout recall 100% / false-flag
19.2%) into the live FastAPI + React app as a set of graduated trust gates: a replica
MUST be human-approved before any variants are generated; variant generation starts as
human-reviewed small batches (5) and graduates to bulk (35–50) only when the operator
manually unlocks it, informed by a reliability ledger that tracks pipeline-vs-human
agreement. QA verdicts are produced asynchronously at generation time, failed images
are auto-regenerated under a cost cap, and approved variants are later exported to
Shopify via Matrixify CSV (schema out of scope here).

## Introduction

### Problem

The QA judgment pipeline is built and validated but runs only offline
(`scripts/qa_eval.py`, `scripts/qa_report.py`) against already-generated images. The
live app has no gates: `POST /projects/{id}/generate` runs the full swatch selection
immediately after a style is learned, regardless of replica quality. Three gaps follow:

1. **Money**: variants of a bad replica are worthless but still cost ~$0.134 each.
2. **Approval state**: "replica approved" currently exists only as accept-labels in the
   calibration file `output/.qa/labels.json` (OQ-3 of the geometry-checks plan). There
   is no production approval record for the policy layer's `approved_keys` /
   `replica_approved` inputs.
3. **Trust evidence**: there is no recorded comparison between pipeline verdicts and the
   operator's own judgments, so there is no data-driven basis to decide when the
   pipeline can be trusted to gate bulk runs on its own.

A structural prerequisite surfaced during review: the app stores results as a
completion-ordered `list[tuple[str, bytes]]` that is wiped on re-learn, and the QA
candidate key treats `version 0` as "current" — so positional keys can neither bind a
verdict to the image it judged under concurrency nor survive re-learn (a new replica
would silently inherit the old replica's approval under the key
`{pid}:0:replica:-1`). <!-- D-006 --> The trust layer therefore keys off stable
per-image identifiers, introduced in D0 below.

### Scope

**In scope:**

- Stable per-image identity and persisted generation-run records (D0).
- First-class approval store for replicas and variants, exposed via API.
- Server-enforced generation gates (Stage A/B/C, defined below).
- Asynchronous QA judging (vision judge + geometry checks) at generation time.
- Auto-regeneration of `regenerate`-verdict variants with retry and cost caps.
- Reliability ledger recording pipeline-vs-human verdict pairs and an aggregate stats
  endpoint + UI panel.
- Frontend affordances: verdict badges, Approve/Reject controls, gated generate button,
  reliability panel, pre-spend cost confirmation.

**Out of scope:**

- Judge prompt iteration (separate eval-loop workstream against the frozen calibration
  labels; no code changes to this design).
- Shopify/Matrixify CSV export schema and script (deferred until the store's
  product/handle/SKU mapping is specified; see Open Questions).
- Automatic graduation rules (bulk unlock is a manual operator decision). <!-- D-003 -->
- Multi-user auth. The app is a single-operator internal tool. <!-- D-002 -->
- Any modification to the calibration ground truth `output/.qa/labels.json` or to the
  frozen holdout methodology.

## Motivation

The operator's stated workflow: *"replicas approved by our pipeline HAVE to be approved
by me first, at least for a while, before generating 35–50 variations… then after
replicas are approved we generate 5 variations that are approved by pipeline, then I
check those as well… if we go through multiple rounds where the approved replicas and
variants are good, then we bulk."* <!-- D-004 --> This RFC is that workflow, enforced
server-side.

## Terminology

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted as described in
RFC 2119.

- **Replica** — the base door image produced by `learn_door_style` (stored as
  `base_door.bin`); the geometry anchor for all variants of a project version.
- **Variant** — a generated image of the replica's door in a specific material.
- **Image ID** — a stable, unique identifier (`uuid4` hex) assigned to every generated
  image (replica or variant attempt) at submission time. Approvals, verdicts, and
  ledger records key off image IDs. Image IDs survive completion ordering, re-judging,
  re-learn, and version archiving. <!-- D-006 -->
- **Candidate key** — `"{project_id}:{version}:{kind}:{index}"`; the QA corpus/eval
  identifier. Retained for offline eval compatibility and as derived reporting
  metadata; the trust layer MUST NOT use candidate keys as primary keys because
  `version 0` is positional ("current") and index is completion-ordered.
- **Run / run manifest** — one generation request and its persisted record
  (`output/.projects/<id>/runs/<run_id>.json`): planned selections, per-image attempt
  history, spend counter, config snapshot, status.
- **Pipeline verdict** — the output of QA for one image:
  `pass | regenerate | needs_human | error`. `error` means the judge/geometry pass
  itself failed; it gates like `needs_human` and is excluded from agreement
  statistics. <!-- D-007 -->
- **Human verdict** — the operator's explicit `approved | rejected` on an image.
- **Approval store** — the production record of human verdicts
  (`output/.qa/approvals.json`), distinct from calibration labels.
- **Reliability ledger** — append-only record of (pipeline verdict, human verdict)
  pairs used to measure agreement.
- **Style-class** — the geometry measurability class of a door style
  (`frame_standard | frame_narrow | excluded`), resolved by `style_class()` in the
  existing `backend/qa/styles_classes.py` module. Bulk unlock and reliability
  breakdowns are scoped by style-class.
- **Stage A / B / C** — replica gate / small-batch variants / bulk variants (see State
  Machine).
- **Bulk unlock** — an operator-set configuration flag (global or per style-class)
  permitting Stage C generation sizes.
- **Consented spend** — images the operator explicitly confirmed in the pre-run cost
  dialog. **Unconsented spend** — auto-retry images the system adds on its own; only
  unconsented spend is bounded by the run cost cap. <!-- D-009 -->

## Design

### D0. Stable image identity and run manifests

<!-- D-006 -->
The foundation for everything else in this RFC.

**Result records.** `ProjectState.results` changes from `list[tuple[str, bytes]]` to a
list of records:

```python
@dataclass
class ResultRecord:
    image_id: str        # uuid4 hex, assigned at submission
    wood_name: str
    attempt: int         # 0 = initial, 1..max_auto_retries = auto-regen attempts
    created_at: str      # ISO 8601
    # image bytes stored on disk as today (result_N.bin naming preserved for the
    # active attempt; superseded attempts as result_N_attempt_K.bin)
```

- The replica also receives an `image_id` when `learn_door_style` stores it.
- **Migration** MUST be non-destructive and backward-compatible: on first load of an
  old-format project, tuples are converted to records with freshly generated
  `image_id`s and `attempt=0`; nothing under `output/.projects/` is deleted or
  overwritten except the manifest being upgraded, and signature bytes are never
  touched. Old app versions' data MUST remain readable.
- `qa_verdicts: dict[str, QaVerdict]` is keyed by `image_id` (replica included).
  `archive_current_version` MUST carry the verdicts and records of the archived
  version into `versions/vN/` so verdict history survives re-learn.

**Run manifests.** Every generation run (initial batch or auto-retry activity) is
recorded in `output/.projects/<id>/runs/<run_id>.json`:

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

- `images_submitted` and `unconsented_images` are incremented **under the store lock,
  before each API submission** — this is the atomic counter the cost cap reads.
  <!-- D-009 -->
- On process start, any run manifest still marked `running` MUST be flipped to
  `truncated` and surfaced in the project's status so a crash mid-bulk is visible,
  not silently reported "done".
- `config_snapshot` is taken once at run start; mid-run edits to `trust_config.json`
  apply to subsequent runs only. <!-- D-009 -->

### D1. Approval store (`backend/qa/approvals.py`)

A small module owning `output/.qa/approvals.json`, modeled on the existing `LabelStore`
pattern (load on init, persist on every write).

```python
@dataclass
class Approval:
    image_id: str
    project_id: str
    kind: str          # "replica" | "variant"
    verdict: str       # "approved" | "rejected"
    reasons: list[str] = field(default_factory=list)  # REASONS vocabulary, rejects only
    note: str = ""
    decided_at: str = ""   # ISO 8601, set by the store

class ApprovalStore:
    def set(self, approval: Approval) -> None: ...            # upsert + save
    def get(self, image_id: str) -> Approval | None: ...
    def for_project(self, project_id: str) -> list[Approval]: ...
    def approved_ids(self) -> frozenset[str]: ...
```

Rules:

- The store MUST guard all reads and writes with an internal lock (like
  `ProjectStore._lock`): worker threads read `approved_ids()` while API requests
  write. <!-- D-010 -->
- `verdict` MUST be `approved` or `rejected`; `reasons` MUST come from the existing QA
  `REASONS` vocabulary and SHOULD be present on rejects.
- The store MUST be separate from `labels.json`. Calibration labels remain frozen
  ground truth; approvals are operational state. Code MUST NOT write approvals into
  the label store or vice versa — including one-time seeding. Existing projects start
  unapproved and are approved by the operator as they go. <!-- D-011 -->
- Because approvals key off `image_id`, a re-learned replica is a new image and starts
  unapproved automatically; approvals of archived images remain valid history.
- For the offline eval path (`scripts/qa_eval.py`), which still operates in candidate
  keys, an adapter derives `approved_keys` by mapping approved image IDs to their
  candidate keys; the two key spaces meet only at that boundary.

### D2. Generation gates (server-enforced)

`POST /projects/{project_id}/generate` (`backend/routers/projects_generation.py`)
gains gate checks executed before `start_generation`:

1. **Stage A (replica gate).** The request MUST be rejected with `409` and error code
   `GT-001` if the current replica's `image_id` has no `approved` record in the
   approval store. The existing signature/swatch checks are unchanged.
2. **Selection resolution.** The gate and the estimate endpoint MUST count **resolved**
   selections — the output of `build_selections()` (today's private
   `worker._build_selections`, moved to a shared `backend/selections.py` module so the
   router, worker, and estimate use one resolver). <!-- D-010 --> A resolved selection
   count of zero MUST be rejected with `400` / `GT-006`.
3. **Stage B (small batch).** If bulk is not unlocked for the project's style-class,
   the request MUST be rejected with `422` / `GT-002` when the resolved selection
   count exceeds `small_batch_limit` (default **5**). <!-- D-004 -->
4. **Stage C (bulk).** When bulk is unlocked, any selection size is permitted.

`POST /projects/{id}/results/{idx}/retry` (manual retry) is NOT gated — retrying an
existing variant implies the replica gate already passed when it was generated.

Approval revocation while a run is in flight MUST NOT cancel in-flight work: the
current batch's spend is already consented, and images continue to record. Revocation
takes effect at the next gate check; there is no mid-run cancel path in this design.

The gate configuration lives in `backend/qa/trust_config.json`:

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

- `bulk_unlocked: true` unlocks bulk globally; otherwise a project's style-class
  (via `style_class()` in `backend/qa/styles_classes.py`) must appear in
  `bulk_unlocked_style_classes`.
- The file is operator-edited (or via a future settings endpoint). It is read at gate
  time per request and snapshotted into each run manifest at run start (D0); on parse
  error the server MUST fall back to the conservative defaults above (bulk locked,
  cap $10).

### D3. QA-at-generation (asynchronous lane)

<!-- D-007 -->
QA MUST NOT run on the generation run's critical path. A dedicated small executor
(the *QA lane*, `ThreadPoolExecutor(max_workers=2)`) receives one QA task per stored
image:

- **Replica**: at the end of `_run_learn`, when a new replica + signature is stored,
  a QA task is enqueued (judge with sample photo as reference; geometry
  replica-vs-sample advisory per existing policy).
- **Variant**: in the generation/retry paths, after the result record is stored, a QA
  task is enqueued (judge + geometry variant-vs-replica hard gate, exactly the
  composition in `backend/qa/policy.decide()`), with `approved_ids`-derived inputs
  from the approval store and `replica_approved` for the current replica.

Storage, keyed by `image_id` on `ProjectState` (and mirrored into the run manifest's
attempt entries):

```python
@dataclass
class QaVerdict:
    verdict: str        # "pass" | "regenerate" | "needs_human" | "error"
    reason: str
    scores: dict[str, int]     # judge rubric scores
    geometry: str | None       # "ok" | "drift" | "unmeasurable" | None (excluded class)
    qa_status: str             # "pending" | "judging" | "done"
    judged_at: str             # ISO 8601
```

Rules:

- `generation_status="done"` continues to mean *generation* is done; QA completeness
  is visible per-image via `qa_status`. The UI renders "judging…" badges until each
  verdict lands.
- Each QA task acquires **one** `_api_semaphore` slot for the *entire* `judge()` call
  (including majority-vote votes and retries). This preserves the global cap of 4
  concurrent Gemini calls; the latency cost of holding a slot across votes is
  acceptable because QA is off the critical path. <!-- D-010 -->
- QA calls reuse the request's `X-API-Key` (already threaded to the worker) and the
  judge's existing disk cache (`output/.qa/verdicts/<config-hash>/`).
- A judge/geometry failure MUST NOT fail or block the generation itself: the image is
  stored regardless. The failed QA task records verdict `error` and the QA lane
  SHOULD schedule exactly one automatic re-judge; if that also errors, the verdict
  stays `error`, gates as `needs_human`, and a manual "Re-judge" action remains
  available in the UI. `error` verdicts are not disk-cached (existing judge rule), so
  re-judging is always possible.
- Replica verdicts are advisory ordering for the operator (the human gate is absolute
  either way); variant verdicts drive auto-regeneration (D4) and review priority.

### D4. Auto-regeneration loop

When a variant's QA verdict lands as `regenerate`:

- The QA lane submits a new generation attempt for that wood (a fresh `image_id`,
  `attempt = K+1`) through the normal generation executor, then that attempt is QA'd
  in turn — up to `max_auto_retries` (default 2) additional attempts per wood slot.
  <!-- D-005 -->
- `needs_human` and `error` verdicts MUST NOT trigger auto-regeneration. <!-- D-007 -->
- All attempts are kept on disk during Stages A/B (`result_N_attempt_K.bin`);
  retention MAY be revisited at Stage C. <!-- D-012 -->
- **Best-attempt selection**: when a wood slot's attempts are exhausted (a `pass`
  verdict, retries used up, or cap hit), the attempt with the highest judge score sum
  becomes the active record; ties break to the **highest attempt number**
  (deterministic). Selection is a manifest/record pointer update under the store lock
  — image files are never deleted. <!-- D-012 -->
- **Cost cap**: before submitting each auto-retry, the QA lane increments
  `unconsented_images` under the store lock and checks
  `unconsented_images * image_cost_usd <= run_cost_cap_usd` (from the run's config
  snapshot); if the check fails the increment is rolled back, no submission happens,
  remaining retries for the run are cancelled, and the run manifest records
  `GT-003`. Initial (consented) images are never cancelled by the cap. <!-- D-009 -->
- Progress accounting: auto-retry attempts increment the run manifest's counters; the
  UI derives progress from the manifest, so `generation_total` semantics for the
  initial batch are unchanged (no mid-run mutation of `generation_total` is needed).

### D5. Reliability ledger (`backend/qa/reliability.py`)

Append-only JSONL at `output/.qa/reliability.jsonl`. One record per human verdict
event:

```json
{"image_id": "…", "project_id": "abc", "kind": "variant",
 "style_class": "frame_standard", "pipeline_verdict": "pass",
 "human_verdict": "rejected", "reasons": ["profile_character"],
 "at": "2026-07-03T10:22:00Z"}
```

- A record MUST be appended on every approval-store write, capturing the pipeline
  verdict for that `image_id` at decision time (`null` if QA hasn't completed;
  excluded from rates).
- **Agreement is computed over decisive pipeline verdicts only** (`pass` and
  `regenerate`): pipeline `pass` + human `approved`, or pipeline `regenerate` + human
  `rejected`, count as agreement; the inverse pairs count as disagreement.
  `needs_human` and `error` verdicts are reported separately as the **deferral rate**
  and MUST NOT count toward agreement — a pipeline that declines to decide
  demonstrates no discriminative skill. <!-- D-008 -->
- `GET /qa/reliability` returns: agreement rate over decisive verdicts, deferral
  rate, counts, and disagreement breakdown, split by `kind` (replica/variant) and by
  `style_class`, plus totals.
- Graduation is manual: the endpoint provides evidence; the operator edits
  `trust_config.json` to unlock bulk. The system MUST NOT auto-unlock. <!-- D-003 -->

### D6. API surface

```
POST /projects/{id}/approvals            body: {image_id, verdict, reasons?, note?}
GET  /projects/{id}/approvals            → ApprovalStore.for_project(id)
POST /projects/{id}/images/{image_id}/rejudge   → re-enqueue QA for an image (D3)
GET  /qa/reliability                     → aggregate agreement stats
GET  /projects/{id}/generate/estimate    → {images: N, est_cost_usd: N*c,
                                            worst_case_usd: N*c + cap,
                                            stage: "A"|"B"|"C", gate_ok: bool,
                                            gate_reason: str|null}
```

- `POST .../approvals` MUST validate that the `image_id` belongs to the project
  (GT-005). Writes are **ordered, not atomic**: the approval is persisted first, then
  the ledger record is appended; a ledger-append failure is logged and MUST NOT roll
  back the approval.
- The estimate's `images` count uses resolved selections (D2); `worst_case_usd` is
  the consented spend plus the full unconsented cap
  (`N*image_cost_usd + run_cost_cap_usd`), so the confirm dialog never under-quotes.
  <!-- D-009 -->
- `ProjectResponse` and `GenerationStatusResponse` gain `qa_verdicts` (by image_id),
  `replica_approved: bool`, and the current run's manifest summary so the frontend
  renders badges, gate state, and truncation warnings without extra round-trips.

### D7. Frontend

- **Verdict badges** on `ResultsGrid` items and on the replica image: pass /
  regenerate / needs-human / error / judging…, with judge reason + scores on hover.
- **Approve / Reject** buttons on the replica (blocking banner while unapproved:
  "Variants locked — approve the replica first") and on each variant. Reject opens the
  fixed reason checklist (same `REASONS` vocabulary as labeling).
- **Generate flow**: the generate button calls `/generate/estimate` first and shows a
  confirm dialog — "N images ≈ $X.XX (worst case $Y.YY with auto-retries) — proceed?"
  — before `POST /generate`. Estimate responses with `gate_ok: false` render the
  reason and disable generation.
- **Selection cap**: in Stage B the `SwatchGrid` selection indicator warns beyond 5
  selected; the server remains the authority (GT-002).
- **Truncation warning**: projects with a `truncated` run manifest show a banner so
  partial batches are never mistaken for complete ones.
- **Reliability panel**: a small view (in `Layout` or a drawer) rendering
  `/qa/reliability` — agreement %, deferral %, and counts per kind and style-class.

## State Machine

Per project version (the current replica and its variants). Stage A is the
`REPLICA_PENDING → REPLICA_APPROVED` gate below:

```
UNLEARNED → REPLICA_PENDING     (on: learn completes; QA verdict attached async)
REPLICA_PENDING → REPLICA_APPROVED  (on: operator approves replica)   [Stage A gate]
REPLICA_PENDING → REPLICA_REJECTED  (on: operator rejects replica)
REPLICA_REJECTED → REPLICA_PENDING  (on: re-learn → new version, new replica image_id)
REPLICA_APPROVED → GENERATING       (on: POST /generate, gates pass)
GENERATING → REVIEW                 (on: run done; variants carry pipeline verdicts)
REVIEW → GENERATING                 (on: further generate runs, same gates)
```

Trust level (orthogonal, per style-class or global, operator-controlled):

```
STAGE_B (default) → STAGE_C  (on: operator sets bulk_unlocked[_style_classes])
STAGE_C → STAGE_B            (on: operator revokes; MUST be reversible at any time)
```

(Stage A is not a trust-level state: the replica gate applies identically in Stage B
and Stage C.)

Invalid transitions (e.g. `POST /generate` in `REPLICA_PENDING`) MUST be rejected with
the error codes below and MUST NOT enqueue background work. Approval revocation during
`GENERATING` does not cancel in-flight work (D2).

## Error Handling

```
GT-001 (409, critical)  Replica not approved.
        Recovery: operator approves or rejects+re-learns. UI shows blocking banner.
GT-002 (422, warning)   Resolved selection exceeds small-batch limit while bulk locked.
        Recovery: trim selection to ≤5 or unlock bulk in trust_config.json.
GT-003 (run manifest, warning) Unconsented-spend cap reached; auto-retries cancelled.
        Recorded on the run manifest (NOT in project.errors, which is reserved for
        per-variant generation failures). Recovery: operator reviews remaining
        regenerate/needs_human verdicts manually; a new run gets a fresh budget.
GT-004 (logged, info)   QA judge/geometry error for an image.
        Recovery: verdict "error" after one automatic re-judge; gates as needs_human;
        image retained; manual re-judge available. Error verdicts are never disk-cached.
GT-005 (400, warning)   image_id invalid for project / image missing.
        Recovery: client refreshes project state.
GT-006 (400, warning)   Resolved selection is empty.
        Recovery: select at least one resolvable swatch.
```

- All background QA failures are per-image and isolated: one failed judge call MUST
  NOT abort the generation run (mirrors existing per-selection error isolation in
  `_run_generation`).
- Ledger append failures are logged and MUST NOT block the approval write (D6).
- Retry policy for judge API calls: the existing 3-attempt loop in `VisionJudge`
  applies unchanged, wrapped in a single semaphore slot per judge() call (D3).
- Process restart: `running` run manifests flip to `truncated` on load (D0); the UI
  surfaces the truncation banner (D7).

## Security Considerations

- **Trust boundary**: single-operator internal tool on localhost; no user auth is
  added. The Gemini `X-API-Key` continues to flow per-request from browser
  localStorage and MUST NOT be persisted server-side (existing invariant).
- **Input validation**: approval payloads validate verdict enum, reasons vocabulary,
  and image-belongs-to-project (GT-005). `trust_config.json` values are validated on
  read with safe fallbacks to conservative defaults (bulk locked, cap $10) on parse
  error; each run uses an immutable config snapshot (D0).
- **Blast radius**: worst credible failure is monetary — a gate bug enabling an
  ungated bulk run (~$7/project) or a runaway retry loop. Mitigations: server-side
  gates (not UI-only), an atomic per-run unconsented-spend counter checked before
  each submission, retries bounded per wood slot, worst-case cost shown at consent
  time, and the existing 4-call concurrency semaphore.
- **Data integrity**: `output/.projects/` stays authoritative and irreplaceable —
  projects and signatures MUST NOT be deleted; the D0 migration is non-destructive
  and backward-compatible, never touches signature bytes, and superseded attempt
  images are retained rather than deleted. `labels.json` (calibration, 179 hand
  labels) is frozen; approvals and ledger are separate files. All QA state stays
  under gitignored `output/.qa/`.
- **Prompt injection**: judge inputs are operator-supplied images and fixed rubric
  text; no untrusted third-party text enters prompts.

## Alternatives Considered

1. **Offline operator console (scripts, like `qa_label.py`).** Attractive: zero risk
   to the app, proven pattern. Rejected: duplicates image display/navigation the app
   already has, and a script-side gate is advisory only — the app's generate button
   could still fire ungated runs. Server-side enforcement requires touching the
   backend anyway. <!-- D-002 -->
2. **Automatic numeric graduation gate** (e.g. "3 consecutive rounds at 100%
   agreement unlocks bulk"). Rejected for now: premature to commit thresholds before
   observing real agreement data; manual unlock informed by the ledger achieves the
   same safety with less machinery. MAY be revisited once the ledger has volume.
   <!-- D-003 -->
3. **Approvals derived from calibration labels** (status quo of `qa_eval.py`),
   including one-time seeding of the approval store from accept-labels. Rejected:
   conflates frozen eval ground truth with mutable operational state; no history, no
   timestamps, no UI path; and seeded approvals would grant Stage-A passage to
   replicas the operator never reviewed in the new workflow. <!-- D-011 -->
4. **QA as a separate post-run batch pass** instead of at generation time. Rejected:
   delays verdicts past the moment of maximum context, complicates auto-regeneration,
   and adds an orchestration layer for no cost saving (same judge calls either way).
5. **Positional candidate keys as the trust layer's primary key.** Rejected after
   review: index is assigned in completion order (unbindable under concurrency),
   results are wiped on re-learn, and `version 0` = "current" means a re-learned
   replica inherits its predecessor's approval. Stable image IDs fix all three; the
   candidate-key space remains for offline eval. <!-- D-006 -->
6. **Synchronous QA inside `_run_generation`'s drain loop.** Rejected after review:
   serializes the 4-way-parallel batch whenever any variant retries, and holds the
   run's `done` transition hostage to judge latency/outages. <!-- D-007 -->

## Implementation Plan

Phases are ordered by value-per-risk; each is independently shippable.

1. **Phase 1 — Identity foundation (D0).** `ResultRecord` + `image_id` migration,
   run-manifest module, verdict/record archiving in `archive_current_version`,
   truncation detection on load, `build_selections` moved to `backend/selections.py`.
   Verify: old projects load unchanged and re-save in new format; archive round-trip
   carries records; existing tests green.
2. **Phase 2 — Approval store + gates (the money-saver).**
   `backend/qa/approvals.py` (locked), `trust_config.json`, gate checks (GT-001/002/
   005/006) in `projects_generation.py`, approval endpoints, minimal UI (approve/
   reject on replica, blocking banner, selection-cap error surfacing). Verify: gated
   `POST /generate` returns the right codes; approval flow unblocks; revocation
   doesn't cancel in-flight work.
3. **Phase 3 — Async QA lane + badges (D3).** QA executor, `QaVerdict` persistence,
   single-slot judge semantics, error re-judge, response-model extensions,
   `ResultsGrid` badges + replica verdict + judging states. Verify: generated images
   carry verdicts; judge failure yields GT-004 behavior without touching
   generation_status.
4. **Phase 4 — Reliability ledger + estimate + cost confirm (D5, D6).**
   `reliability.py`, ledger writes on approval, `/qa/reliability`,
   `/generate/estimate` with worst-case band, confirm dialog, reliability panel.
   Verify: agreement/deferral math on synthetic fixtures; estimate matches resolved
   selection size.
5. **Phase 5 — Auto-regeneration loop (D4).** Retry submission from the QA lane,
   attempt records, best-attempt selection with deterministic tie-break, atomic cap
   accounting, GT-003 on manifest. Verify: regenerate-verdict variant retries ≤2;
   cap cancellation recorded; attempts retained on disk.
6. **Phase 6 — Bulk unlock mechanics.** Style-class unlock resolution, Stage C
   behavior, revocation, truncation banner. Verify: unlock/revoke round-trip without
   restart; snapshot semantics honored mid-run.

Go/no-go between phases: all existing QA tests (`tests/qa/`) and app tests green;
ruff clean. Judge prompt iteration and CSV export proceed as separate workstreams
(out of scope).

## Open Questions

1. **Judge cost/latency budget at generation time.** Each variant adds 1–3 judge
   calls (majority vote on low confidence). Estimated cost is small relative to
   image generation but unmeasured in this app path. Needed: observed per-image
   judge cost from Phase 3 telemetry. If material, batch-judging or a cheaper judge
   model MAY be considered. Decider: operator, after Phase 3 data.
2. **Shopify/Matrixify mapping.** How do `(project, wood_name)` pairs map to Shopify
   product handles/SKUs/image positions? Blocks the export script only. Needed: a
   worked example from the live store's Matrixify export. Decider: operator.
3. **Attempt retention at Stage C.** Attempts are kept during Stages A/B
   (<!-- D-012 --> decided); whether bulk-scale retention needs pruning is deferred
   until Stage C volumes are real. Decider: operator, at bulk unlock time.

## References

### Normative

- `docs/qa-pipeline.md` — operator guide to the three-layer QA pipeline.
- `backend/qa/policy.py` — 12-step decision precedence this design feeds
  (`approved_keys`, `replica_approved`).
- `.plans/geometry-checks/01_deterministic-geometry-checks-for-the-judgment-pipeline.rfc.md`
  — geometry measurement + replica-anchor policy (D1) this builds on.

### Informative

- `.plans/graduated-trust-pipeline/rfc-review.md` — four-agent review that drove
  revisions D-006…D-012.
- `docs/superpowers/specs/2026-07-02-judgment-pipeline-design.md` — original judgment
  pipeline design.
- `.plans/geometry-checks/progress-report.md` — validation results (holdout recall
  100%, false-flag 19.2%) and the deferred follow-ups this RFC picks up (OQ-3).
