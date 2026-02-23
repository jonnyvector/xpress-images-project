import type { Project } from '../types';

interface Props {
  projects: Project[];
  onSelectProject: (id: string) => void;
}

export default function DoorLibrary({ projects, onSelectProject }: Props) {
  const learned = projects.filter((p) => p.has_signature);

  if (learned.length === 0) {
    return (
      <div className="status-info">
        No learned door styles yet. Upload a door image and learn its style in a project tab to see it here.
      </div>
    );
  }

  return (
    <div className="library-grid">
      {learned.map((p) => (
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
            <div className="library-card-name">{p.name}</div>
            {p.door_style && (
              <div className="library-card-style">{p.door_style}</div>
            )}
            <div className="library-card-count">
              {p.results.length} variation{p.results.length !== 1 ? 's' : ''}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
