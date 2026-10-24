// Top-level Coverage view: fetches /api/coverage once, holds the active
// sub-tab and the "only uncovered" filter, renders the active category, and
// hosts the Refresh from Shopify control.
import { useState, useEffect, useCallback } from 'react';
import type { CoverageResponse } from '../types';
import * as api from '../api';
import CoverageTable from './CoverageTable';
import { useProjects } from '../context/ProjectsContext';

interface Props {
  onOpenProject: (id: string) => void;
}

export default function CoveragePage({ onOpenProject }: Props) {
  const { projects } = useProjects();
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [onlyUncovered, setOnlyUncovered] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    api
      .getCoverage()
      .then((resp) => {
        setData(resp);
        setActiveKey((prev) => prev ?? resp.categories[0]?.key ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load coverage'));
  }, []);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    setRefreshError(null);
    api
      .refreshShopify()
      .then(setData)
      // Shown inline rather than as a toast: a lapsed login says which script to run.
      .catch((err) => setRefreshError(err instanceof Error ? err.message : 'Refresh failed'))
      .finally(() => setRefreshing(false));
  }, []);

  if (error) return <div className="status-error">{error}</div>;
  if (!data) return <div className="status-info">Loading coverage…</div>;

  const active = data.categories.find((c) => c.key === activeKey) ?? data.categories[0];
  const approvedCount = active
    ? active.products.filter((p) => p.approved_total > 0 && p.approved_count === p.approved_total).length
    : 0;
  const onShopifyCount = active
    ? active.products.filter((p) => p.in_shopify || p.on_shopify === true).length
    : 0;

  return (
    <div>
      <div className="tab-bar" style={{ marginBottom: '1rem' }}>
        {data.categories.map((c) => (
          <button
            key={c.key}
            className={`tab-item ${c.key === active?.key ? 'active' : ''}`}
            onClick={() => setActiveKey(c.key)}
          >
            {c.label} ({c.covered}/{c.total})
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.875rem' }}>
          <input
            type="checkbox"
            checked={onlyUncovered}
            onChange={(e) => setOnlyUncovered(e.target.checked)}
          />
          Show only not-yet-generated
        </label>

        {active && (
          <span style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
            {approvedCount}/{active.total} approved · {onShopifyCount}/{active.total} on Shopify
          </span>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
            {syncLabel(data)}
          </span>
          <button type="button" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? 'Reading Shopify…' : 'Refresh from Shopify'}
          </button>
        </div>
      </div>

      {refreshError && (
        <div className="status-error" style={{ marginBottom: '0.75rem' }}>
          {refreshError}
        </div>
      )}

      {active && (
        <CoverageTable
          category={active}
          onlyUncovered={onlyUncovered}
          onOpenProject={onOpenProject}
          projects={projects}
          onChanged={setData}
          shopifyAdminUrl={data.shopify_admin_url}
        />
      )}
    </div>
  );
}

function syncLabel(data: CoverageResponse): string {
  if (data.shopify_error) return `${data.shopify_error}. Refresh to fix.`;
  if (data.shopify_source === 'live' && data.shopify_synced_at) {
    const mins = Math.round((Date.now() - new Date(data.shopify_synced_at).getTime()) / 60000);
    if (mins < 1) return 'Synced just now';
    if (mins < 60) return `Synced ${mins} min ago`;
    if (mins < 60 * 24) return `Synced ${Math.round(mins / 60)} h ago`;
    return `Synced ${new Date(data.shopify_synced_at).toLocaleDateString()}`;
  }
  if (data.shopify_source === 'csv') return 'Using old CSV upload';
  return 'Not synced with Shopify yet';
}
