import { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import { usePollingTask } from '../hooks/usePollingTask';

interface Props {
  project: Project;
  apiKey: string;
}

export default function GenerateStep({ project, apiKey }: Props) {
  const dispatch = useDispatch();
  const [generating, setGenerating] = useState(false);
  const [completed, setCompleted] = useState(0);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const projectIdRef = useRef(project.id);
  projectIdRef.current = project.id;

  const handleErrorExhausted = useCallback(() => {
    setGenerating(false);
    setError('Lost connection to server. Click Generate to retry.');
  }, []);

  const { start, stop, retrying, resetErrors } = usePollingTask({
    enabled: false,
    onPoll: async () => {
      const genStatus = await api.getGenerationStatus(projectIdRef.current);
      setCompleted(genStatus.completed);
      setTotal(genStatus.total);

      // Refresh the project every poll so results and QA badges land live,
      // not only when the run finishes.
      try {
        const updated = await api.getProject(projectIdRef.current);
        dispatch({ type: 'UPDATE_PROJECT', project: updated });
      } catch {
        // transient — next poll will sync
      }

      if (genStatus.status !== 'running') {
        setGenerating(false);
        stop();
        return false;
      }

      return true;
    },
    onErrorExhausted: handleErrorExhausted,
  });

  useEffect(() => {
    if (project.generation_status === 'running') {
      setGenerating(true);
      setTotal(project.selected_swatches.length);
      start();
    } else {
      stop();
    }
  }, [project.generation_status, project.selected_swatches.length, start, stop]);

  const handleGenerate = useCallback(async () => {
    setError(null);
    try {
      // Consent with honest numbers: estimate mirrors the server gates and
      // includes the worst-case auto-retry band — it can never under-quote.
      const est = await api.getGenerateEstimate(project.id);
      if (!est.gate_ok) {
        setError(est.gate_reason ?? 'Generation is gated');
        return;
      }
      const msg =
        `Stage ${est.stage} — ${est.images} image${est.images === 1 ? '' : 's'} ≈ $${est.est_cost_usd.toFixed(2)}` +
        ` (worst case $${est.worst_case_usd.toFixed(2)} with auto-retries) — proceed?`;
      if (!window.confirm(msg)) return;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Estimate failed');
      return;
    }
    setGenerating(true);
    resetErrors();
    setCompleted(0);
    try {
      await api.startGeneration(project.id);
      setTotal(project.selected_swatches.length);
      start();
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : 'Generation failed');
    }
  }, [project.id, project.selected_swatches.length, resetErrors, start]);

  const hasSignature = project.has_signature;
  const hasSwatches = project.selected_swatches.length > 0;
  const replicaApproved = project.replica_approved;
  const canGenerate = Boolean(apiKey) && hasSignature && hasSwatches && replicaApproved && !generating;

  return (
    <section>
      <h3>3. Generate Variations</h3>

      {!apiKey && <div className="status-info">Enter your API key in the sidebar</div>}
      {apiKey && !hasSignature && <div className="status-info">Learn a style first (Step 1)</div>}
      {apiKey && hasSignature && !replicaApproved && (
        <div className="status-error">
          Variants locked — approve the replica first (Stage A gate)
        </div>
      )}
      {apiKey && hasSignature && replicaApproved && !hasSwatches && (
        <div className="status-info">Select at least one wood type (Step 2)</div>
      )}

      <button
        className="primary"
        onClick={handleGenerate}
        disabled={!canGenerate}
        style={{ width: '100%', marginTop: '0.75rem' }}
      >
        {generating ? (
          <>
            <span className="spinner" /> Generating...
          </>
        ) : (
          'Generate Variations'
        )}
      </button>

      {generating && total > 0 && (
        <div style={{ marginTop: '0.75rem' }}>
          <div style={{ fontSize: '0.875rem', marginBottom: '0.25rem' }}>
            {completed} / {total} completed
            {retrying && <span style={{ color: '#b59f3b', marginLeft: '0.5rem' }}>Connection issue, retrying...</span>}
          </div>
          <div className="progress-bar">
            <div className="fill" style={{ width: `${(completed / total) * 100}%` }} />
          </div>
        </div>
      )}

      {error && <div className="status-error" style={{ marginTop: '0.75rem' }}>{error}</div>}
    </section>
  );
}
