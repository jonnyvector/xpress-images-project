import type { Project, ActiveView } from '../types';

interface Props {
  projects: Project[];
  activeId: string | null;
  activeView: ActiveView;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onSelectView: (view: ActiveView) => void;
}

export default function TabBar({
  projects,
  activeId,
  activeView,
  onSelect,
  onClose,
  onSelectView,
}: Props) {
  return (
    <div className="tab-bar">
      <button
        className={`tab-item ${activeView === 'library' ? 'active' : ''}`}
        onClick={() => onSelectView('library')}
      >
        Library
      </button>
      <button
        className={`tab-item ${activeView === 'coverage' ? 'active' : ''}`}
        onClick={() => onSelectView('coverage')}
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
