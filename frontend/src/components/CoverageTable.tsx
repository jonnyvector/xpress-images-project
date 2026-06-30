// Renders one best-seller category as a coverage checklist: a header summary
// with a progress bar, then one row per product showing covered status, sales
// figures, and a link to the matched project. Presentational only.
import type { CoverageCategory } from '../types';

interface Props {
  category: CoverageCategory;
  onlyUncovered: boolean;
  onOpenProject: (id: string) => void;
}

export default function CoverageTable({ category, onlyUncovered, onOpenProject }: Props) {
  const products = onlyUncovered
    ? category.products.filter((p) => !p.covered)
    : category.products;

  const pct = category.total > 0 ? Math.round((category.covered / category.total) * 100) : 0;

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
        <h3 style={{ margin: 0 }}>
          {category.covered} / {category.total} generated
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
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.title} className={p.covered ? 'covered' : ''}>
                <td style={{ textAlign: 'center' }}>{p.covered ? '✓' : '○'}</td>
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
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
