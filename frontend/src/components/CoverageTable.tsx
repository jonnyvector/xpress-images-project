// One coverage category: a row per product with sales, live Shopify image
// status, and a link to its canonical project. Each row expands into the
// Shopify detail and a ProductSignoffPanel. Presentational only.
import { Fragment, useState } from 'react';
import type { CoverageCategory, CoverageResponse, Project } from '../types';
import ProductSignoffPanel from './ProductSignoffPanel';
import { ShopifyBadge, ShopifyDetail } from './ShopifyListings';
import { isDone } from '../coverageStatus';

export type CoverageFilter = 'all' | 'done' | 'not_done';

interface Props {
  category: CoverageCategory;
  filter: CoverageFilter;
  onOpenProject: (id: string) => void;
  projects: Project[];
  onChanged: (r: CoverageResponse) => void;
  shopifyAdminUrl: string | null;
}

export default function CoverageTable({
  category,
  filter,
  onOpenProject,
  projects,
  onChanged,
  shopifyAdminUrl,
}: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const products = category.products.filter((p) =>
    filter === 'not_done' ? !isDone(p) : filter === 'done' ? isDone(p) : true,
  );

  return (
    <section>
      {products.length === 0 ? (
        <div className="status-info">
          {filter === 'not_done'
            ? 'Everything in this category is done.'
            : filter === 'done'
              ? 'Nothing in this category is done yet.'
              : 'No products.'}
        </div>
      ) : (
        <table className="coverage-table">
          <thead>
            <tr>
              <th style={{ width: '2rem' }} />
              <th>Product</th>
              <th style={{ textAlign: 'right' }}>Net sales</th>
              <th style={{ textAlign: 'right' }}>Units</th>
              <th>Shopify AI images</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <Fragment key={p.title}>
                <tr className={isDone(p) ? 'covered' : ''}>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setExpanded(expanded === p.title ? null : p.title)}
                    >
                      {expanded === p.title ? '▾' : '▸'}
                    </button>
                  </td>
                  <td>
                    {/* Linked once a canonical project is chosen — that is the
                        project this row is actually about. Linking on `covered`
                        instead would hide the link until sign-off, and opening
                        matched_project_ids[0] could land on a fuzzy match (a
                        stray *-test project) rather than the designated one. */}
                    {p.canonical_project_id ? (
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => onOpenProject(p.canonical_project_id as string)}
                        title="Open the canonical project for this product"
                      >
                        {p.title}
                      </button>
                    ) : (
                      p.title
                    )}
                  </td>
                  {/* Store products outside the sales CSV have no sales figures. */}
                  <td style={{ textAlign: 'right' }}>
                    {p.quantity
                      ? `$${p.net_sales.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                      : '—'}
                  </td>
                  <td style={{ textAlign: 'right' }}>{p.quantity ? p.quantity.toLocaleString() : '—'}</td>
                  <td>
                    <ShopifyBadge product={p} />
                  </td>
                </tr>
                {expanded === p.title && (
                  <tr>
                    <td colSpan={5}>
                      <ShopifyDetail listings={p.shopify_listings} adminUrl={shopifyAdminUrl} />
                      <ProductSignoffPanel product={p} projects={projects} onChanged={onChanged} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
