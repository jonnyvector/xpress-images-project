import type { Project } from '../types';

interface Props {
  projects: Project[];
  activeId: string | null;
  activeView: 'library' | 'project';
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onSelectLibrary: () => void;
}

export default function TabBar({ projects, activeId, activeView, onSelect, onClose, onSelectLibrary }: Props) {
  return (
    <div className="tab-bar">
      <button
        className={`tab-item ${activeView === 'library' ? 'active' : ''}`}
        onClick={onSelectLibrary}
      >
        Library
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
