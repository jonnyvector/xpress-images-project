// Renders one best-seller category as a coverage checklist: a header summary
// with a progress bar, then one row per product showing covered status, sales
// figures, approval progress, Shopify status, and a link to the matched
// project. Each row expands into a ProductSignoffPanel for recording the two
// sign-off gates. Presentational only — projects/onChanged are passed through.
import { Fragment, useState } from 'react';
import type { CoverageCategory, CoverageResponse, Project } from '../types';
import ProductSignoffPanel from './ProductSignoffPanel';
import { ShopifyBadge, ShopifyDetail } from './ShopifyListings';
import { isDone, shopifyDisagrees } from '../coverageStatus';

export type CoverageFilter = 'all' | 'not_done' | 'disagree';

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
    filter === 'not_done' ? !isDone(p) : filter === 'disagree' ? shopifyDisagrees(p) : true,
  );

  return (
    <section>
      {products.length === 0 ? (
        <div className="status-info">
          {filter === 'not_done'
            ? 'Everything in this category is done.'
            : filter === 'disagree'
              ? 'Shopify agrees with every sign-off here.'
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
              <th>Approved</th>
              <th>On Shopify</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <Fragment key={p.title}>
                <tr className={p.variations_complete ? 'covered' : ''}>
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
                  <td style={{ textAlign: 'right' }}>
                    ${p.net_sales.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </td>
                  <td style={{ textAlign: 'right' }}>{p.quantity.toLocaleString()}</td>
                  <td>
                    {p.approved_total > 0 ? (
                      <span
                        className={`badge ${p.approved_count === p.approved_total ? 'badge-approved' : 'badge-partial'}`}
                      >
                        {p.approved_count}/{p.approved_total} approved
                      </span>
                    ) : (
                      <span className="badge badge-muted">—</span>
                    )}
                  </td>
                  <td>
                    <ShopifyBadge product={p} />
                  </td>
                </tr>
                {expanded === p.title && (
                  <tr>
                    <td colSpan={6}>
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
