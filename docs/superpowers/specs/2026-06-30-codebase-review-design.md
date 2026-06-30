# Full Codebase Review & Cleanup — Design

**Date:** 2026-06-30
**Status:** Approved (brainstorming) → ready for review sweep

## Goal

The Cabinet Door Generator was built incrementally ("patch-worked") and has
accumulated jank. We want to **review the entire codebase, produce a prioritized
findings report, then fix what the user approves** — leaving the app behaving the
same but with cleaner, more maintainable code.

Outcome chosen by user: **Review first, then fix.** Nothing changes until the
findings list is triaged and approved.

## Review dimensions (all four, weighted equally across the codebase)

1. **Correctness / bugs** — real bugs, race conditions, error-handling gaps,
   silent failures — especially around generation and thought signatures.
2. **Structure / organization** — oversized files, unclear boundaries, duplicated
   logic, tangled responsibilities.
3. **Consistency / style** — inconsistent naming/patterns, dead code, leftover
   patch-work, formatting drift.
4. **Frontend UX jank** — polling glitches, stale state, loading/error states,
   cross-tab issues.

No single hotspot — review the whole thing evenly and let findings reveal where
the mess concentrates.

## Method

**Approach A: single structured pass, by area.** One reviewer (main session),
no multi-agent fan-out, no code changes during the review. Six passes:

1. **Generation core** — `backend/generator.py` (815), `materials.py`, `models.py`
2. **Worker & state** — `backend/worker.py` (549), `state.py` (404)
3. **Routers** — `backend/app.py` + `routers/*` (crud, generation, media,
   versions, common, swatches)
4. **Swatch / catalog data** — `backend/styles/catalog.py` (1022),
   `swatches/*.json`, `scripts/remove_watermarks.py`
5. **Frontend state & data flow** — `ProjectsContext.tsx`, `api.ts`,
   `usePollingTask.ts`, `types.ts`
6. **Frontend components** — `UploadStep` (411), `ResultsGrid` (377),
   `DoorLibrary` (309), and the remaining components

## Findings report format

Produced at `docs/superpowers/specs/2026-06-30-codebase-review-findings.md`.

Each finding:

> **[ID] Severity · Dimension · `file:line`** — one-line problem → proposed fix
> (effort: S/M/L)

Severity scale (sorted P0 → P3):

- **P0** — correctness / data-loss risk
- **P1** — real bug or sharp edge
- **P2** — structural debt
- **P3** — consistency / polish

The report ends with a **suggested fix batching** section: related fixes grouped
into safe, independently-shippable commits.

## Cleanup flow & safety

- **Before any fix:** confirm `tests/` runs green as a regression net. If coverage
  is thin around a fix, note where added tests would de-risk it.
- **Fixing only after triage:** the user picks which findings/batches to do.
- Fixes land as **small, focused commits**; riskier changes flagged for a
  check-in before being made.
- **Behavior-preserving** unless the user explicitly approves a behavior change.

### Sacred — never touched

- Saved project state and thought-signature files (irreplaceable).
- Project deletion (never delete projects).

### Out of scope

- The two planning docs stay as-is: `PLAN-cross-tab-polling.md` (completed fix
  log) and `doorupdates.md` (domain swatch descriptions).
- No unrelated refactoring beyond what the findings justify.

## Deliverables

1. A triaged, prioritized findings report.
2. A sequence of clean, focused commits implementing the approved fixes.
3. App behaves the same; code is de-janked.
