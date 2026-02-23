import { useState, useCallback, useEffect, useRef, memo } from 'react';
import type { Project, SignatureVersion } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';

interface Props {
  project: Project;
}

export default memo(function SignatureHistory({ project }: Props) {
  const dispatch = useDispatch();
  const [expanded, setExpanded] = useState(false);
  const [versions, setVersions] = useState<SignatureVersion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Invalidate cache when version_count changes (e.g. after re-learn)
  const prevCountRef = useRef(project.version_count);
  useEffect(() => {
    if (project.version_count !== prevCountRef.current) {
      prevCountRef.current = project.version_count;
      setVersions(null); // force reload on next expand
      if (expanded) {
        // Reload immediately if panel is open
        api.listVersions(project.id).then(setVersions).catch(console.error);
      }
    }
  }, [project.version_count, project.id, expanded]);

  const loadVersions = useCallback(async () => {
    if (versions !== null) return;
    setLoading(true);
    try {
      const data = await api.listVersions(project.id);
      setVersions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load versions');
    } finally {
      setLoading(false);
    }
  }, [project.id, versions]);

  const handleToggle = useCallback(() => {
    const next = !expanded;
    setExpanded(next);
    if (next) loadVersions();
  }, [expanded, loadVersions]);

  const handleRestore = useCallback(async (version: number) => {
    setRestoring(version);
    setError(null);
    try {
      const updated = await api.restoreVersion(project.id, version);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      // Reload versions list since a new archive was created
      const data = await api.listVersions(project.id);
      setVersions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Restore failed');
    } finally {
      setRestoring(null);
    }
  }, [project.id, dispatch]);

  if (project.version_count === 0) return null;

  const activeLabel = project.signature_version > 0
    ? `v${project.signature_version} restored`
    : 'current';

  return (
    <div style={{ marginTop: '0.75rem' }}>
      <button
        type="button"
        onClick={handleToggle}
        style={{
          background: 'none',
          border: 'none',
          padding: '0.25rem 0',
          fontSize: '0.8125rem',
          color: 'var(--color-text-muted)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '0.375rem',
        }}
      >
        <span style={{
          display: 'inline-block',
          transition: 'transform 0.15s',
          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
          fontSize: '0.625rem',
        }}>
          &#9654;
        </span>
        Signature {activeLabel} &mdash; {project.version_count} older version{project.version_count !== 1 ? 's' : ''}
      </button>

      {expanded && (
        <div style={{
          marginTop: '0.5rem',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)',
          overflow: 'hidden',
        }}>
          {loading && (
            <div style={{ padding: '0.75rem', fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
              Loading versions...
            </div>
          )}

          {error && (
            <div style={{ padding: '0.75rem', fontSize: '0.8125rem', color: 'var(--color-danger)' }}>
              {error}
            </div>
          )}

          {versions && versions.length === 0 && (
            <div style={{ padding: '0.75rem', fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
              No archived versions found.
            </div>
          )}

          {versions && versions.map((v) => (
            <div
              key={v.version}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.5rem 0.75rem',
                borderBottom: '1px solid var(--color-border)',
                fontSize: '0.8125rem',
              }}
            >
              <img
                src={`/api/projects/${project.id}/versions/${v.version}/base-image`}
                alt={`v${v.version} base`}
                style={{
                  width: 48,
                  height: 48,
                  objectFit: 'cover',
                  borderRadius: 4,
                  flexShrink: 0,
                  background: 'var(--color-bg)',
                }}
                loading="lazy"
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500 }}>
                  v{v.version}
                  {v.door_style && (
                    <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '0.375rem' }}>
                      {v.door_style}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                  {new Date(v.created_at).toLocaleDateString()} &middot; {v.result_count} result{v.result_count !== 1 ? 's' : ''}
                  {v.style_notes && (
                    <span> &middot; {v.style_notes.length > 40 ? v.style_notes.slice(0, 40) + '...' : v.style_notes}</span>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleRestore(v.version)}
                disabled={restoring !== null}
                style={{
                  fontSize: '0.75rem',
                  padding: '0.25rem 0.5rem',
                  flexShrink: 0,
                }}
              >
                {restoring === v.version ? 'Restoring...' : 'Restore'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
