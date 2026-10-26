// Approve/Reject for a replica. Approving it unlocks generation (GT-001).
// Variants use VariantActions (Keep / Delete) instead.
import { useCallback, useState } from 'react';
import type { Project } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';

interface Props {
  project: Project;
  imageId: string;
  verdict: 'approved' | 'rejected' | null;
  onChanged?: () => void;
  compact?: boolean;
}

export default function ApprovalControls({ project, imageId, verdict, onChanged, compact }: Props) {
  const dispatch = useDispatch();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async (v: 'approved' | 'rejected') => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.setApproval(project.id, imageId, v);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save approval');
    } finally {
      setBusy(false);
    }
  }, [project.id, imageId, dispatch, onChanged]);

  const size = compact ? { padding: '0.2rem 0.5rem', fontSize: '0.75rem' } : {};

  return (
    <div style={{ marginTop: compact ? '0.25rem' : '0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {verdict === 'approved' && (
          <span className="approval-badge approved" title="Operator approved">✓ Approved</span>
        )}
        {verdict === 'rejected' && (
          <span className="approval-badge rejected" title="Operator rejected">✗ Rejected</span>
        )}
        {verdict !== 'approved' && (
          <button className="approve-btn" onClick={() => submit('approved')} disabled={busy} style={size}>
            Approve
          </button>
        )}
        <button
          className="danger"
          onClick={() => submit('rejected')}
          disabled={busy}
          style={size}
        >
          Reject
        </button>
      </div>
      {error && <div className="status-error" style={{ marginTop: '0.4rem' }}>{error}</div>}
    </div>
  );
}
