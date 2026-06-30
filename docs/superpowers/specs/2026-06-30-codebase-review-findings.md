# Codebase Review — Findings Report

**Date:** 2026-06-30
**Scope:** Full codebase (backend + frontend), all four dimensions
(correctness / structure / consistency / UX).
**Method:** Single structured pass (Approach A). No code changed.

## Baseline

- `ruff check backend/` — **passes clean**.
- `pytest` — **5/5 pass** (~5s). Coverage is thin: only `materials`,
  `project_store`, and an API smoke test. Nothing exercises worker concurrency,
  the generator (retry/extraction), media/version routes, or the frontend.
- Note: ruff does **not** flag the `__import__("re")` hack (F3) — it's valid
  Python, just ugly.

## Severity scale

- **P0** — correctness / data-loss risk
- **P1** — real bug or sharp edge
- **P2** — structural debt
- **P3** — consistency / polish

Effort: **S** (<30 min) · **M** (~1–2 h) · **L** (half-day+).

---

## P0 — Data loss

### F1 · UX/correctness · `frontend/src/components/Layout.tsx:64`, `:106`
**"Reset All" deletes every project with no confirmation.** `handleResetAll`
loops `api.deleteProject(p.id)` over **all** projects, then creates a fresh
"Door 1". The button sits in the sidebar (`className="danger"`) and fires on a
single click — no confirm, no undo. This destroys every project's
thought-signature, which is **irreplaceable**.
→ **Fix:** add a type-to-confirm dialog ("type DELETE"), or remove the button
entirely. At minimum a `window.confirm`. **Effort: S.** *(Highest priority.)*

---

## P1 — Real bugs

### F2 · correctness · `backend/worker.py:199`, `backend/state.py:170`
**Concurrent generation mutates shared `ProjectState` outside the store lock.**
`store.get()` returns the shared object; up to 4 pool threads run
`project.generation_completed += 1` (a read-modify-write → lost-update race) and
`project.results.append(...)` + `store.save()` concurrently, while
`_save_project` iterates `project.results`. The progress counter can drift and
every thread re-serializes the whole result set (O(n²) disk writes per batch).
Self-heals to `done` via the `finally` block, so blast radius is limited.
→ **Fix:** funnel result/counter mutations through a store method that holds
`self._lock` (e.g. `store.record_result(project_id, wood_name, data, error)`).
**Effort: M.** *(Coverage: add a concurrency test — see F20.)*

### F19 · correctness · `backend/worker.py:392`, `:398`
**Stale retry errors accumulate.** `_run_retry` appends to `project.errors` on a
failed retry but never removes the prior error for that index; on success it
replaces `results[idx]` but leaves any earlier error entry in the list. The
errors panel can show stale/duplicate entries.
→ **Fix:** key errors by result index (or clear the matching error before
appending/replacing). **Effort: M.**

---

## P2 — Structural debt

### F3 · consistency · `backend/routers/projects_media.py:193`, `:198`, `:200`, `:227`, `:239`
**`__import__("re")` instead of `import re`.** Five call sites use the runtime
`__import__` hack. Clear patch-work residue.
→ **Fix:** add `import re` at module top, replace all five. **Effort: S.**

### F4 · structure · `backend/generator.py:765`
**Dead code: `DoorGenerator.generate_batch` (51 lines).** No callers anywhere
(worker uses `learn_door_style` + `generate_variation` directly). Its
`progress_callback` is the only use of the `Callable` import.
→ **Fix:** delete the method and the now-unused import. **Effort: S.**

### F5 · structure · `backend/generator.py:445`, `:599`, `:707`
**Triplicated retry/backoff loop.** `learn_door_style`, `generate_variation`,
and `generate_variation_from_reference` each contain a near-identical
`for attempt in range(MAX_RETRIES)` block with the same 429/quota/sleep handling
and `Exception → GenerationResult` mapping.
→ **Fix:** extract `_generate_with_retry(contents, config, *, label) ->
GenerationResult`. **Effort: M.** *(Behavior-preserving; this is the API call
path — verify carefully, ideally with a mocked client test first.)*

### F6 · structure · `backend/worker.py:166`, `:355`
**Duplicated generate-one dispatch.** The `if use_base_door_reference and
reference_image: generate_variation_from_reference(...) else
generate_variation(...)` block is copy-pasted between `_run_generation._generate_one`
and `_run_retry`.
→ **Fix:** extract `_generate_for_selection(generator, sel, *, ...)`. **Effort: M.**

### F7 · structure · `frontend/src/components/DoorLibrary.tsx:142`, `:234`
**Library-card markup duplicated (~70 lines).** The card (thumb + inline rename +
delete) is repeated almost verbatim for the "learned" grid and the "imported"
grid, plus an IIFE-in-JSX (`:223`) for the imported sections.
→ **Fix:** extract a `<LibraryCard>` component; lift the imported-sections logic
out of the IIFE. **Effort: M.**

### F8 · structure/correctness · `frontend/src/components/UploadStep.tsx`
**411-line "god component."** Mixes material/product toggles, file upload +
drag/drop, the style form, learn-polling, and error-retry. Also a subtle bug:
local `useState` mirrors of project fields (`materialType`, `doorStyle`,
`styleNotes`, `geminiModel`, …) only initialize once, so an external update
(e.g. **version restore** changing `door_style`/`material_type`) leaves the form
showing **stale values** until remount.
→ **Fix:** (a) sync the mirrored fields from props via effects (or derive from
props), (b) decompose into `UploadDropzone` / `StyleForm` / `LearnControls`.
**Effort: M** (sync) **/ L** (decompose).

