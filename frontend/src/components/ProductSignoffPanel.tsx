// Per-product sign-off: canonical project, palette checklist, two gates.
// Coverage is decided ONLY by the two gates here — the palette grid is
// evidence to make that judgment fast, never an input to it.
import { useState } from 'react';
import type { CoverageProduct, CoverageResponse, Project } from '../types';
import * as api from '../api';

interface Props {
  product: CoverageProduct;
  projects: Project[];
  onChanged: (r: CoverageResponse) => void;
}

export default function ProductSignoffPanel({ product, projects, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const candidates = projects.filter((p) => product.matched_project_ids.includes(p.id));

  const run = async (fn: () => Promise<CoverageResponse>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  const signoff = (gate: 'variations' | 'shopify', value: boolean) =>
    run(async () => {
      try {
        return await api.setSignoff(product.title, gate, value);
      } catch (err) {
        // 409 = colours still missing per the backend's gap check. Confirm,
        // then re-send acknowledged. When there's no canonical project the
        // backend's message ("N colours still missing") is misleading — it's
        // comparing against nothing, not reporting a real gap — so show our
        // own neutral wording instead of the raw server message in that case.
        const msg = err instanceof Error ? err.message : '';
        if (gate === 'variations' && value && msg) {
          const confirmMsg = product.gap
            ? msg
            : 'No canonical project selected — nothing to compare against.';
          if (window.confirm(`${confirmMsg}\n\nSign off anyway?`)) {
            return api.setSignoff(product.title, gate, value, true);
          }
        }
        throw err;
      }
    });

  const toggleColor = (color: string) => {
    const next = product.excluded_colors.includes(color)
      ? product.excluded_colors.filter((c) => c !== color)
      : [...product.excluded_colors, color];
    return run(() => api.setExclusions(product.title, next));
  };

  return (
    <div style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.03)' }}>
      {error && <div className="status-error">{error}</div>}
      {product.stale && (
        <div className="status-info">
          The canonical project changed since sign-off. Re-check and sign off again.
        </div>
      )}

      <label style={{ display: 'block', marginBottom: '0.5rem' }}>
        Canonical project:{' '}
        {candidates.length === 0 ? (
          <span className="status-info" style={{ display: 'inline' }}>
            No matching projects found yet — projects may still be loading, or none
            match this product.
          </span>
        ) : (
          <select
            value={product.canonical_project_id ?? ''}
            disabled={busy}
            onChange={(e) => run(() => api.setCanonicalProject(product.title, e.target.value))}
          >
            <option value="" disabled>Pick one…</option>
            {candidates.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({new Set(p.results.map((r) => r.wood_name)).size} colors)
              </option>
            ))}
          </select>
        )}
      </label>

      {product.gap ? (
        <>
          <div style={{ fontSize: '0.85rem', marginBottom: '0.35rem' }}>
            {product.gap.generated}/{product.gap.expected} generated
            {product.gap.missing.length > 0 && (
              <> — missing: {product.gap.missing.join(', ')}</>
            )}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
            {[...product.gap.missing, ...product.gap.excluded].sort().map((color) => {
              const excluded = product.excluded_colors.includes(color);
              return (
                <button
                  key={color}
                  disabled={busy}
                  onClick={() => toggleColor(color)}
                  title={excluded ? 'Marked not needed — click to require' : 'Click to mark not needed'}
                  style={{
                    fontSize: '0.75rem',
                    padding: '0.1rem 0.4rem',
                    opacity: excluded ? 0.45 : 1,
                    textDecoration: excluded ? 'line-through' : 'none',
                  }}
                >
                  {color}
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <div className="status-info">
          No canonical project selected — nothing to compare against.
        </div>
      )}

      <div style={{ marginTop: '0.6rem', display: 'flex', gap: '1rem' }}>
        <label>
          <input
            type="checkbox"
            checked={product.variations_complete}
            disabled={busy}
            onChange={(e) => signoff('variations', e.target.checked)}
          />{' '}
          All variations generated
        </label>
        <label>
          <input
            type="checkbox"
            checked={product.in_shopify}
            disabled={busy}
            onChange={(e) => signoff('shopify', e.target.checked)}
          />{' '}
          Uploaded to Shopify
        </label>
      </div>
    </div>
  );
}
