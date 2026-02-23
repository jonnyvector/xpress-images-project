import type { Project } from '../types';

interface Props {
  projects: Project[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
}

export default function TabBar({ projects, activeId, onSelect, onClose }: Props) {
  return (
    <div className="tab-bar">
      {projects.map((p) => (
        <button
          key={p.id}
          className={`tab-item ${p.id === activeId ? 'active' : ''}`}
          onClick={() => onSelect(p.id)}
        >
          {p.name}
          {projects.length > 1 && (
            <span
              className="close-btn"
              onClick={(e) => {
                e.stopPropagation();
                onClose(p.id);
              }}
            >
              x
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
