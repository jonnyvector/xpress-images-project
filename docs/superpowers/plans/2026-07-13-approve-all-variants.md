# Approve All (Variants) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click "Approve All" action that bulk-approves every not-yet-decided variant image for a door, in the Results grid and in the Review queue.

**Architecture:** A new shared `ApproveAllButton` React component loops sequentially over the existing single-image `api.setApproval(...)` call (no new backend endpoint), tracking progress/failures locally, and is wired into `ResultsGrid.tsx` and `ReviewQueue.tsx` next to their existing per-image approval controls.

**Tech Stack:** React 19 + TypeScript + Vite (frontend only — no backend changes in this plan).

## Global Constraints

- Design source of truth: `docs/superpowers/specs/2026-07-13-approve-all-variants-design.md`.
- Variants only — never bulk-approves the replica image.
- Calls run **sequentially** (await each before starting the next), never in parallel — avoids concurrent writes to the same project on the backend.
- Targets only variants with **no decision yet**. A variant already `rejected` is left untouched (not overwritten).
- No confirmation dialog — the action fires immediately on click.
- No new backend endpoint — reuses the existing `POST /projects/{id}/approvals` via `api.setApproval` from `frontend/src/api.ts:151-162` (unchanged).
- Continues through individual failures (one bad id doesn't abort the rest) and reports a `succeeded/failed` summary.
- Renders nothing when there is nothing to approve (empty target list).
- No new backend tests (no backend changes). No frontend test framework exists in this project — verification is `npm run build` (typecheck) plus manual smoke testing.

---

### Task 1: `ApproveAllButton` component

**Files:**
- Create: `frontend/src/components/ApproveAllButton.tsx`

**Interfaces:**
- Consumes: `api.setApproval(id: string, imageId: string, verdict: 'approved' | 'rejected', reasons?: string[], note?: string): Promise<Project>` from `frontend/src/api.ts:151-162` (existing, unchanged).
- Produces: default-exported React component `ApproveAllButton` with props `{ projectId: string; imageIds: string[]; onDone: () => void }`. Later tasks import this as `import ApproveAllButton from './ApproveAllButton'`.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/ApproveAllButton.tsx`:

```tsx
// One-click bulk-approve for a list of undecided variant image ids. Runs
// sequentially against the existing single-image approval endpoint (no new
// backend call) so it never introduces a concurrent write to the same
// project — the same effect as clicking Approve N times in a row quickly.
import { useCallback, useState } from 'react';
import * as api from '../api';

interface Props {
  projectId: string;
  imageIds: string[];
  onDone: () => void;
}

interface RunResult {
  succeeded: number;
  failed: number;
}

export default function ApproveAllButton({ projectId, imageIds, onDone }: Props) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<RunResult | null>(null);

  const handleClick = useCallback(async () => {
    setRunning(true);
    setResult(null);
    let succeeded = 0;
    let failed = 0;
    for (let i = 0; i < imageIds.length; i++) {
      setProgress(i);
      try {
        await api.setApproval(projectId, imageIds[i], 'approved');
        succeeded++;
      } catch (err) {
        console.error('Approve All: failed to approve', imageIds[i], err);
        failed++;
      }
    }
    setProgress(imageIds.length);
    setRunning(false);
    setResult({ succeeded, failed });
    onDone();
    if (failed === 0) {
      setTimeout(() => setResult(null), 4000);
    }
  }, [projectId, imageIds, onDone]);

  if (imageIds.length === 0) return null;

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
      <button
        onClick={handleClick}
        disabled={running}
        style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
      >
        {running ? `Approving… (${progress}/${imageIds.length})` : `Approve All (${imageIds.length})`}
      </button>
      {result && result.failed > 0 && (
        <span className="status-error" style={{ fontSize: '0.75rem', padding: '0.15rem 0.4rem' }}>
          {result.succeeded}/{result.succeeded + result.failed} approved — {result.failed} failed, click to retry
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit 2>&1 | grep -i ApproveAllButton || echo "no ApproveAllButton errors"`
Expected: `no ApproveAllButton errors`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ApproveAllButton.tsx
git commit -m "feat: add ApproveAllButton component"
```

---

### Task 2: Wire into the Results grid

**Files:**
- Modify: `frontend/src/components/ResultsGrid.tsx`

**Interfaces:**
- Consumes: `ApproveAllButton` from Task 1 (`frontend/src/components/ApproveAllButton.tsx`, props `{ projectId, imageIds, onDone }`); the file's own existing `verdicts: Map<string, Approval['verdict']>` state (populated via `api.listApprovals`, `ResultsGrid.tsx:28-36`) and `refreshApprovals: () => void` callback (`ResultsGrid.tsx:29-33`); `project.results: ProjectResult[]` (each with `image_id: string`, from `frontend/src/types.ts:60-65`).

- [ ] **Step 1: Import the component and compute the undecided-variant id list**

In `frontend/src/components/ResultsGrid.tsx`, add the import alongside the existing component imports (near line 6-7):

```tsx
import ApprovalControls from './ApprovalControls';
import ApproveAllButton from './ApproveAllButton';
import QaBadge from './QaBadge';
```

Then, inside the `ResultsGrid` function body, add this computation right after the `verdicts`/`refreshApprovals` block (after line 36, before the QA-polling `hasPendingQa` block):

```tsx
  const undecidedVariantIds = project.results
    .filter((r) => {
      const v = verdicts.get(r.image_id);
      return v !== 'approved' && v !== 'rejected';
    })
    .map((r) => r.image_id);
```

- [ ] **Step 2: Render the button next to the "Wood Variations" header**

In the same file, find this block (around line 264-272):

```tsx
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h3 style={{ margin: 0 }}>Wood Variations ({project.results.length})</h3>
            <button
              onClick={toggleSort}
              style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
            >
              {sortAlpha ? 'Sort: Original' : 'Sort: A–Z'}
            </button>
          </div>
```

Replace it with:

```tsx
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h3 style={{ margin: 0 }}>Wood Variations ({project.results.length})</h3>
            <ApproveAllButton
              projectId={project.id}
              imageIds={undecidedVariantIds}
              onDone={refreshApprovals}
            />
            <button
              onClick={toggleSort}
              style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
            >
              {sortAlpha ? 'Sort: Original' : 'Sort: A–Z'}
            </button>
          </div>
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit 2>&1 | grep -i ResultsGrid || echo "no ResultsGrid errors"`
Expected: `no ResultsGrid errors`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ResultsGrid.tsx
git commit -m "feat: wire Approve All into the Results grid"
```

---

### Task 3: Wire into the Review queue

**Files:**
- Modify: `frontend/src/components/ReviewQueue.tsx`

**Interfaces:**
- Consumes: `ApproveAllButton` from Task 1; the file's own existing `p: QueueProject` (`ReviewQueue.tsx:20-27`, has `project_id: string` and `variants: QueueVariant[]` where `QueueVariant.image_id: string`, `ReviewQueue.tsx:12-18`) and `onChanged: () => void` callback (`ReviewQueue.tsx:59-65`).

- [ ] **Step 1: Import the component**

In `frontend/src/components/ReviewQueue.tsx`, add the import alongside the existing ones (near line 9-10):

```tsx
import ApprovalControls from './ApprovalControls';
import ApproveAllButton from './ApproveAllButton';
import QaBadge from './QaBadge';
```

- [ ] **Step 2: Render the button next to each project section's heading**

Find this line (around line 85):

```tsx
          <h3>{p.project_name}</h3>
```

Replace it with:

```tsx
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <h3 style={{ margin: 0 }}>{p.project_name}</h3>
            <ApproveAllButton
              projectId={p.project_id}
              imageIds={p.variants.map((v) => v.image_id)}
              onDone={onChanged}
            />
          </div>
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit 2>&1 | grep -i ReviewQueue || echo "no ReviewQueue errors"`
Expected: `no ReviewQueue errors`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ReviewQueue.tsx
git commit -m "feat: wire Approve All into the Review queue"
```

---

### Task 4: End-to-end verification

**Files:** none (verification only)

**Interfaces:**
- Consumes: the running app (Tasks 1-3 complete).

- [ ] **Step 1: Run the full frontend build**

Run: `npm run build`
Expected: builds successfully with no TypeScript errors

- [ ] **Step 2: Manual smoke test**

Run: `npm run dev` (starts backend on :8000 and frontend on :5173)

In the browser:
1. Open a project that has generated variant results, with at least one variant already approved and, if possible, one already rejected. Confirm the "Wood Variations" header shows an `Approve All (N)` button where N is the count of variants with no decision yet (not counting the already-approved or already-rejected ones).
2. Click it. Confirm the label shows live progress (`Approving… (k/N)`), then every previously-undecided variant flips to ✓ Approved, the already-rejected variant (if any) stays ✗ Rejected, and the button disappears once nothing remains undecided.
3. Open the Review queue tab. For a project section with pending variants, confirm it shows its own `Approve All (N)` button; click it and confirm those variants clear out of the queue (or, if the project also had a pending replica, confirm the replica stays untouched — still awaiting its own individual approval).
4. Confirm a project with zero undecided variants shows no Approve All button in either view.
5. If you previously built the Coverage page feature (branch `feat/coverage-approval-shopify-status` / PR #2), and want to cross-check: open that branch's Coverage tab against a door you just bulk-approved here and confirm its "Approved" badge reflects the new count. (Optional — Coverage isn't required for this plan's own verification, since it lives on a different, not-yet-merged branch.)

- [ ] **Step 3: Stop the dev servers**

Press Ctrl+C in the terminal running `npm run dev` (only if you started it yourself for this test — leave it running if it was already up before you began).
