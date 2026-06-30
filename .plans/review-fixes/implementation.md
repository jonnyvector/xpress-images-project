# Review Fixes — Implementation Plan

## ⚠️ Execution Protocol

A progress report exists at `.plans/review-fixes/progress-report.md`. It lists
every feature for every milestone as a checkbox.

**Mandatory rules for all agents working on this plan:**

1. Before starting a milestone, run `plan-db check-progress --plan "review-fixes"`
   and read its section in the progress report — those current-cutoff
   checkboxes are your spec.
2. Check each box as you complete the feature, not at the end.
3. A milestone is NOT done until every current-cutoff checkbox under it is checked.
4. If you find features missing from the report, add them first.
5. Never declare a phase complete without updating the current focus marker and Summary.
6. Deferred follow-up and superseded/obsolete debt must not count as current blockers.
7. Execution is batch-by-batch (D-004): one commit per phase/milestone group,
   run lint + tests, check in with the user before the next batch.

---

Turns the 20-finding codebase review
(`docs/superpowers/specs/2026-06-30-codebase-review-findings.md`) into an
executable, batch-by-batch cleanup. Every batch is independently shippable and
behavior-preserving unless explicitly noted.

## Architecture

This is a cleanup plan, not a feature. No new subsystems; the system shape is
unchanged. Work falls into four kinds:

- **Safety guard** (F1) — make irreversible mass deletion impossible by accident.
- **Backend correctness** (F2, F19) — make concurrent result writes lock-safe
  and keep the errors list consistent.
- **Dedup / responsibility** (F4, F5, F6, F10, F7, F8b) — remove dead code,
  collapse triplicated logic behind helpers, and move misplaced logic to the
  module that owns the responsibility.
- **Consistency / polish** (F3, F11, F13, F14, F15, F16, F17, F18) — kill
  patch-work residue and align patterns.

### Key Constraints

| Constraint | Impact |
|-----------|--------|
| Thought signatures are irreplaceable | No batch touches `signature.bin`, `base_door.bin`, version archives, or on-disk project layout. |
| Behavior-preserving | Refactors must not change generation output or API contracts. The one behavior change (F1 guard) is intentional and approved (D-001). |
| Generation prompts are sacred | F12 (davenport plank count) is **deferred** pending user confirmation — no prompt edits in this plan (D-002). |
| Thin test net | Only 5 tests today. Backend correctness/dedup batches add targeted tests so the refactor is verifiable (addresses F20). |

### Boundaries

Two responsibility seams are formalized by this plan:

- **`_generate_for_selection` (worker)** — single dispatch point for "given a
  selection, call the right generator method." Owns the
  reference-vs-signature branch. Removes the F6 copy-paste between
  `_run_generation` and `_run_retry`.
- **`_generate_with_retry` (generator)** — single retry/backoff/exception→result
  wrapper. Owns transient-error classification (429/quota/signature). Removes
  the F5 triplication across `learn_door_style`, `generate_variation`,
  `generate_variation_from_reference`.
- **Filename parsing module** (F10) — `_extract_wood_name`/`_match_color_key`
  move out of the `projects_media` router into `materials.py` (or a new
  `filename_parsing.py`). The router keeps only HTTP concerns. New/!moved
  module gets a module-level docstring stating what it owns.
- **`LibraryCard` component** (F7) — one card renderer used by both the learned
  and imported grids in `DoorLibrary`.
- **UploadStep decomposition** (F8b) — split into `UploadDropzone`, `StyleForm`,
  `LearnControls` sub-components; `UploadStep` becomes the orchestrator.

### Observability

Low relevance — no transport/provider changes. The one runtime-behavior batch
(F2) should keep the existing `[generate_variation]`/`[learn_door_style]`
stderr logs and add a structured note when a result write is dropped because the
project was deleted mid-generation (already partially handled by the
`project is None` guards).

---

## Phases

### Phase 1: Safety (do first, ship alone)

**Goal:** Accidental mass deletion of all projects is impossible.

#### M1: Guard "Reset All" (F1)
- **Dependencies:** none
- **Effort:** S
- **Tasks:**
  1. <!-- D-001 --> Replace the bare `handleResetAll` click path in
     `frontend/src/components/Layout.tsx` with a type-to-confirm dialog
     (modal or `prompt`) requiring the user to type `DELETE` before any
     deletion runs.
  2. Verify cancel / wrong-input paths perform **no** deletion.
  3. Manual check: button no longer deletes on a single click.

### Gate 1→2
- [ ] Reset All requires typed confirmation; cancel deletes nothing.
- [ ] `npm run lint` + frontend build clean.

---

### Phase 2: Backend low-risk cleanups (one commit)

**Goal:** Patch-work residue and dead code removed; lint + tests stay green.

