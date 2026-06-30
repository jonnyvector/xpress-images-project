import { useState, useMemo, type ReactNode } from 'react';
import type { Project } from '../types';
import LibraryCard from './LibraryCard';

interface Props {
  projects: Project[];
  onSelectProject: (id: string) => void;
  onRenameProject: (id: string, newName: string) => void;
  onDeleteProject: (id: string) => Promise<void>;
}

type ProductFilter = 'all' | 'Cabinet Door' | 'Drawer Front';
type MaterialFilter = 'all' | 'wood' | 'rtf';
type SortOption = 'name-asc' | 'name-desc' | 'variations-desc' | 'variations-asc';

export default function DoorLibrary({ projects, onSelectProject, onRenameProject, onDeleteProject }: Props) {
  const [productFilter, setProductFilter] = useState<ProductFilter>('all');
  const [materialFilter, setMaterialFilter] = useState<MaterialFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('name-asc');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function handleRenameSubmit(p: Project) {
    const trimmed = editName.trim();
    if (trimmed && trimmed !== p.name) {
      onRenameProject(p.id, trimmed);
    }
    setEditingId(null);
  }

  async function handleDeleteProject(p: Project) {
    const ok = window.confirm(`Delete "${p.name}" and all of its generated variations? This cannot be undone.`);
    if (!ok) return;
    setDeletingId(p.id);
    try {
      await onDeleteProject(p.id);
    } catch (err) {
      console.error('Failed to delete project:', err);
      window.alert('Failed to delete project. Please try again.');
    } finally {
      setDeletingId(null);
    }
  }

  const learned = projects.filter((p) => p.has_signature);
  const imported = projects.filter((p) => !p.has_signature && p.results.length > 0);

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

  const renderCard = (p: Project, thumbUrl: string | null, body: ReactNode) => (
    <LibraryCard
      key={p.id}
      project={p}
      thumbUrl={thumbUrl}
      isEditing={editingId === p.id}
      editName={editName}
      onEditNameChange={setEditName}
      onRenameSubmit={() => handleRenameSubmit(p)}
      onCancelEdit={() => setEditingId(null)}
      onStartEdit={() => {
        setEditingId(p.id);
        setEditName(p.name);
      }}
      isDeleting={deletingId === p.id}
      onDelete={() => handleDeleteProject(p)}
      onSelect={onSelectProject}
    >
      {body}
    </LibraryCard>
  );

  const importedDoors = imported.filter((p) => p.product_type !== 'Drawer Front');
  const importedDrawers = imported.filter((p) => p.product_type === 'Drawer Front');
  const importedSections: { label: string; items: Project[] }[] = [];
  if (importedDoors.length > 0) importedSections.push({ label: 'Imported Doors', items: importedDoors });
  if (importedDrawers.length > 0) importedSections.push({ label: 'Imported Drawer Fronts', items: importedDrawers });
  if (importedSections.length === 0 && imported.length > 0) {
    importedSections.push({ label: 'Imported', items: imported });
  }

  if (learned.length === 0 && imported.length === 0) {
    return (
      <div className="status-info">
        No door styles yet. Upload a door image and learn its style in a project tab to see it here.
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
          {filtered.map((p) =>
            renderCard(
              p,
              p.has_base_image ? `/api/projects/${p.id}/base-image` : null,
              <>
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
              </>,
            ),
          )}
        </div>
      )}

      {importedSections.map((section) => (
        <div key={section.label}>
          <h3 style={{ marginTop: '2rem', marginBottom: '0.75rem' }}>{section.label}</h3>
          <div className="library-grid">
            {section.items.map((p) =>
              renderCard(
                p,
                p.results.length > 0
                  ? `/api/projects/${p.id}/results/0/image?watermark=false`
                  : null,
                <div className="library-card-count">
                  {p.results.length} image{p.results.length !== 1 ? 's' : ''}
                </div>,
              ),
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