### F9 · structure/UX · `frontend/src/components/ResultsGrid.tsx:45`
**Ad-hoc recursive `setTimeout` polling for retry.** `handleRetry` rolls its own
`setTimeout(poll, 2000)` loop instead of the shared `usePollingTask` hook — no
unmount cleanup (the timer keeps firing after the component unmounts) and no
error cap.
→ **Fix:** route retry through `usePollingTask` like the other flows. **Effort: M.**

### F10 · structure · `backend/routers/projects_media.py:203`–`:255`
**Filename-parsing heuristic lives in a router.** `_extract_wood_name` /
`_match_color_key` (~50 lines) are domain logic, not HTTP concerns.
→ **Fix:** move to `materials.py` (or a `filename_parsing.py`); keeps the router
thin and makes the heuristic unit-testable. **Effort: S/M.**

---

## P3 — Consistency / polish

### F11 · consistency · `backend/styles/catalog.py:3`
`STYLES` annotated `dict[str, dict[str, str]]` but values include bools
(`use_base_door_reference: True`) and the structure is heterogeneous.
→ **Fix:** `dict[str, dict[str, Any]]` or a `TypedDict`. **Effort: S.**

### F12 · correctness (content) · `backend/styles/catalog.py:11` vs `:17`
`davenport` `learn_prompt` says **"FOUR vertical … planks"**; `variation_hint`
says **"THREE … planks"**. Likely a real prompt inconsistency.
→ **Fix:** user confirms the intended count, then align. **Effort: S.**
*(Domain content — touches generation; user decides, behavior-changing.)*

### F13 · consistency · `frontend/src/api.ts:42`, `:89`, `:97`, `:114`
`deleteProject`, `discardResult`, `getResultsZip`, `saveResultsToFolder`
re-implement the API-key header + error handling instead of sharing a helper
(the JSON `request()` can't serve blob/204 responses, but an `authHeaders()` /
`requestRaw()` helper could).
→ **Fix:** extract a small raw-fetch helper. **Effort: S.**

### F14 · consistency · `frontend/src/components/ResultsGrid.tsx:78`
`handleDiscard` uses `listProjects()` then `.find()`, while the rest of the app
moved to `getProject(id)` (the cross-tab polling refactor). Broad fetch +
re-render.
→ **Fix:** use `getProject(project.id)`. **Effort: S.**

### F15 · consistency · `backend/routers/projects_generation.py:24`
Local `from backend.worker import start_learning` inside the handler while
siblings (`start_generation`, `start_retry`) import at module top. No
circular-import reason.
→ **Fix:** move to top-level import. **Effort: S.**

### F16 · UX consistency · `DoorLibrary.tsx:33,40`, `UploadStep.tsx:359`, `Layout.tsx`
Native `window.confirm`/`window.alert` used inconsistently — DoorLibrary delete
and UploadStep re-learn confirm, but the most destructive action (Reset All,
F1) does not. Pick one pattern (styled modal or consistent `confirm`).
**Effort: S–M** (fold into F1).

### F17 · consistency · ResultsGrid / UploadStep / SignatureHistory / SwatchGrid
Large inline `style={{…}}` objects scattered and mixed with CSS classes.
→ **Fix:** move repeated/structural styles to CSS classes. **Effort: L** (cosmetic).

### F18 · consistency · `backend/state.py:88`–`91`
Dead no-op: `if upload_path.exists() and not project.upload_filename: pass`.
→ **Fix:** remove. **Effort: S.**

### F20 · coverage · `tests/`
Only 5 tests; no coverage of worker concurrency (F2), generator retry/extraction
(F5), media/version routes, or the wood-name parser (F10).
→ **Fix:** add targeted tests alongside the F2/F5/F10 fixes to lock behavior.
**Effort: ongoing.**

### Minor note (not numbered)
`retry_result` (`projects_generation.py:86`) gates on `project.has_signature`
even for `use_base_door_reference` styles, which retry from `base_door.bin`
rather than a signature. Low impact (those styles still have a signature today),
but the gate is inconsistent with `start_retry`'s logic.

---

## Suggested fix batching

Each batch is independently shippable and behavior-preserving (except F12, which
is a deliberate content change). Ordered by value-to-risk.

1. **Safety first (S):** F1 (Reset All confirm/remove). Ship alone, immediately.
2. **Backend dead code + jank (S):** F3 (`import re`), F4 (delete `generate_batch`),
   F15 (import style), F18 (dead no-op), F11 (type annotation). All low-risk;
   lint + tests must stay green.
3. **Backend correctness (M):** F2 (lock-guarded result writes) + F19 (retry
   error keying), with a new concurrency test (F20).
4. **Backend dedup (M):** F5 (retry helper) + F6 (generate-one helper) +
   F10 (move filename parser), with tests for the parser and a mocked-client
   generator test.
5. **Frontend correctness/consistency (M):** F9 (retry via `usePollingTask`),
   F14 (`getProject`), F13 (api helper), F8a (sync stale form state).
6. **Frontend structure (M/L):** F7 (`LibraryCard`), F8b (decompose UploadStep).
7. **Cosmetic (L, optional):** F16/F17 (dialog + inline-style cleanup).
8. **Content (S, user-confirmed):** F12 (davenport plank count).

## Sacred — untouched in every batch

Saved project state, `signature.bin` / `base_door.bin` / version archives, and
project deletion semantics. No batch alters on-disk project data or the
generation prompts (except F12, only with user sign-off).