#### M2: Mechanical backend cleanups (F3, F4, F11, F15, F18)
- **Dependencies:** none
- **Effort:** S
- **Tasks:**
  1. F3 — add `import re` at top of `backend/routers/projects_media.py`;
     replace all five `__import__("re")` call sites.
  2. F4 — delete `DoorGenerator.generate_batch` (`generator.py:765`) and the
     now-unused `Callable` import if nothing else uses it.
  3. F11 — change `STYLES` annotation in `backend/styles/catalog.py:3` to
     `dict[str, dict[str, Any]]` (or a `TypedDict`); add the `Any` import.
  4. F15 — hoist the local `from backend.worker import start_learning` in
     `projects_generation.py:24` to a module-level import alongside the others.
  5. F18 — remove the dead `if upload_path.exists() and not
     project.upload_filename: pass` block in `state.py:88`.
- **Verify:** `npm run lint`, `uv run pytest -q` both green; `grep -rn
  '__import__' backend` returns nothing.

### Gate 2→3
- [ ] ruff clean, 5/5 tests pass.
- [ ] No `__import__` or `generate_batch` references remain.

---

### Phase 3: Backend correctness (one commit)

**Goal:** Concurrent generation writes are lock-safe; errors stay consistent.

#### M3: Lock-guarded result writes (F2)
- **Dependencies:** none (independent of M2)
- **Effort:** M
- **Tasks:**
  1. RED: Add a concurrency test (`tests/test_worker_concurrency.py`) that
     drives many simulated result writes against a `ProjectStore` and asserts
     `generation_completed` equals the number of writes and no results are lost.
  2. GREEN: Add a store method that mutates under `self._lock` — e.g.
     `record_result(project_id, wood_name, image_data=None, error=None)` that
     appends to results or errors and increments `generation_completed`
     atomically, then persists.
  3. GREEN: Refactor `_run_generation` (and the `except` branch) in
     `worker.py` to call the new store method instead of mutating the shared
     `ProjectState` and calling `store.save` directly.
  4. REFACTOR: Confirm `_run_retry` writes go through a lock-safe path too.

#### M4: Consistent retry errors (F19)
- **Dependencies:** M3
- **Effort:** M
- **Tasks:**
  1. RED: Test that a failed retry followed by a successful retry on the same
     index leaves exactly one entry (the success) and no stale error.
  2. GREEN: Key/clear errors by result index in `_run_retry` so a prior error
     for that index is removed before appending/replacing.
  3. Minor: align the `retry_result` router gate (`projects_generation.py:86`)
     so reference-based styles aren't rejected for lacking a signature when
     `start_retry` can handle them via `base_door.bin`.

### Gate 3→4
- [ ] New concurrency + retry tests pass; full suite green.
- [ ] `generation_completed` accounting verified under parallel writes.

---

### Phase 4: Backend dedup (one commit)

**Goal:** Triplicated/copy-pasted logic collapsed behind owned seams.

#### M5: Retry wrapper (F5)
- **Dependencies:** none (M3 helps but not required)
- **Effort:** M
- **Tasks:**
  1. RED: Add a generator test with a mocked `genai` client that returns a
     429 once then succeeds; assert the wrapper retries and returns the image.
  2. GREEN: Extract `_generate_with_retry(contents, config, *, label) ->
     GenerationResult` and route all three methods (`learn_door_style`,
     `generate_variation`, `generate_variation_from_reference`) through it.
  3. REFACTOR: Verify signature-extraction and error mapping unchanged.

#### M6: Generate-one helper (F6)
- **Dependencies:** M5 (shared shape)
- **Effort:** M
- **Tasks:**
  1. GREEN: Extract `_generate_for_selection(generator, sel, *, door_style,
     aspect_ratio, ...)` and call it from both `_run_generation._generate_one`
     and `_run_retry`.
  2. Verify reference-vs-signature branching identical to before.

#### M7: Move filename parser (F10)
- **Dependencies:** none
- **Effort:** S/M
- **Tasks:**
  1. RED: Add `tests/test_filename_parsing.py` covering the documented cases
     (model-code prefixes, `_rtf` suffix, trailing version numbers).
  2. GREEN: Move `_extract_wood_name`/`_match_color_key`/the regexes to
     `materials.py` (or new `backend/filename_parsing.py` with a module
     docstring); import into `projects_media`.

### Gate 4→5
- [ ] All three generator/worker call paths produce identical prompts/results
      (spot-check against pre-refactor behavior).
- [ ] Parser tests pass; router imports the moved functions.

---

### Phase 5: Frontend correctness & consistency (one commit)

**Goal:** Polling/refresh consistent; stale form state fixed; api helper deduped.

