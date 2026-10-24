// One door in the library. Click to open; double-click the name to rename.
// No delete button, on purpose: style signatures cannot be recreated.
import { useRef, useState } from 'react';
import type { Project } from '../types';
import { displayName } from '../doorNames';
import { doorStage, doorThumb, materialLabel, productLabel, stageLabel } from '../doorStatus';

interface Props {
  project: Project;
  productTitle?: string; // set for a product's main (canonical) door
  onOpen: (id: string) => void;
  onRename: (id: string, name: string) => Promise<boolean>;
}

const STAGE_CLASS = {
  empty: 'badge-muted',
  not_learned: 'badge-warn',
  replica_pending: 'badge-partial',
  ready: 'badge-product',
  variants: 'badge-approved',
} as const;

export default function LibraryCard({ project, productTitle, onOpen, onRename }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(project.name);
  const thumb = doorThumb(project);
  // Escape unmounts the input, which fires blur; this stops that blur saving.
  const cancelled = useRef(false);

  const submit = async () => {
    if (cancelled.current) return;
    const name = draft.trim();
    if (name && name !== project.name && !(await onRename(project.id, name))) return;
    setEditing(false);
  };

  return (
    <div
      className="library-card"
      role="link"
      tabIndex={0}
      onClick={() => !editing && onOpen(project.id)}
      onKeyDown={(e) => {
        if (!editing && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onOpen(project.id);
        }
      }}
    >
      <div className="library-card-thumb">
        {thumb ? <img src={thumb} alt="" loading="lazy" /> : <span>No image</span>}
      </div>
      <div className="library-card-info">
        {productTitle && <div className="library-card-product">{productTitle}</div>}
        {editing ? (
          <input
            className="library-card-name-input"
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onBlur={submit}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') e.currentTarget.blur(); // blur submits, exactly once
              if (e.key === 'Escape') {
                cancelled.current = true;
                setDraft(project.name);
                setEditing(false);
              }
            }}
          />
        ) : (
          <div
            className={productTitle ? 'library-card-sub' : 'library-card-name'}
            title={`${project.name} (double-click to rename)`}
            onDoubleClick={(e) => {
              e.stopPropagation();
              cancelled.current = false;
              setDraft(project.name);
              setEditing(true);
            }}
          >
            {displayName(project.name)}
          </div>
        )}
        <div className="library-card-meta">
          <span className={`badge ${STAGE_CLASS[doorStage(project)]}`}>{stageLabel(project)}</span>
          <span className="library-card-kind">
            {materialLabel(project)} · {productLabel(project)}
          </span>
        </div>
      </div>
    </div>
  );
}
