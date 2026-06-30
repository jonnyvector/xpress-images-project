// Shared project card for the door library. Renders the thumbnail, the
// inline-rename header row, and a delete button; the variant-specific body
// (badges/counts) is passed as children by each grid (learned vs imported).
import type { ReactNode } from 'react';
import type { Project } from '../types';

interface Props {
  project: Project;
  thumbUrl: string | null;
  isEditing: boolean;
  editName: string;
  onEditNameChange: (value: string) => void;
  onRenameSubmit: () => void;
  onCancelEdit: () => void;
  onStartEdit: () => void;
  isDeleting: boolean;
  onDelete: () => void;
  onSelect: (id: string) => void;
  children?: ReactNode;
}

export default function LibraryCard({
  project,
  thumbUrl,
  isEditing,
  editName,
  onEditNameChange,
  onRenameSubmit,
  onCancelEdit,
  onStartEdit,
  isDeleting,
  onDelete,
  onSelect,
  children,
}: Props) {
  return (
    <div
      className="library-card"
      role="button"
      tabIndex={0}
      onClick={() => onSelect(project.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(project.id);
        }
      }}
    >
      {thumbUrl && (
        <img src={thumbUrl} alt={project.name} className="library-card-thumb" />
      )}
      <div className="library-card-info">
        <div className="library-card-header-row">
          {isEditing ? (
            <input
              className="library-card-name-input"
              value={editName}
              onChange={(e) => onEditNameChange(e.target.value)}
              onBlur={onRenameSubmit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onRenameSubmit();
                if (e.key === 'Escape') onCancelEdit();
              }}
              onClick={(e) => e.stopPropagation()}
              autoFocus
            />
          ) : (
            <div
              className="library-card-name"
              onDoubleClick={(e) => {
                e.stopPropagation();
                onStartEdit();
              }}
              title="Double-click to rename"
            >
              {project.name}
            </div>
          )}
          <button
            type="button"
            className="library-delete-btn"
            disabled={isDeleting}
            onClick={(e) => {
              e.stopPropagation();
              void onDelete();
            }}
          >
            {isDeleting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
