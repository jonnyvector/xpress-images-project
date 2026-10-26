// Command center: every active door and drawer front on Shopify, hottest
// sellers first, with how many of its variants have an AI image live on
// Shopify, generated here but not uploaded, or nothing yet.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import type { CatalogProduct, CatalogResponse } from '../types';
import * as api from '../api';
import { syncedAgo } from '../shopifySync';
import Segmented from './Segmented';
import CellBar from './CellBar';

type StatusFilter = 'needs' | 'done' | 'all';
const STATUSES: readonly StatusFilter[] = ['needs', 'done', 'all'];

export default function ProductsPage() {
  const [data, setData] = useState<CatalogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [params, setParams] = useSearchParams();
  const statusParam = params.get('status');
  const status = STATUSES.find((s) => s === statusParam) ?? 'needs';
  const category = params.get('cat') ?? 'all';
  const query = params.get('q') ?? '';

  const setParam = useCallback(
    (key: string, value: string, fallback: string) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value === fallback) next.delete(key);
          else next.set(key, value);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  const load = useCallback(
    () =>
      api
        .getCatalog()
        .then(setData)
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load products')),
    [],
  );

  useEffect(() => {
    load();
  }, [load]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    setError(null);
    api
      .refreshShopify()
      .then(load)
      .catch((err) => setError(err instanceof Error ? err.message : 'Refresh failed'))
      .finally(() => setRefreshing(false));
  }, [load]);

  // Categories come from the data, so they always match the backend's.
  const categoryOptions = useMemo(() => {
    const labels = new Map((data?.products ?? []).map((p) => [p.category, p.category_label]));
    return [['all', 'All'] as const, ...labels];
  }, [data]);
  const inCategory = useMemo(
    () => (data?.products ?? []).filter((p) => category === 'all' || p.category === category),
    [data, category],
  );
  const doneCount = inCategory.filter((p) => p.done).length;
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return inCategory.filter(
      (p) =>
        (status === 'all' || (status === 'done') === p.done) && (!q || p.title.toLowerCase().includes(q)),
    );
  }, [inCategory, status, query]);

  return (
    <div className="page">
      <header className="page-header">
        <h1>Products</h1>
        <div className="coverage-sync">
          <span>{data ? syncedAgo(data.synced_at) ?? 'Not synced with Shopify yet' : ''}</span>
          <button type="button" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? 'Reading Shopify…' : 'Refresh from Shopify'}
          </button>
        </div>
      </header>

      {error && <div className="status-error products-notice">{error}</div>}
      {data?.error && <div className="status-error products-notice">{data.error}</div>}
      {data?.sales_error && (
        <div className="status-info products-notice">
          No sales data ({data.sales_error}). Run scripts/shopauth.sh, then refresh.
        </div>
      )}
      {!data && !error && <div className="status-info">Loading products…</div>}

      {data && !data.error && (
        <>
          <p className="products-intro">
            Every active door and drawer front on Shopify, best sellers first
            {data.sales_days ? ` (units sold in the last ${data.sales_days} days)` : ''}. Each bar shows its
            variants: <span className="legend legend--live">AI image on Shopify</span>
            <span className="legend legend--generated">generated, not uploaded</span>
            <span className="legend legend--missing">no image</span>
          </p>

          <div className="products-controls">
            <Segmented<StatusFilter>
              value={status}
              onChange={(v) => setParam('status', v, 'needs')}
              options={[
                ['needs', `Needs work (${inCategory.length - doneCount})`],
                ['done', `Done (${doneCount})`],
                ['all', `All (${inCategory.length})`],
              ]}
            />
            <Segmented<string>
              value={category}
              onChange={(v) => setParam('cat', v, 'all')}
              options={categoryOptions}
            />
            <input
              type="search"
              className="products-search"
              placeholder="Search products"
              value={query}
              onChange={(e) => setParam('q', e.target.value, '')}
              aria-label="Search products"
            />
          </div>

          {shown.length === 0 ? (
            <div className="status-info">No products match.</div>
          ) : (
            <table className="coverage-table products-table">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Product</th>
                  <th className="num">Units sold</th>
                  <th>Variants</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((p) => (
                  <ProductRow key={p.handle} product={p} rank={data.products.indexOf(p) + 1} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

function ProductRow({ product: p, rank }: { product: CatalogProduct; rank: number }) {
  return (
    <tr className={p.done ? 'covered' : ''}>
      <td className="num muted">{rank}</td>
      <td>
        <Link to={`/products/${p.handle}`}>{p.title}</Link>
        <div className="products-sub">{p.category_label}</div>
      </td>
      <td className="num">{p.units ? p.units.toLocaleString() : '—'}</td>
      <td className="products-cells">
        <CellBar live={p.live} generated={p.generated} missing={p.missing} />
        <span className="products-counts">
          {p.done ? (
            <>✓ All {p.variant_count} live</>
          ) : (
            <>
              {p.live} live
              {p.generated > 0 && <> · {p.generated} generated</>}
              {p.missing > 0 && <> · {p.missing} missing</>}
            </>
          )}
        </span>
      </td>
    </tr>
  );
}
