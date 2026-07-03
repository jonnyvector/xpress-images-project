// Approve/Reject controls for one image (replica or variant) — the human half
// of the graduated-trust pipeline. Rejects require reasons from the fixed
// vocabulary so disagreements feed the reliability ledger cleanly.
import { useCallback, useState } from 'react';
import type { Project } from '../types';
import { REJECT_REASONS } from '../types';
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
  const [rejecting, setRejecting] = useState(false);
  const [reasons, setReasons] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async (v: 'approved' | 'rejected', rs: string[]) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.setApproval(project.id, imageId, v, rs);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      setRejecting(false);
      setReasons(new Set());
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save approval');
    } finally {
      setBusy(false);
    }
  }, [project.id, imageId, dispatch, onChanged]);

  const toggleReason = useCallback((r: string) => {
    setReasons((prev) => {
      const next = new Set(prev);
      if (next.has(r)) next.delete(r);
      else next.add(r);
      return next;
    });
  }, []);

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
        <button
          onClick={() => submit('approved', [])}
          disabled={busy || verdict === 'approved'}
          style={{ ...size, background: verdict === 'approved' ? undefined : '#2e7d32', color: '#fff' }}
        >
          Approve
        </button>
        <button
          className="danger"
          onClick={() => setRejecting((v) => !v)}
          disabled={busy}
          style={size}
        >
          Reject
        </button>
      </div>
      {rejecting && (
        <div style={{ marginTop: '0.4rem', fontSize: '0.8rem' }}>
          {REJECT_REASONS.map((r) => (
            <label key={r} style={{ display: 'block', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={reasons.has(r)}
                onChange={() => toggleReason(r)}
              />{' '}
              {r.replace(/_/g, ' ')}
            </label>
          ))}
          <button
            className="danger"
            onClick={() => submit('rejected', Array.from(reasons))}
            disabled={busy || reasons.size === 0}
            style={{ ...size, marginTop: '0.25rem' }}
          >
            Confirm reject
          </button>
        </div>
      )}
      {error && <div className="status-error" style={{ marginTop: '0.4rem' }}>{error}</div>}
    </div>
  );
}
