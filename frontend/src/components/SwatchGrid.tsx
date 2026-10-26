import { useState, useEffect, useCallback, useRef } from 'react';
import type { DoorShopifyColors, Project, Swatch } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import { onError } from '../notify';

interface Props {
  project: Project;
}

export default function SwatchGrid({ project }: Props) {
  const dispatch = useDispatch();
  const [swatches, setSwatches] = useState<Swatch[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set(project.selected_swatches));
  const [saveError, setSaveError] = useState<string | null>(null);

  const materialType = project.material_type || 'wood';

  useEffect(() => {
    api.listSwatches(materialType).then(setSwatches).catch(onError("Couldn't load swatches"));
  }, [materialType]);

  // Only the colours this door's Shopify listing sells are worth generating.
  const [onShopify, setOnShopify] = useState<DoorShopifyColors | null>(null);
  const [scopeError, setScopeError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    let stale = false;
    setOnShopify(null);
    setScopeError(null);
    api
      .getDoorShopifyColors(project.id)
      .then((c) => !stale && setOnShopify(c))
      .catch((e) => {
        if (stale) return;
        // 409 = no per-variant snapshot yet: an expected state, not a failure.
        if (!(e instanceof api.ApiError && e.status === 409)) onError("Couldn't read the Shopify colours")(e);
        setScopeError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      stale = true;
    };
  }, [project.id]);
  const listingKeys = onShopify?.listings.length ? new Set(onShopify.swatch_keys) : null;
  // Selected swatches stay visible even when off-listing, so nothing is picked unseen.
  const visible = listingKeys && !showAll
    ? swatches.filter((s) => listingKeys.has(s.key) || selected.has(s.key))
    : swatches;

  // Sync selected from project prop
  useEffect(() => {
    setSelected(new Set(project.selected_swatches));
  }, [project.selected_swatches]);

  // Each toggle PATCHes the whole selection set. Sent concurrently, those
  // requests race and the server keeps whichever ARRIVES last rather than
  // whichever was clicked last — so a deselected swatch can survive on the
  // server and get generated. Chaining the writes makes the server settle on
  // the last set clicked; the sequence guard keeps a superseded response from
  // clobbering newer local state.
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  const saveSeqRef = useRef(0);

  const saveSelections = useCallback((keys: Set<string>) => {
    const seq = ++saveSeqRef.current;
    saveChainRef.current = saveChainRef.current.then(async () => {
      try {
        const updated = await api.updateProject(project.id, {
          selected_swatches: Array.from(keys),
        });
        if (seq !== saveSeqRef.current) return; // a newer toggle superseded this
        dispatch({ type: 'UPDATE_PROJECT', project: updated });
        setSaveError(null);
      } catch (err) {
        console.error('Failed to save swatch selection:', err);
        // Silent failure previously let generation run against a selection the
        // operator never confirmed. Surface it instead.
        setSaveError(
          'Swatch selection did not save. Reload before generating — the server '
          + 'may still hold a different selection.',
        );
      }
    });
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
    const all = new Set(visible.map((s) => s.key));
    setSelected(all);
    saveSelections(all);
  }, [visible, saveSelections]);

  const clearAll = useCallback(() => {
    const empty = new Set<string>();
    setSelected(empty);
    saveSelections(empty);
  }, [saveSelections]);

  const realSwatches = visible.filter((s) => !s.is_virtual);
  const virtualSwatches = visible.filter((s) => s.is_virtual);
  const noun = materialType === 'rtf' ? 'colors' : 'wood types';
  const missing = new Set(project.missing_swatches);

  return (
    <section style={{ marginTop: '1rem' }}>
      <h3>{materialType === 'rtf' ? 'Colors' : 'Wood types'}</h3>

      {saveError && (
        <div
          role="alert"
          style={{
            marginBottom: '0.75rem',
            padding: '0.5rem 0.75rem',
            border: '1px solid #b00',
            borderRadius: '4px',
            color: '#b00',
            fontSize: '0.85rem',
          }}
        >
          {saveError}
        </div>
      )}

      {listingKeys ? (
        <div className="swatch-scope">
          {showAll ? `Showing all ${swatches.length} ${noun}.` : (
            <>
              Showing the {listingKeys.size} {noun} sold on{' '}
              {onShopify!.listings.map((l) => l.title).join(', ')}.
            </>
          )}{' '}
          <button type="button" className="link-button" onClick={() => setShowAll((v) => !v)}>
            {showAll ? 'Only Shopify ones' : `Show all ${swatches.length}`}
          </button>
          {onShopify!.unmatched.length > 0 && (
            <div className="swatch-scope-missing">
              On Shopify but no swatch here: {onShopify!.unmatched.join(', ')}
            </div>
          )}
        </div>
      ) : onShopify ? (
        <div className="swatch-scope">
          No Shopify listing matches this door, so all {noun} are shown.
        </div>
      ) : scopeError && (
        <div className="swatch-scope">
          All {noun} shown: {scopeError}
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button
          onClick={selectAll}
          disabled={!onShopify && !scopeError}
          title={!onShopify && !scopeError ? 'Reading the Shopify colours…' : undefined}
          style={{ flex: 1 }}
        >
          Select All
        </button>
        <button onClick={clearAll} style={{ flex: 1 }}>Clear</button>
      </div>

      {realSwatches.length > 0 && (
        <>
          <strong style={{ fontSize: '0.8125rem' }}>
            {materialType === 'rtf' ? 'Available Colors:' : 'Available Wood Types:'}
          </strong>
          <div className="swatch-grid" style={{ marginTop: '0.5rem' }}>
            {realSwatches.map((swatch) => {
              const isMissing = missing.has(swatch.name);
              return (
                <div
                  key={swatch.key}
                  className={`swatch-item ${selected.has(swatch.key) ? 'selected' : ''}`}
                  onClick={() => toggleSwatch(swatch.key)}
                  title={isMissing ? 'No variant generated for this yet' : undefined}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="swatch-thumb">
                    <img src={swatch.swatch_image_url} alt={swatch.name} />
                    {isMissing && <span className="swatch-missing">Not generated</span>}
                  </div>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.has(swatch.key)}
                      onChange={() => toggleSwatch(swatch.key)}
                    />
                    {swatch.name}
                  </label>
                </div>
              );
            })}
          </div>
        </>
      )}

      {virtualSwatches.length > 0 && (
        <>
          <strong style={{ fontSize: '0.8125rem', display: 'block', marginTop: '1rem' }}>
            Composite Material Types:
          </strong>
          {virtualSwatches.map((swatch) => {
            const isMissing = missing.has(swatch.name);
            return (
              <div key={swatch.key} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: '0.5rem 0' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontWeight: 'normal' }}>
                  <input
                    type="checkbox"
                    checked={selected.has(swatch.key)}
                    onChange={() => toggleSwatch(swatch.key)}
                  />
                  {swatch.name}
                  {isMissing && (
                    <span style={{ color: '#c0392b', fontWeight: 600 }}> ● not generated</span>
                  )}
                </label>
                {swatch.reference_image_url && (
                  <img
                    src={swatch.reference_image_url}
                    alt="Reference"
                    style={{ width: 60, borderRadius: 4 }}
                  />
                )}
              </div>
            );
          })}
        </>
      )}

      <div style={{ marginTop: '0.75rem', fontSize: '0.875rem', fontWeight: 600 }}>
        Selected: {selected.size} / {visible.length}
        {selected.size > 5 && (
          <div style={{ color: '#b59f3b', fontWeight: 400 }}>
            Stage B limit: batches over 5 are blocked until bulk is unlocked
          </div>
        )}
      </div>
    </section>
  );
}
