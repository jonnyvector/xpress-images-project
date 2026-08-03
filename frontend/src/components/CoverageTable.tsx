// Renders one best-seller category as a coverage checklist: a header summary
// with a progress bar, then one row per product showing covered status, sales
// figures, approval progress, Shopify status, and a link to the matched
// project. Each row expands into a ProductSignoffPanel for recording the two
// sign-off gates. Presentational only — projects/onChanged are passed through.
import { Fragment, useState } from 'react';
import type { CoverageCategory, CoverageResponse, Project } from '../types';
import ProductSignoffPanel from './ProductSignoffPanel';

interface Props {
  category: CoverageCategory;
  onlyUncovered: boolean;
  onOpenProject: (id: string) => void;
  projects: Project[];
  onChanged: (r: CoverageResponse) => void;
}

export default function CoverageTable({ category, onlyUncovered, onOpenProject, projects, onChanged }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const products = onlyUncovered
    ? category.products.filter((p) => !p.variations_complete)
    : category.products;

  const pct = category.total > 0 ? Math.round((category.variations_complete / category.total) * 100) : 0;

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
        <h3 style={{ margin: 0 }}>
          {category.variations_complete} / {category.total} variations complete
          {' · '}
          {category.in_shopify_count} / {category.total} in Shopify
        </h3>
        <div className="progress-bar" style={{ flex: 1, maxWidth: 240 }}>
          <div className="fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {products.length === 0 ? (
        <div className="status-info">
          {onlyUncovered ? 'Everything in this category has been generated.' : 'No products.'}
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
                    {p.covered && p.matched_project_ids.length > 0 ? (
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => onOpenProject(p.matched_project_ids[0])}
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
                    {p.on_shopify === true ? (
                      <span className="badge badge-approved">On Shopify</span>
                    ) : p.on_shopify === false ? (
                      <span className="badge badge-warn">Missing images</span>
                    ) : (
                      <span className="badge badge-muted">—</span>
                    )}
                  </td>
                </tr>
                {expanded === p.title && (
                  <tr>
                    <td colSpan={6}>
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
