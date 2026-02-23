import { useState, useEffect, useCallback } from 'react';
import type { Project, Swatch } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';

interface Props {
  project: Project;
}

export default function SwatchGrid({ project }: Props) {
  const dispatch = useDispatch();
  const [swatches, setSwatches] = useState<Swatch[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set(project.selected_swatches));

  useEffect(() => {
    api.listSwatches().then(setSwatches).catch(console.error);
  }, []);

  // Sync selected from project prop
  useEffect(() => {
    setSelected(new Set(project.selected_swatches));
  }, [project.selected_swatches]);

  const saveSelections = useCallback(async (keys: Set<string>) => {
    try {
      const updated = await api.updateProject(project.id, {
        selected_swatches: Array.from(keys),
      });
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
    } catch (err) {
      console.error('Failed to save swatch selection:', err);
    }
  }, [dispatch, project.id]);

  const toggleSwatch = useCallback((key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      saveSelections(next);
      return next;
    });
  }, [saveSelections]);

  const selectAll = useCallback(() => {
    const all = new Set(swatches.map((s) => s.key));
    setSelected(all);
    saveSelections(all);
  }, [swatches, saveSelections]);

  const clearAll = useCallback(() => {
    const empty = new Set<string>();
    setSelected(empty);
    saveSelections(empty);
  }, [saveSelections]);

  const realSwatches = swatches.filter((s) => !s.is_virtual);
  const virtualSwatches = swatches.filter((s) => s.is_virtual);

  return (
    <section style={{ marginTop: '1rem' }}>
      <h3>2. Select Wood Types</h3>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button onClick={selectAll} style={{ flex: 1 }}>Select All</button>
        <button onClick={clearAll} style={{ flex: 1 }}>Clear</button>
      </div>

      {realSwatches.length > 0 && (
        <>
          <strong style={{ fontSize: '0.8125rem' }}>Available Wood Types:</strong>
          <div className="swatch-grid" style={{ marginTop: '0.5rem' }}>
            {realSwatches.map((swatch) => (
              <div
                key={swatch.key}
                className={`swatch-item ${selected.has(swatch.key) ? 'selected' : ''}`}
                onClick={() => toggleSwatch(swatch.key)}
                style={{ cursor: 'pointer' }}
              >
                <img src={swatch.swatch_image_url} alt={swatch.name} />
                <label>
                  <input
                    type="checkbox"
                    checked={selected.has(swatch.key)}
                    onChange={() => toggleSwatch(swatch.key)}
                  />
                  {swatch.name}
                </label>
              </div>
            ))}
          </div>
        </>
      )}

      {virtualSwatches.length > 0 && (
        <>
          <strong style={{ fontSize: '0.8125rem', display: 'block', marginTop: '1rem' }}>
            Composite Material Types:
          </strong>
          {virtualSwatches.map((swatch) => (
            <div key={swatch.key} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: '0.5rem 0' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontWeight: 'normal' }}>
                <input
                  type="checkbox"
                  checked={selected.has(swatch.key)}
                  onChange={() => toggleSwatch(swatch.key)}
                />
                {swatch.name}
              </label>
              {swatch.reference_image_url && (
                <img
                  src={swatch.reference_image_url}
                  alt="Reference"
                  style={{ width: 60, borderRadius: 4 }}
                />
              )}
            </div>
          ))}
        </>
      )}

      <div style={{ marginTop: '0.75rem', fontSize: '0.875rem', fontWeight: 600 }}>
        Selected: {selected.size} / {swatches.length}
      </div>
    </section>
  );
}
