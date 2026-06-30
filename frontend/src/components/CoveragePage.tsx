// frontend/src/components/CoveragePage.tsx
// Top-level Coverage view: fetches /api/coverage once, holds the active
// sub-tab (one per best-seller category) and the "only uncovered" filter,
// and renders the selected category via CoverageTable.
import { useState, useEffect } from 'react';
import type { CoverageResponse } from '../types';
import * as api from '../api';
import CoverageTable from './CoverageTable';

interface Props {
  onOpenProject: (id: string) => void;
}

export default function CoveragePage({ onOpenProject }: Props) {
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [onlyUncovered, setOnlyUncovered] = useState(false);

  useEffect(() => {
    api
      .getCoverage()
      .then((resp) => {
        setData(resp);
        setActiveKey((prev) => prev ?? resp.categories[0]?.key ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load coverage'));
  }, []);

  if (error) return <div className="status-error">{error}</div>;
  if (!data) return <div className="status-info">Loading coverage…</div>;

  const active = data.categories.find((c) => c.key === activeKey) ?? data.categories[0];

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

      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem', fontSize: '0.875rem' }}>
        <input
          type="checkbox"
          checked={onlyUncovered}
          onChange={(e) => setOnlyUncovered(e.target.checked)}
        />
        Show only not-yet-generated
      </label>

      {active && (
        <CoverageTable
          category={active}
          onlyUncovered={onlyUncovered}
          onOpenProject={onOpenProject}
        />
      )}
    </div>
  );
}
