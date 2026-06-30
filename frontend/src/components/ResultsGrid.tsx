import { useCallback, useEffect, useState } from 'react';
import type { Project } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import { usePollingTask } from '../hooks/usePollingTask';

interface Props {
  project: Project;
}

export default function ResultsGrid({ project }: Props) {
  const dispatch = useDispatch();
  const [importFolder, setImportFolder] = useState('');
  const [importing, setImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);

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

  // Single shared poller for all in-flight retries: refresh the project until
  // the server reports no indices still retrying. The sync effect above clears
  // local entries as they finish. usePollingTask gives us unmount cleanup and
  // an error cap for free.
  const { start: startRetryPoll } = usePollingTask({
    enabled: false,
    onPoll: async () => {
      const updated = await api.getProject(project.id);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      return updated.retrying_indices.length > 0;
    },
  });

  const handleRetry = useCallback(async (idx: number) => {
    setRetryingIndices((prev) => new Set(prev).add(idx));
    try {
      await api.retryVariation(project.id, idx);
      startRetryPoll();
    } catch (err) {
      console.error('Failed to retry variation:', err);
      setRetryingIndices((prev) => {
        const next = new Set(prev);
        next.delete(idx);
        return next;
      });
    }
  }, [project.id, startRetryPoll]);

  const handleDiscard = useCallback(async (idx: number) => {
    try {
      await api.discardResult(project.id, idx);
      const updated = await api.getProject(project.id);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
    } catch (err) {
      console.error('Failed to discard result:', err);
    }
  }, [dispatch, project.id]);

  const sortStorageKey = `sort_alpha_${project.id}`;
  const [sortAlpha, setSortAlpha] = useState(
    () => localStorage.getItem(`sort_alpha_${project.id}`) === 'true'
  );

  const toggleSort = useCallback(() => {
    setSortAlpha((prev) => {
      const next = !prev;
      localStorage.setItem(sortStorageKey, String(next));
      return next;
    });
  }, [sortStorageKey]);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [watermarkOffset, setWatermarkOffset] = useState(0);
  const [imageScale, setImageScale] = useState(1.0);
  const [watermarkCacheBust, setWatermarkCacheBust] = useState(() => Date.now());
  const watermarkStorageKey = `watermark_offset_${project.id}`;
  const imageScaleStorageKey = `image_scale_${project.id}`;

  useEffect(() => {
    const saved = localStorage.getItem(watermarkStorageKey);
    if (saved !== null) {
      const parsed = Number(saved);
      if (!Number.isNaN(parsed)) setWatermarkOffset(parsed);
    }
  }, [watermarkStorageKey]);

  useEffect(() => {
    const saved = localStorage.getItem(imageScaleStorageKey);
    if (saved !== null) {
      const parsed = Number(saved);
      if (!Number.isNaN(parsed)) setImageScale(parsed);
    }
  }, [imageScaleStorageKey]);

  useEffect(() => {
    localStorage.setItem(watermarkStorageKey, String(watermarkOffset));
    setWatermarkCacheBust(Date.now());
  }, [watermarkOffset, watermarkStorageKey]);

  useEffect(() => {
    localStorage.setItem(imageScaleStorageKey, String(imageScale));
    setWatermarkCacheBust(Date.now());
  }, [imageScale, imageScaleStorageKey]);

  const handleImport = useCallback(async () => {
    if (!importFolder.trim()) return;
    setImporting(true);
    setImportStatus(null);
    try {
      const result = await api.importResultsFromFolder(project.id, importFolder.trim());
      setImportStatus(`Imported ${result.imported} image(s)`);
      const updated = await api.getProject(project.id);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      setImportFolder('');
      setTimeout(() => setImportStatus(null), 4000);
    } catch (err) {
      setImportStatus(err instanceof Error ? err.message : 'Import failed');
      setTimeout(() => setImportStatus(null), 4000);
    } finally {
      setImporting(false);
    }
  }, [dispatch, project.id, importFolder]);

  const handleSaveToFolder = useCallback(async (watermark: boolean) => {
    try {
      setSaveStatus('Saving...');
      const result = await api.saveResultsToFolder(project.id, watermark, watermarkOffset, imageScale);
      setSaveStatus(`Saved ${result.files.length} file(s) to ${result.saved_to}`);
      setTimeout(() => setSaveStatus(null), 4000);
    } catch (err) {
      console.error('Failed to save to folder:', err);
      setSaveStatus('Failed to save — check console');
      setTimeout(() => setSaveStatus(null), 4000);
    }
  }, [project.id, watermarkOffset, imageScale]);

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

      <details style={{ marginBottom: '1rem' }}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>
          Import images from folder
        </summary>
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
          <input
            type="text"
            placeholder="/path/to/folder"
            value={importFolder}
            onChange={(e) => setImportFolder(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleImport(); }}
            style={{ flex: 1 }}
          />
          <button onClick={handleImport} disabled={importing || !importFolder.trim()}>
            {importing ? 'Importing...' : 'Import'}
          </button>
        </div>
        {importStatus && (
          <div
            className={importStatus.startsWith('Imported') ? 'status-success' : 'status-error'}
            style={{ marginTop: '0.5rem' }}
          >
            {importStatus}
          </div>
        )}
      </details>

      {project.results.length > 0 && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h3 style={{ margin: 0 }}>Wood Variations ({project.results.length})</h3>
            <button
              onClick={toggleSort}
              style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
            >
              {sortAlpha ? 'Sort: Original' : 'Sort: A–Z'}
            </button>
          </div>

          {project.results.length > 0 && (
            <>
              <div className="control-row">
                <label style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                  Watermark position
                </label>
                <input
                  type="range"
                  min={-600}
                  max={600}
                  step={5}
                  value={watermarkOffset}
                  onChange={(e) => setWatermarkOffset(Number(e.target.value))}
                  style={{ flex: 1, minWidth: '180px' }}
                />
                <span style={{ fontSize: '0.875rem', minWidth: '56px', textAlign: 'right' }}>
                  {watermarkOffset}px
                </span>
                <button
                  onClick={() => setWatermarkOffset(0)}
                  style={{ padding: '0.25rem 0.5rem' }}
                >
                  Reset
                </button>
              </div>
              <div className="control-row">
                <label style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                  Image size
                </label>
                <input
                  type="range"
                  min={1.0}
                  max={1.5}
                  step={0.01}
                  value={imageScale}
                  onChange={(e) => setImageScale(Number(e.target.value))}
                  style={{ flex: 1, minWidth: '180px' }}
                />
                <span style={{ fontSize: '0.875rem', minWidth: '56px', textAlign: 'right' }}>
                  {Math.round(imageScale * 100)}%
                </span>
                <button
                  onClick={() => setImageScale(1.0)}
                  style={{ padding: '0.25rem 0.5rem' }}
                >
                  Reset
                </button>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <button onClick={() => handleSaveToFolder(true)} style={{ flex: 1 }}>
                  Save Watermarked to Folder
                </button>
                <button onClick={() => handleSaveToFolder(false)} style={{ flex: 1 }}>
                  Save Plain to Folder
                </button>
              </div>
              {saveStatus && (
                <div
                  className={
                    saveStatus.startsWith('Saved')
                      ? 'status-success'
                      : saveStatus === 'Saving...'
                      ? 'status-info'
                      : 'status-error'
                  }
                  style={{ marginBottom: '0.5rem' }}
                >
                  {saveStatus}
                </div>
              )}
            </>
          )}

          <div className="results-grid">
            {(sortAlpha
              ? [...project.results].sort((a, b) => a.wood_name.localeCompare(b.wood_name))
              : project.results
            ).map((result) => {
              const isRetrying = retryingIndices.has(result.index);
              return (
                <div key={result.index} className="result-card" style={{ position: 'relative' }}>
                  {isRetrying && (
                    <div className="result-retry-overlay">
                      <div className="result-retry-overlay-label">
                        <div className="spinner" style={{ margin: '0 auto 0.5rem' }} />
                        Retrying...
                      </div>
                    </div>
                  )}
                  <img
                    src={`/api/projects/${project.id}/results/${result.index}/image?v=${project.results.length}&watermark_offset=${watermarkOffset}&image_scale=${imageScale}&wmv=${watermarkCacheBust}`}
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
