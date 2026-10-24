// Coverage: per category, how many best-selling products are done (variants
// signed off AND on Shopify signed off), with live Shopify data alongside.
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router';
import type { CoverageResponse } from '../types';
import * as api from '../api';
import { useProjects } from '../context/ProjectsContext';
import { isDone, shopifyDisagrees } from '../coverageStatus';
import CoverageTable, { type CoverageFilter } from './CoverageTable';
import Segmented from './Segmented';

export default function CoveragePage() {
  const navigate = useNavigate();
  const { projects } = useProjects();
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [filter, setFilter] = useState<CoverageFilter>('all');
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
  const products = active?.products ?? [];
  const done = products.filter(isDone).length;
  const variantsSigned = products.filter((p) => p.variations_complete).length;
  const shopifySigned = products.filter((p) => p.in_shopify).length;
  const disagree = products.filter(shopifyDisagrees).length;
  const pct = products.length ? Math.round((done / products.length) * 100) : 0;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Coverage</h1>
        <div className="coverage-sync">
          <span>{syncLabel(data)}</span>
          <button type="button" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? 'Reading Shopify…' : 'Refresh from Shopify'}
          </button>
        </div>
      </header>

      {refreshError && (
        <div className="status-error" style={{ marginBottom: '0.75rem' }}>
          {refreshError}
        </div>
      )}

      <div className="tab-bar coverage-tabs">
        {data.categories.map((c) => (
          <button
            key={c.key}
            type="button"
            className={`tab-item ${c.key === active?.key ? 'active' : ''}`}
            onClick={() => setActiveKey(c.key)}
          >
            {c.label} <span className="coverage-tab-count">{c.products.filter(isDone).length}/{c.total}</span>
          </button>
        ))}
      </div>

      {active && (
        <>
          <div className="coverage-summary">
            <div className="coverage-done">
              <strong>{done}</strong> of {products.length} done
              <div className="progress-bar">
                <div className="fill" style={{ width: `${pct}%` }} />
              </div>
            </div>
            <div className="coverage-parts">
              Done = variants signed off <em>and</em> on Shopify signed off.
              <br />
              {variantsSigned} have variants signed off · {shopifySigned} signed off as on Shopify
            </div>
          </div>

          <Segmented<CoverageFilter>
            className="coverage-filter"
            value={filter}
            onChange={setFilter}
            options={[
              ['all', `All (${products.length})`],
              ['not_done', `Not done (${products.length - done})`],
              ['disagree', `Shopify disagrees (${disagree})`],
            ]}
          />

          <CoverageTable
            category={active}
            filter={filter}
            onOpenProject={(id) => navigate(`/doors/${id}`)}
            projects={projects}
            onChanged={setData}
            shopifyAdminUrl={data.shopify_admin_url}
          />
        </>
      )}
    </div>
  );
}

function syncLabel(data: CoverageResponse): string {
  if (data.shopify_error) return `${data.shopify_error}. Refresh to fix.`;
  const syncedAt = data.shopify_synced_at ? new Date(data.shopify_synced_at) : null;
  if (data.shopify_source === 'live' && syncedAt && !Number.isNaN(syncedAt.getTime())) {
    const mins = Math.round((Date.now() - syncedAt.getTime()) / 60000);
    if (mins < 1) return 'Shopify synced just now';
    if (mins < 60) return `Shopify synced ${mins} min ago`;
    if (mins < 60 * 24) return `Shopify synced ${Math.round(mins / 60)} h ago`;
    return `Shopify synced ${syncedAt.toLocaleDateString()}`;
  }
  if (data.shopify_source === 'csv') return 'Using an old Shopify CSV';
  return 'Not synced with Shopify yet';
}
