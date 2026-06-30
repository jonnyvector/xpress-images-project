// Upload area for a project's source image: a drag-and-drop / click-to-browse
// zone before an image exists, or a preview with a "Change image" button once
// one is uploaded. Purely presentational — upload state and handlers live in
// the parent UploadStep.
import { type ChangeEvent, type DragEvent, type RefObject } from 'react';
import type { Project } from '../types';

interface Props {
  project: Project;
  uploadLabel: string;
  dragOver: boolean;
  onDrop: (e: DragEvent) => void;
  onDragOver: (e: DragEvent) => void;
  onDragLeave: (e: DragEvent) => void;
  onFileUpload: (e: ChangeEvent<HTMLInputElement>) => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
}

export default function UploadDropzone({
  project,
  uploadLabel,
  dragOver,
  onDrop,
  onDragOver,
  onDragLeave,
  onFileUpload,
  fileInputRef,
}: Props) {
  if (!project.upload_filename) {
    return (
      <div
        className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          onChange={onFileUpload}
          hidden
        />
        <div className="drop-zone-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <p className="drop-zone-text">
          Drag & drop your {uploadLabel} image here
        </p>
        <p className="drop-zone-hint">
          or click to browse &middot; JPG, PNG, WEBP
        </p>
      </div>
    );
  }

  return (
    <div className="uploaded-preview">
      <img src={`/api/projects/${project.id}/upload`} alt={`Your ${uploadLabel}`} />
      <button
        className="change-image-btn"
        onClick={() => fileInputRef.current?.click()}
        type="button"
      >
        Change image
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".jpg,.jpeg,.png,.webp"
        onChange={onFileUpload}
        hidden
      />
    </div>
  );
}
