# Approve All (Variants) — Design

**Date:** 2026-07-13
**Status:** Approved (brainstorming) → ready for implementation plan

## Goal

Approving every generated variant image one click at a time is painstaking,
especially for doors the operator has already fully vetted. This adds an
"Approve All" action that bulk-approves every not-yet-decided variant for a
door in one click, so the Coverage page's "Approved" progress (added in
`docs/superpowers/specs/2026-07-13-coverage-approval-shopify-status-design.md`)
reflects it immediately without per-image clicking.

## Decisions (from brainstorming)

- **Where:** two places, both already showing per-image Approve/Reject
  controls — the project's own Results grid (`ResultsGrid.tsx`) and the
  cross-project Review queue (`ReviewQueue.tsx`, per-project section).
- **Scope:** variants only, never the replica. Targets every variant with no
  decision on record yet, regardless of the QA judge's own verdict
  (pass/regenerate/needs_human/pending) — the operator's bulk approval
  overrides/ignores the judge's internal flag by design.
- **Prior rejections:** left untouched. Approve All only fills in undecided
  variants; a variant already explicitly rejected stays rejected until
  individually re-reviewed.
- **Confirmation:** none — fires immediately on click. Approvals aren't
  destructive (any variant can still be individually re-reviewed after), so a
  confirm dialog would just be friction for the exact painless workflow this
  feature exists to provide.
- **Implementation approach:** reuse the existing single-image
  `POST /projects/{id}/approvals` endpoint via a sequential frontend loop —
  no new backend endpoint. See Architecture.

## Architecture

```
ResultsGrid.tsx   ─┐
                    ├─►  ApproveAllButton (shared)  ──►  api.setApproval() × N, sequential
ReviewQueue.tsx   ─┘                                         │
                                                               ▼
                                              existing POST /projects/{id}/approvals
                                              (backend/routers/qa.py, unchanged)
```

No backend changes. `ApproveAllButton` is a new shared frontend component
that, given a project id and a list of target `image_id`s, calls the
existing `api.setApproval(projectId, imageId, 'approved')` once per id, **in
sequence** (awaiting each call before starting the next) rather than in
parallel. Sequential execution is a deliberate choice: `ProjectStore`'s
write path (`store.save()`) has no proven safety under concurrent writes to
the same project, and each `setApproval` call ends with one such save.
Running the calls one at a time — the same as if the operator clicked
Approve N times in a row very quickly — sidesteps that risk entirely rather
than introducing a new concurrent-write path into `ProjectStore` that has
never had to exist before this feature.

This reuses 100% of the existing single-image approval logic (image-ownership
validation, `ApprovalStore` write, reliability-ledger append) with zero new
backend surface to write or test.

## Component: `ApproveAllButton`

**Props:** `projectId: string`, `imageIds: string[]` (the precomputed target
list — the caller decides what's "undecided"), `onDone: () => void` (called
once after the run finishes, regardless of outcome, so the caller can
refresh its own state).

**Behavior:**
- Renders nothing if `imageIds.length === 0` (nothing to approve).
- Otherwise renders a button labeled `Approve All (N)` where N is
  `imageIds.length`.
- On click: disables itself, then calls `api.setApproval(projectId, id,
  'approved')` for each id in order, catching and counting individual
  failures without stopping the loop. While running, the label shows live
  progress: `Approving… (k/N)`.
- When the loop finishes: re-enables (implicitly removed if the caller's
  refresh now reports 0 remaining), calls `onDone()`, and if any calls
  failed, shows an inline message: `${succeeded}/${N} approved — ${failed}
  failed, click to retry` (clicking again re-runs against the same
  `imageIds` list; already-approved ones simply get resubmitted as a no-op
  since setting an existing `approved` verdict is harmless and idempotent).

## Call sites

**`ResultsGrid.tsx`** — next to the existing "Wood Variations (N)" header.
Target list: `project.results` entries whose `verdicts.get(image_id)` (the
component's existing local approvals map, already populated via
`api.listApprovals`) is neither `'approved'` nor `'rejected'`.
`onDone` calls the existing `refreshApprovals()`.

**`ReviewQueue.tsx`** — next to each project section's `<h3>{p.project_name}</h3>`.
Target list: that section's `p.variants.map(v => v.image_id)` — by
construction (the `/api/qa/review-queue` endpoint only lists undecided,
judged items) every entry here is already undecided, so no additional
filtering is needed. `onDone` calls the existing `onChanged()` (refreshes
the queue and syncs any open project tabs).

## Error handling

- Per-item failures don't abort the loop — the next id is still attempted.
  This matters because a single stale/renamed image reference shouldn't
  block approving 33 other perfectly fine variants.
- The button disables itself only for its own run; the existing per-variant
  Approve/Reject buttons remain independently clickable during a bulk run —
  both paths hit the same idempotent endpoint, so there's no conflict.
- After the run (success, partial failure, or total failure), the caller's
  `onDone()` always fires, so the UI reconciles against real server state
  rather than an optimistic count — a totally-offline run surfaces as
  `0/N approved — N failed, click to retry`, never a silent no-op.

## Testing

No backend code changes, so no new backend tests. This project has no
frontend test framework, so verification is `npm run build` (typecheck) plus
manual smoke testing:
- Partially-approved door in the Results grid: click Approve All, confirm
  every undecided variant flips to ✓ Approved, any previously-rejected
  variant stays ✗ Rejected, and the button disappears once nothing remains
  undecided.
- Same check from the Review queue's per-project Approve All.
- Coverage page: confirm the door's "Approved" badge updates to `N/N` (or
  the correct partial count if some variants were left rejected) after
  either bulk-approve action.
- Zero-undecided state: confirm the button doesn't render when everything is
  already decided.

## Out of scope (this iteration)

- A backend batch endpoint (rejected in favor of the sequential frontend
  loop — see Architecture).
- Bulk-approving the replica image (Approve All is variants-only; the
  replica keeps its existing single-image gate in `ResultsGrid`/`ReviewQueue`).
- A "reject all" or "undo bulk approve" action.
- Confirmation dialogs or undo — explicitly decided against.
- Any change to QA judge behavior, trust-config thresholds, or the
  reliability ledger's scoring — bulk approvals feed the ledger exactly the
  same way individual approvals already do (verified during brainstorming:
  `append_record` already tolerates a null pipeline verdict for
  not-yet-judged images, no new code path needed there).

## Deliverables

1. `frontend/src/components/ApproveAllButton.tsx` (new, shared).
2. `ResultsGrid.tsx`: wired in next to the Wood Variations header.
3. `ReviewQueue.tsx`: wired in per-project section.
4. `npm run build` clean; manual smoke test passes for both call sites and
   the Coverage page reflects the result.