#### M8: Frontend consistency fixes (F9, F14, F13, F8a)
- **Dependencies:** none
- **Effort:** M
- **Tasks:**
  1. F9 — replace the recursive `setTimeout` retry poll in `ResultsGrid`
     with `usePollingTask` (gets unmount cleanup + error cap for free).
  2. F14 — `ResultsGrid.handleDiscard` uses `getProject(id)` instead of
     `listProjects()` + `.find()`.
  3. F13 — extract an `authHeaders()` / `requestRaw()` helper in `api.ts`;
     use it in `deleteProject`, `discardResult`, `getResultsZip`,
     `saveResultsToFolder`.
  4. F8a — sync UploadStep's mirrored fields (`materialType`, `doorStyle`,
     `styleNotes`, `geminiModel`, …) from props via effects so a version
     restore / external update doesn't leave stale form values.
- **Verify:** frontend build/typecheck clean; manual smoke of retry, discard,
  zip download, and version-restore-then-check-form.

### Gate 5→6
- [ ] No `listProjects()` in poll/discard paths; retry uses the hook.
- [ ] Restoring a version updates the visible form fields.

---

### Phase 6: Frontend structure (one or two commits)

**Goal:** Card and upload duplication collapsed into owned components.

#### M9: Extract LibraryCard (F7)
- **Dependencies:** none
- **Effort:** M
- **Tasks:**
  1. GREEN: Create `LibraryCard` with the shared markup (thumb, inline rename,
     delete); use it in both the learned and imported grids.
  2. REFACTOR: Lift the imported-sections IIFE (`DoorLibrary.tsx:223`) into a
     computed value or helper.

#### M10: Decompose UploadStep (F8b)
- **Dependencies:** M8 (F8a sync lands first so the split inherits correct state handling)
- **Effort:** L
- **Tasks:**
  1. GREEN: Split into `UploadDropzone`, `StyleForm`, `LearnControls`;
     `UploadStep` orchestrates. Each new file gets a module-level comment
     describing what it owns.
  2. Verify learn flow, drag/drop, polling-resume, and error-retry all behave
     identically.

### Gate 6→7
- [ ] DoorLibrary card markup defined once; both grids render correctly.
- [ ] UploadStep behavior unchanged after decomposition.

---

### Phase 7: Cosmetic polish (one commit, optional last)

**Goal:** Dialog and styling consistency.

#### M11: Dialog + inline-style cleanup (F16, F17)
- **Dependencies:** M1 (F1 sets the confirm pattern), M9/M10
- **Effort:** L
- **Tasks:**
  1. F16 — make destructive-action confirmations consistent (align on the
     pattern chosen for F1).
  2. F17 — move repeated/structural inline `style={{…}}` objects in
     `ResultsGrid`, `UploadStep` (post-split), `SignatureHistory`, `SwatchGrid`
     into CSS classes. Cosmetic; verify visually.

### Gate 7→done
- [ ] Visual parity; build/lint clean; full test suite green.

---

## Deferred / follow-up (not current blockers)

- **F12 (davenport plank count)** — deferred pending user confirmation of the
  intended count (D-002). Generation-behavior change; do not edit prompts until
  confirmed. *Not counted as a current blocker.*
- **F20 (broader coverage)** — additional tests beyond those added in Phases
  3–4 are ongoing/opportunistic, not a blocker for this plan.

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation | Owner |
|------|----------|------------|------------|-------|
| F5/F6 refactor silently changes a prompt → different generation output | high | medium | Diff prompt strings before/after; mocked-client test; spot-check one real generation per affected path | impl |
| F2 store-method refactor introduces a deadlock (lock held during disk I/O) | medium | low | Keep the existing pattern of saving under lock (already does); concurrency test; no nested lock acquisition | impl |
| F8b/F10 moves break imports | low | medium | Lint + build catch import errors immediately | impl |
| F17 inline-style move changes layout | low | medium | Visual check per component; cosmetic-only, easy rollback | impl |

---

## Escape Hatches

1. **If an F5/F6 refactor can't be proven behavior-preserving:** ship the
   tests + dead-code removal, revert the extraction, leave the duplication as a
   documented follow-up rather than risk generation drift.
2. **If F8b decomposition balloons:** ship F8a (the stale-state fix) and the
   LibraryCard extraction; defer the full UploadStep split.

---

## Validation Commands

```bash
npm run lint                 # ruff check backend/
uv run pytest -q             # backend tests
cd frontend && npm run build # tsc typecheck + vite build
```

---

## Decisions

Canonical decisions live in `.plans/review-fixes/plan.db`:

```bash
npx tsx /Users/jonathanhicks/.claude/skills/planner/scripts/plan-db.ts query-decisions --plan review-fixes
```

- <!-- D-001 --> F1 → type-to-confirm guard on Reset All.
- <!-- D-002 --> F12 → deferred pending user confirmation.
- <!-- D-003 --> Scope includes F8b and F17.
- <!-- D-004 --> Execution: batch-by-batch, commit + lint/test + check-in per batch.
