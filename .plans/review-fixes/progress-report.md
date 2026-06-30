# Review Fixes — Progress Report

> Auto-generated from the implementation plan. Canonical source of truth for
> what is done and what remains. Check each box as the feature lands — never
> mark a milestone complete until every current-cutoff checkbox under it is
> checked.

> Current focus: Phase 5 — Frontend correctness & consistency

## Phase 1: Safety

### M1: Guard "Reset All" (F1)
Source: `frontend/src/components/Layout.tsx:64`, `:106`

- [x] Reset All opens a type-to-confirm dialog requiring the literal text `DELETE`
- [x] Typing the wrong text (or cancelling) performs zero deletions
- [x] Correct confirmation deletes all projects then recreates "Door 1" (existing behavior preserved)
- [x] Single click no longer triggers any deletion

## Phase 2: Backend low-risk cleanups

### M2: Mechanical backend cleanups (F3, F4, F11, F15, F18)
Source: `routers/projects_media.py`, `generator.py`, `styles/catalog.py`, `routers/projects_generation.py`, `state.py`

- [x] `import re` added at top of `projects_media.py`; all 5 `__import__("re")` sites replaced (F3)
- [x] `DoorGenerator.generate_batch` removed; unused `Callable` import dropped if orphaned (F4)
- [x] `STYLES` annotation changed to `dict[str, dict[str, Any]]` with `Any` imported (F11)
- [x] `start_learning` import hoisted to module top in `projects_generation.py` (F15)
- [x] Dead `upload_path` no-op block removed from `state.py:88` (F18)
- [x] `grep -rn '__import__' backend` returns nothing; ruff + pytest green

## Phase 3: Backend correctness

### M3: Lock-guarded result writes (F2)
Source: `worker.py:199`, `state.py:170`

- [x] Concurrency test asserts `generation_completed` == number of writes with no lost results
- [x] Store gains a lock-held write method (e.g. `record_result`) that appends + increments + persists atomically
- [x] `_run_generation` (success and except branches) routes writes through the store method instead of mutating shared state
- [x] `_run_retry` result/error writes go through a lock-safe path
- [x] No nested lock acquisition introduced (no deadlock)

### M4: Consistent retry errors (F19)
Source: `worker.py:392`, `:398`, `routers/projects_generation.py:86`

- [x] Test: failed-then-successful retry on same index leaves exactly one (success) entry, no stale error
- [x] `_run_retry` clears/keys the prior error for an index before appending or replacing
- [x] `retry_result` router gate no longer rejects reference-based styles for missing signature when `start_retry` can handle them

## Phase 4: Backend dedup

### M5: Retry wrapper (F5)
Source: `generator.py:445`, `:599`, `:707`

- [x] Mocked-client test: 429-then-success retries and returns the image
- [x] `_generate_with_retry(contents, config, *, label)` extracted (as `_call_with_retry`)
- [x] `learn_door_style` routes through the wrapper with identical behavior
- [x] `generate_variation` routes through the wrapper with identical behavior
- [x] `generate_variation_from_reference` routes through the wrapper with identical behavior
- [x] Prompt strings + signature extraction unchanged (diffed before/after)

### M6: Generate-one helper (F6)
Source: `worker.py:166`, `:355`

- [x] `_generate_for_selection(generator, sel, *, ...)` extracted
- [x] `_run_generation._generate_one` calls the helper
- [x] `_run_retry` calls the helper
- [x] Reference-vs-signature branching identical to pre-refactor

### M7: Move filename parser (F10)
Source: `routers/projects_media.py:203`–`:255`

- [x] `tests/test_filename_parsing.py` covers model-code prefixes, `_rtf` suffix, trailing version numbers
- [x] `_extract_wood_name`/`_match_color_key`/regexes moved out of the router into a module with a docstring
- [x] `projects_media` imports the moved functions; router holds only HTTP concerns

## Phase 5: Frontend correctness & consistency

### M8: Frontend consistency fixes (F9, F14, F13, F8a)
Source: `ResultsGrid.tsx:45`, `:78`, `api.ts:42`/`89`/`97`/`114`, `UploadStep.tsx`

- [ ] `ResultsGrid` retry uses `usePollingTask` (unmount cleanup + error cap), no recursive `setTimeout` (F9)
- [ ] `handleDiscard` uses `getProject(id)` instead of `listProjects()` + find (F14)
- [ ] `authHeaders()`/`requestRaw()` helper added in `api.ts` and used by the 4 raw-fetch functions (F13)
- [ ] UploadStep mirrored fields sync from props via effects (F8a)
- [ ] Restoring a version updates visible form fields (no stale state)

## Phase 6: Frontend structure

### M9: Extract LibraryCard (F7)
Source: `DoorLibrary.tsx:142`, `:234`

- [ ] `LibraryCard` component created with shared markup (thumb, inline rename, delete)
- [ ] Learned grid renders via `LibraryCard`
- [ ] Imported grid renders via `LibraryCard`
- [ ] Imported-sections IIFE lifted to a computed value/helper

### M10: Decompose UploadStep (F8b)
Source: `UploadStep.tsx` (411 lines)

- [ ] `UploadDropzone` extracted (drag/drop + file input) with module comment
- [ ] `StyleForm` extracted (style name/type/corner/notes/model fields) with module comment
- [ ] `LearnControls` extracted (learn button, maple toggle, learn polling) with module comment
- [ ] `UploadStep` orchestrates the sub-components
- [ ] Learn flow, drag/drop, polling-resume, and error-retry behave identically

## Phase 7: Cosmetic polish

### M11: Dialog + inline-style cleanup (F16, F17)
Source: `DoorLibrary.tsx`, `UploadStep.tsx`, `Layout.tsx`, `ResultsGrid.tsx`, `SignatureHistory.tsx`, `SwatchGrid.tsx`

- [ ] Destructive-action confirmations use a consistent pattern (aligned with F1)
- [ ] Repeated/structural inline styles in `ResultsGrid` moved to CSS classes
- [ ] Repeated/structural inline styles in `UploadStep` (post-split) moved to CSS classes
- [ ] Repeated/structural inline styles in `SignatureHistory` + `SwatchGrid` moved to CSS classes
- [ ] Visual parity verified per component

## Deferred follow-up

- [ ] F12 (davenport plank count) — pending user confirmation of intended count (D-002); generation-behavior change, do not edit prompts until confirmed
- [ ] F20 (broader test coverage beyond Phases 3–4) — opportunistic, not a blocker

## Superseded/obsolete checklist debt

_(none)_

## Summary
- Total features (current cutoff): 50
- Completed: 31
- Remaining: 19
- Current cutoff blockers: 19
- Accepted/deferred follow-up: 2
- Superseded/obsolete checklist debt: 0
