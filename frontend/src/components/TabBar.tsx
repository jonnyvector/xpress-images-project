import type { Project } from '../types';

interface Props {
  projects: Project[];
  activeId: string | null;
  activeView: 'library' | 'project' | 'coverage';
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onSelectLibrary: () => void;
  onSelectCoverage: () => void;
}

export default function TabBar({
  projects,
  activeId,
  activeView,
  onSelect,
  onClose,
  onSelectLibrary,
  onSelectCoverage,
}: Props) {
  return (
    <div className="tab-bar">
      <button
        className={`tab-item ${activeView === 'library' ? 'active' : ''}`}
        onClick={onSelectLibrary}
      >
        Library
      </button>
      <button
        className={`tab-item ${activeView === 'coverage' ? 'active' : ''}`}
        onClick={onSelectCoverage}
      >
        Coverage
      </button>
      {projects.map((p) => (
        <button
          key={p.id}
          className={`tab-item ${p.id === activeId && activeView === 'project' ? 'active' : ''}`}
          onClick={() => onSelect(p.id)}
        >
          {p.name}
          <span
            className="close-btn"
            onClick={(e) => {
              e.stopPropagation();
              onClose(p.id);
            }}
          >
            x
          </span>
        </button>
      ))}
    </div>
  );
}
