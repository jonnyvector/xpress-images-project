import { useCallback, useEffect, useState } from 'react';
import type { Project } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';

interface Props {
  project: Project;
}

export default function ResultsGrid({ project }: Props) {
  const dispatch = useDispatch();
  // Cache-bust base image URL when re-learning completes
  const [baseImageCacheBust, setBaseImageCacheBust] = useState(() => Date.now());
  useEffect(() => {
    if (project.learning_status === 'done') {
      setBaseImageCacheBust(Date.now());
    }
  }, [project.learning_status]);

  const [retryingIndices, setRetryingIndices] = useState<Set<number>>(
    () => new Set(project.retrying_indices ?? []),
  );

  // Sync server-side retrying_indices into local state
  useEffect(() => {
    setRetryingIndices((prev) => {
      const serverSet = new Set(project.retrying_indices ?? []);
      // Keep local entries that are still on the server, drop ones that finished
      const next = new Set<number>();
      for (const idx of prev) {
        if (serverSet.has(idx)) next.add(idx);
      }
      for (const idx of serverSet) {
        next.add(idx);
      }
      if (next.size === prev.size && [...next].every((v) => prev.has(v))) return prev;
      return next;
    });
  }, [project.retrying_indices]);

  const handleRetry = useCallback(async (idx: number) => {
    setRetryingIndices((prev) => new Set(prev).add(idx));
    try {
      await api.retryVariation(project.id, idx);

      // Poll until this index leaves retrying_indices
      const poll = async () => {
        const updated = await api.getProject(project.id);
        dispatch({ type: 'UPDATE_PROJECT', project: updated });
        if (updated.retrying_indices.includes(idx)) {
          setTimeout(poll, 2000);
        } else {
          setRetryingIndices((prev) => {
            const next = new Set(prev);
            next.delete(idx);
            return next;
          });
        }
      };
      setTimeout(poll, 2000);
    } catch (err) {
      console.error('Failed to retry variation:', err);
      setRetryingIndices((prev) => {
        const next = new Set(prev);
        next.delete(idx);
        return next;
      });
    }
  }, [dispatch, project.id]);

  const handleDiscard = useCallback(async (idx: number) => {
    try {
      await api.discardResult(project.id, idx);
      const projects = await api.listProjects();
      const updated = projects.find((p) => p.id === project.id);
      if (updated) dispatch({ type: 'UPDATE_PROJECT', project: updated });
    } catch (err) {
      console.error('Failed to discard result:', err);
    }
  }, [dispatch, project.id]);

  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const handleSaveToFolder = useCallback(async (watermark: boolean) => {
    try {
      setSaveStatus('Saving...');
      const result = await api.saveResultsToFolder(project.id, watermark);
      setSaveStatus(`Saved ${result.files.length} file(s) to ${result.saved_to}`);
      setTimeout(() => setSaveStatus(null), 4000);
    } catch (err) {
      console.error('Failed to save to folder:', err);
      setSaveStatus('Failed to save — check console');
      setTimeout(() => setSaveStatus(null), 4000);
    }
  }, [project.id]);

  return (
    <section style={{ marginTop: '1rem' }}>
      {project.has_base_image && (
        <>
          <h3>Base {project.product_type === 'Drawer Front' ? 'Drawer Front' : 'Door'} (Learned Style)</h3>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}>
            <img
              src={`/api/projects/${project.id}/base-image?v=${baseImageCacheBust}`}
              alt="Base door"
              style={{ maxWidth: '60%', borderRadius: 'var(--radius)' }}
            />
          </div>
        </>
      )}

      {project.results.length > 0 && (
        <>
          <h3>Wood Variations ({project.results.length})</h3>

          {project.results.length > 0 && (
            <>
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <button onClick={() => handleSaveToFolder(true)} style={{ flex: 1 }}>
                  Save Watermarked to Folder
                </button>
                <button onClick={() => handleSaveToFolder(false)} style={{ flex: 1 }}>
                  Save Plain to Folder
                </button>
              </div>
              {saveStatus && (
                <div style={{
                  padding: '0.5rem',
                  marginBottom: '0.5rem',
                  borderRadius: 'var(--radius)',
                  background: saveStatus.startsWith('Saved') ? '#d4edda' : saveStatus === 'Saving...' ? '#cce5ff' : '#f8d7da',
                  color: saveStatus.startsWith('Saved') ? '#155724' : saveStatus === 'Saving...' ? '#004085' : '#721c24',
                  fontSize: '0.875rem',
                }}>
                  {saveStatus}
                </div>
              )}
            </>
          )}

          <div className="results-grid">
            {project.results.map((result) => {
              const isRetrying = retryingIndices.has(result.index);
              return (
                <div key={result.index} className="result-card" style={{ position: 'relative' }}>
                  {isRetrying && (
                    <div style={{
                      position: 'absolute',
                      inset: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: 'rgba(0, 0, 0, 0.5)',
                      borderRadius: 'var(--radius)',
                      zIndex: 1,
                    }}>
                      <div style={{
                        color: '#fff',
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        textAlign: 'center',
                      }}>
                        <div className="spinner" style={{ margin: '0 auto 0.5rem' }} />
                        Retrying...
                      </div>
                    </div>
                  )}
                  <img
                    src={`/api/projects/${project.id}/results/${result.index}/image?v=${project.results.length}`}
                    alt={result.wood_name}
                  />
                  <div className="caption">{result.wood_name}</div>
                  <div className="actions">
                    <a
                      href={`/api/projects/${project.id}/results/${result.index}/image?watermark=false&v=${project.results.length}`}
                      download={`${project.name}_${result.wood_name.toLowerCase().replace(/ /g, '_')}.png`}
                    >
                      <button disabled={isRetrying}>Download</button>
                    </a>
                    <button
                      onClick={() => handleRetry(result.index)}
                      disabled={isRetrying}
                    >
                      Retry
                    </button>
                    <button className="danger" onClick={() => handleDiscard(result.index)} disabled={isRetrying}>
                      Discard
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {project.errors.length > 0 && (
        <details style={{ marginTop: '1rem' }}>
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
            Errors ({project.errors.length})
          </summary>
          {project.errors.map((err, i) => (
            <div key={i} className="status-error" style={{ marginTop: '0.5rem' }}>
              <strong>{err.wood_name}:</strong> {err.error}
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
