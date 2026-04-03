import { useState, useMemo } from 'react';
import type { Project } from '../types';

interface Props {
  projects: Project[];
  onSelectProject: (id: string) => void;
  onRenameProject: (id: string, newName: string) => void;
}

type ProductFilter = 'all' | 'Cabinet Door' | 'Drawer Front';
type MaterialFilter = 'all' | 'wood' | 'rtf';
type SortOption = 'name-asc' | 'name-desc' | 'variations-desc' | 'variations-asc';

export default function DoorLibrary({ projects, onSelectProject, onRenameProject }: Props) {
  const [productFilter, setProductFilter] = useState<ProductFilter>('all');
  const [materialFilter, setMaterialFilter] = useState<MaterialFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('name-asc');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  function handleRenameSubmit(p: Project) {
    const trimmed = editName.trim();
    if (trimmed && trimmed !== p.name) {
      onRenameProject(p.id, trimmed);
    }
    setEditingId(null);
  }

  const learned = projects.filter((p) => p.has_signature);

  const filtered = useMemo(() => {
    let items = learned;
    if (productFilter !== 'all') {
      items = items.filter((p) => p.product_type === productFilter);
    }
    if (materialFilter !== 'all') {
      items = items.filter((p) => p.material_type === materialFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      items = items.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.door_style && p.door_style.toLowerCase().includes(q))
      );
    }
    items.sort((a, b) => {
      switch (sortBy) {
        case 'name-asc':
          return a.name.localeCompare(b.name);
        case 'name-desc':
          return b.name.localeCompare(a.name);
        case 'variations-desc':
          return b.results.length - a.results.length;
        case 'variations-asc':
          return a.results.length - b.results.length;
      }
    });
    return items;
  }, [learned, productFilter, materialFilter, searchQuery, sortBy]);

  if (learned.length === 0) {
    return (
      <div className="status-info">
        No learned door styles yet. Upload a door image and learn its style in a project tab to see it here.
      </div>
    );
  }

  return (
    <div>
      <div className="library-toolbar">
        <input
          type="text"
          className="library-search"
          placeholder="Search by name or style..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <div className="filter-group">
          {(['all', 'Cabinet Door', 'Drawer Front'] as ProductFilter[]).map((v) => (
            <button
              key={v}
              className={`filter-btn${productFilter === v ? ' active' : ''}`}
              onClick={() => setProductFilter(v)}
            >
              {v === 'all' ? 'All' : v === 'Cabinet Door' ? 'Cabinet Doors' : 'Drawer Fronts'}
            </button>
          ))}
        </div>
        <div className="filter-group">
          {(['all', 'wood', 'rtf'] as MaterialFilter[]).map((v) => (
            <button
              key={v}
              className={`filter-btn${materialFilter === v ? ' active' : ''}`}
              onClick={() => setMaterialFilter(v)}
            >
              {v === 'all' ? 'All' : v === 'wood' ? 'Wood' : 'RTF'}
            </button>
          ))}
        </div>
        <select
          className="library-sort"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortOption)}
        >
          <option value="name-asc">Name (A→Z)</option>
          <option value="name-desc">Name (Z→A)</option>
          <option value="variations-desc">Most variations</option>
          <option value="variations-asc">Fewest variations</option>
        </select>
      </div>

      <div className="library-result-count">
        Showing {filtered.length} of {learned.length}
      </div>

      {filtered.length === 0 ? (
        <div className="status-info">
          No matches — try adjusting your filters
        </div>
      ) : (
        <div className="library-grid">
          {filtered.map((p) => (
            <button
              key={p.id}
              className="library-card"
              onClick={() => onSelectProject(p.id)}
            >
              {p.has_base_image && (
                <img
                  src={`/api/projects/${p.id}/base-image`}
                  alt={p.name}
                  className="library-card-thumb"
                />
              )}
              <div className="library-card-info">
                {editingId === p.id ? (
                  <input
                    className="library-card-name-input"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onBlur={() => handleRenameSubmit(p)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameSubmit(p);
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    autoFocus
                  />
                ) : (
                  <div
                    className="library-card-name"
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      setEditingId(p.id);
                      setEditName(p.name);
                    }}
                    title="Double-click to rename"
                  >
                    {p.name}
                  </div>
                )}
                {p.door_style && (
                  <div className="library-card-style">{p.door_style}</div>
                )}
                <div className="library-card-badges">
                  <span className="badge badge-product">{p.product_type}</span>
                  <span className="badge badge-material">
                    {p.material_type === 'rtf' ? 'RTF' : 'Wood'}
                  </span>
                </div>
                <div className="library-card-count">
                  {p.results.length} variation{p.results.length !== 1 ? 's' : ''}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
