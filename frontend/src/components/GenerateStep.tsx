import { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';

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
  const [retrying, setRetrying] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollErrorCount = useRef(0);

  // Keep a stable ref to project.id so the interval callback never goes stale
  const projectIdRef = useRef(project.id);
  projectIdRef.current = project.id;

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // Cleanup on unmount only
  useEffect(() => () => stopPolling(), [stopPolling]);

  // The actual poll logic — stored in a ref so setInterval always calls the latest version
  const pollFnRef = useRef<(() => Promise<void>) | null>(null);
  pollFnRef.current = async () => {
    try {
      const genStatus = await api.getGenerationStatus(projectIdRef.current);
      pollErrorCount.current = 0;
      setRetrying(false);
      setCompleted(genStatus.completed);
      setTotal(genStatus.total);
      if (genStatus.status !== 'running') {
        stopPolling();
        setGenerating(false);
        // Refresh only this project
        const updated = await api.getProject(projectIdRef.current);
        dispatch({ type: 'UPDATE_PROJECT', project: updated });
      }
    } catch {
      pollErrorCount.current += 1;
      if (pollErrorCount.current >= 5) {
        stopPolling();
        setGenerating(false);
        setRetrying(false);
        setError('Lost connection to server. Click Generate to retry.');
      } else {
        setRetrying(true);
      }
    }
  };

  // Stable function to start polling — never changes identity
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => pollFnRef.current?.(), 2000);
  }, []);

  // Resume polling if generation is already running (e.g. after page refresh)
  useEffect(() => {
    if (project.generation_status === 'running' && !pollRef.current) {
      setGenerating(true);
      setTotal(project.selected_swatches.length);
      startPolling();
    }
  }, [project.generation_status, project.selected_swatches.length, startPolling]);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setError(null);
    setRetrying(false);
    pollErrorCount.current = 0;
    setCompleted(0);
    try {
      await api.startGeneration(project.id);
      setTotal(project.selected_swatches.length);
      startPolling();
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : 'Generation failed');
    }
  }, [project.id, project.selected_swatches.length, startPolling]);

  const hasSignature = project.has_signature;
  const hasSwatches = project.selected_swatches.length > 0;
  const canGenerate = Boolean(apiKey) && hasSignature && hasSwatches && !generating;

  return (
    <section>
      <h3>3. Generate Variations</h3>

      {!apiKey && <div className="status-info">Enter your API key in the sidebar</div>}
      {apiKey && !hasSignature && <div className="status-info">Learn a style first (Step 1)</div>}
      {apiKey && hasSignature && !hasSwatches && <div className="status-info">Select at least one wood type (Step 2)</div>}

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
