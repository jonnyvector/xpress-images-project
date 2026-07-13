// Top-level Coverage view: fetches /api/coverage once, holds the active
// sub-tab and the "only uncovered" filter, renders the active category, and
// hosts the Shopify CSV upload control.
import { useState, useEffect, useRef, useCallback } from 'react';
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
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .getCoverage()
      .then((resp) => {
        setData(resp);
        setActiveKey((prev) => prev ?? resp.categories[0]?.key ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load coverage'));
  }, []);

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileSelected = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-uploading a file with the same name
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    api
      .uploadShopifyCsv(file)
      .then(setData)
      .catch((err) => setUploadError(err instanceof Error ? err.message : 'Upload failed'))
      .finally(() => setUploading(false));
  }, []);

  if (error) return <div className="status-error">{error}</div>;
  if (!data) return <div className="status-info">Loading coverage…</div>;

  const active = data.categories.find((c) => c.key === activeKey) ?? data.categories[0];
  const approvedCount = active
    ? active.products.filter((p) => p.approved_total > 0 && p.approved_count === p.approved_total).length
    : 0;
  const onShopifyCount = active ? active.products.filter((p) => p.on_shopify === true).length : 0;

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

        <div style={{ marginLeft: 'auto' }}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            style={{ display: 'none' }}
            onChange={handleFileSelected}
          />
          <button type="button" onClick={handleUploadClick} disabled={uploading}>
            {uploading ? 'Uploading…' : 'Upload Shopify CSV'}
          </button>
        </div>
      </div>

      {uploadError && (
        <div className="status-error" style={{ marginBottom: '0.75rem' }}>
          {uploadError}
        </div>
      )}

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
