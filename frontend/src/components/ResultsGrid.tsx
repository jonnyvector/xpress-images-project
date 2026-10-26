import { useCallback, useEffect, useRef, useState } from 'react';
import type { Approval, Project } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import { usePollingTask } from '../hooks/usePollingTask';
import ImageViewer, { type ViewerImage } from './ImageViewer';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import ApprovalControls from './ApprovalControls';
import ApproveAllButton from './ApproveAllButton';
import VariantActions from './VariantActions';
import { showError, onError } from '../notify';

interface Props {
  project: Project;
  // The door page shows the replica and the variants on separate tabs.
  part: 'replica' | 'variants';
}

export default function ResultsGrid({ project, part }: Props) {
  const dispatch = useDispatch();
  const [importFolder, setImportFolder] = useState('');
  const [importing, setImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [viewer, setViewer] = useState<{ images: ViewerImage[]; index: number } | null>(null);
  const importStatusTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(importStatusTimer.current), []);

  // Cache-bust base image URL when re-learning completes
  const [baseImageCacheBust, setBaseImageCacheBust] = useState(() => Date.now());
  useEffect(() => {
    if (project.learning_status === 'done') {
      setBaseImageCacheBust(Date.now());
    }
  }, [project.learning_status]);

  // Per-image operator verdicts (approvals keyed by stable image_id).
  const [verdicts, setVerdicts] = useState<Map<string, Approval['verdict']>>(new Map());
  const [verdictsLoaded, setVerdictsLoaded] = useState(false);
  const refreshApprovals = useCallback(() => {
    api.listApprovals(project.id)
      .then((items) => {
        setVerdicts(new Map(items.map((a) => [a.image_id, a.verdict])));
        setVerdictsLoaded(true);
      })
      .catch(onError("Couldn't load approvals"));
  }, [project.id]);
  useEffect(() => {
    refreshApprovals();
  }, [refreshApprovals]);

  // Gate on verdictsLoaded: until the first approvals fetch resolves, treating
  // every variant as "undecided" would let Approve All silently overwrite a
  // prior rejection during that window.
  const undecidedVariantIds = verdictsLoaded
    ? project.results
        .filter((r) => {
          const v = verdicts.get(r.image_id);
          return v !== 'approved' && v !== 'rejected';
        })
        .map((r) => r.image_id)
    : [];

  // Verdicts land asynchronously after generation — keep polling while any
  // QA task is visibly in flight so badges flip from judging… to done.
  const hasPendingQa = Object.values(project.qa_verdicts ?? {}).some(
    (v) => v.qa_status !== 'done',
  );
  const { start: startQaPoll } = usePollingTask({
    enabled: false,
    onPoll: async () => {
      const updated = await api.getProject(project.id);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      return Object.values(updated.qa_verdicts ?? {}).some(
        (v) => v.qa_status !== 'done',
      );
    },
  });
  // Both panels mount this component; only the variants one polls.
  useEffect(() => {
    if (hasPendingQa && part === 'variants') startQaPoll();
  }, [hasPendingQa, part, startQaPoll]);

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

  const handleRetry = useCallback(async (idx: number, woodName: string) => {
    if (!window.confirm(`Regenerate ${woodName}? This makes a new paid Gemini image call.`)) return;
    setRetryingIndices((prev) => new Set(prev).add(idx));
    try {
      await api.retryVariation(project.id, idx);
      startRetryPoll();
    } catch (err) {
      showError("Couldn't start retry", err);
      setRetryingIndices((prev) => {
        const next = new Set(prev);
        next.delete(idx);
        return next;
      });
    }
  }, [project.id, startRetryPoll]);

  const refreshProject = useCallback(() => {
    api
      .getProject(project.id)
      .then((updated) => dispatch({ type: 'UPDATE_PROJECT', project: updated }))
      .catch(onError("Couldn't reload the door"));
  }, [dispatch, project.id]);

  // Woods with more than one image, so the bad copies are easy to find.
  const [dupOnly, setDupOnly] = useState(false);

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
  const saveStatusTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
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

  // Only the settled offset/scale reach the server. Dragging emits a value
  // per step, and every step would re-render every result image (add_watermark
  // is ~70ms each, uncached) — enough to saturate the backend threadpool and
  // stall unrelated requests.
  const renderedWatermarkOffset = useDebouncedValue(watermarkOffset, 300);
  const renderedImageScale = useDebouncedValue(imageScale, 300);

  useEffect(() => {
    localStorage.setItem(watermarkStorageKey, String(watermarkOffset));
  }, [watermarkOffset, watermarkStorageKey]);

  useEffect(() => {
    setWatermarkCacheBust(Date.now());
  }, [renderedWatermarkOffset, renderedImageScale]);

  useEffect(() => {
    localStorage.setItem(imageScaleStorageKey, String(imageScale));
  }, [imageScale, imageScaleStorageKey]);

  const handleImport = useCallback(async () => {
    if (!importFolder.trim()) return;
    setImporting(true);
    setImportStatus(null);
    clearTimeout(importStatusTimer.current);
    const clearLater = () => {
      importStatusTimer.current = setTimeout(() => setImportStatus(null), 4000);
    };
    try {
      const result = await api.importResultsFromFolder(project.id, importFolder.trim());
      setImportStatus(`Imported ${result.imported} image(s)`);
      const updated = await api.getProject(project.id);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      setImportFolder('');
      clearLater();
    } catch (err) {
      setImportStatus(err instanceof Error ? err.message : 'Import failed');
      clearLater();
    } finally {
      setImporting(false);
    }
  }, [dispatch, project.id, importFolder]);

  const handleSaveToFolder = useCallback(async (watermark: boolean) => {
    try {
      clearTimeout(saveStatusTimer.current);
      setSaveStatus('Saving...');
      const result = await api.saveResultsToFolder(project.id, watermark, watermarkOffset, imageScale);
      setSaveStatus(`Saved ${result.files.length} file(s) to ${result.saved_to}`);
      clearTimeout(saveStatusTimer.current);
      saveStatusTimer.current = setTimeout(() => setSaveStatus(null), 4000);
    } catch (err) {
      setSaveStatus(null);
      showError("Couldn't save to folder", err);
    }
  }, [project.id, watermarkOffset, imageScale]);

  const replicaSrc = `/api/projects/${project.id}/base-image?v=${baseImageCacheBust}`;
  const replicaImages: ViewerImage[] = [
    ...(project.upload_filename ? [{ src: `/api/projects/${project.id}/upload`, caption: 'Your sample' }] : []),
    { src: replicaSrc, caption: 'Replica' },
  ];
  const copies = new Map<string, number>();
  for (const r of project.results) copies.set(r.wood_name, (copies.get(r.wood_name) ?? 0) + 1);
  const duplicateWoods = [...copies.values()].filter((n) => n > 1).length;
  const sortedResults = dupOnly
    ? project.results
        .filter((r) => (copies.get(r.wood_name) ?? 0) > 1)
        .sort((a, b) => a.wood_name.localeCompare(b.wood_name) || a.index - b.index)
    : sortAlpha
      ? [...project.results].sort((a, b) => a.wood_name.localeCompare(b.wood_name))
      : project.results;
  // Unwatermarked full-size files, for checking detail.
  const variantImages: ViewerImage[] = sortedResults.map((r) => ({
    src: `/api/projects/${project.id}/results/${r.index}/image?watermark=false&v=${r.image_id}`,
    caption: r.wood_name,
  }));

  return (
    <section>
      {part === 'variants' && project.truncated_runs.length > 0 && (
        <div className="status-error" style={{ marginBottom: '0.75rem' }}>
          ⚠ {project.truncated_runs.length} generation run
          {project.truncated_runs.length > 1 ? 's were' : ' was'} cut short by a
          crash — this batch may be incomplete. Review before shipping.
        </div>
      )}
      {part === 'replica' && !project.has_base_image && (
        <div className="status-info">Learn the style first. The replica appears here once it&apos;s ready.</div>
      )}
      {part === 'replica' && project.has_base_image && (
        <>
          <p className="door-hint">
            The replica is the model&apos;s copy of your door. Approve it only if it matches the
            sample&apos;s shape exactly: every variant is built from it.
          </p>
          <div className="replica-compare">
            {project.upload_filename && (
              <figure>
                <img
                  src={`/api/projects/${project.id}/upload`}
                  alt="Your sample"
                  className="zoomable"
                  onClick={() => setViewer({ images: replicaImages, index: 0 })}
                />
                <figcaption>Your sample</figcaption>
              </figure>
            )}
            <figure>
              <img
                src={replicaSrc}
                alt="Replica"
                className="zoomable"
                onClick={() => setViewer({ images: replicaImages, index: replicaImages.length - 1 })}
              />
              <figcaption>
                Replica{' '}
              </figcaption>
            </figure>
          </div>
          {project.base_image_id && (
            <div className="replica-actions">
              <ApprovalControls
                project={project}
                imageId={project.base_image_id}
                verdict={project.replica_approved ? 'approved' : verdicts.get(project.base_image_id) ?? null}
                onChanged={refreshApprovals}
              />
            </div>
          )}
        </>
      )}

      {part === 'variants' && (
      <>
      <details className="door-tools">
        <summary>Import images from a folder</summary>
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
            <h3 style={{ margin: 0 }}>Variants ({project.results.length})</h3>
            <ApproveAllButton
              projectId={project.id}
              imageIds={undecidedVariantIds}
              onDone={refreshApprovals}
            />
            <button
              onClick={toggleSort}
              disabled={dupOnly}
              style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
            >
              {sortAlpha ? 'Sort: Original' : 'Sort: A–Z'}
            </button>
            {(duplicateWoods > 0 || dupOnly) && (
              <button
                type="button"
                className={dupOnly ? 'filter-btn active' : 'filter-btn'}
                aria-pressed={dupOnly}
                onClick={() => setDupOnly((v) => !v)}
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
                title="Show only woods that have more than one image, grouped together"
              >
                Duplicates only ({duplicateWoods} {duplicateWoods === 1 ? 'wood' : 'woods'})
              </button>
            )}
          </div>

          <details className="door-tools">
            <summary>Export &amp; watermark</summary>
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
          </details>

          <div className="results-grid">
            {sortedResults.map((result, position) => {
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
                  <div style={{ overflow: 'hidden' }}>
                    <img
                      src={`/api/projects/${project.id}/results/${result.index}/image?v=${result.image_id}&watermark_offset=${renderedWatermarkOffset}&image_scale=${renderedImageScale}&wmv=${watermarkCacheBust}`}
                      alt={result.wood_name}
                      loading="lazy"
                      className="zoomable"
                      title="Click to zoom"
                      onClick={() => setViewer({ images: variantImages, index: position })}
                      style={{ display: 'block' }}
                    />
                  </div>
                  <div className="caption">
                    {result.wood_name}
                    {(copies.get(result.wood_name) ?? 0) > 1 && (
                      <span className="dup-count" title="Images of this wood in this door">
                        {' '}×{copies.get(result.wood_name)}
                      </span>
                    )}
                    {result.attempt > 0 && (
                      <span style={{ color: '#888', fontSize: '0.75rem' }}> (attempt {result.attempt})</span>
                    )}{' '}
                  </div>
                  <VariantActions
                    projectId={project.id}
                    imageId={result.image_id}
                    kept={verdicts.get(result.image_id) === 'approved'}
                    onKept={refreshApprovals}
                    onDeleted={refreshProject}
                  />
                  <details className="result-more">
                    <summary aria-label={`More actions for ${result.wood_name}`}>⋯</summary>
                    <div className="result-more-menu">
                      <a
                        href={`/api/projects/${project.id}/results/${result.index}/image?watermark=false&v=${result.image_id}`}
                        download={`${project.name}_${result.wood_name.toLowerCase().replace(/ /g, '_')}.png`}
                      >
                        Download
                      </a>
                      <button type="button" onClick={() => handleRetry(result.index, result.wood_name)} disabled={isRetrying}>
                        Retry (paid)
                      </button>
                    </div>
                  </details>
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
      </>
      )}
      {viewer && (
        <ImageViewer
          images={viewer.images}
          index={viewer.index}
          onIndexChange={(index) => setViewer((v) => v && { ...v, index })}
          onClose={() => setViewer(null)}
        />
      )}
    </section>
  );
}
