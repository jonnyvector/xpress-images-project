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
