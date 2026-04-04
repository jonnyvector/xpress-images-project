import { useState, useEffect, useCallback, useRef, memo } from 'react';
import type { Project, Style } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import SignatureHistory from './SignatureHistory';
import { usePollingTask } from '../hooks/usePollingTask';

interface Props {
  project: Project;
  apiKey: string;
}

export default memo(function UploadStep({ project, apiKey }: Props) {
  const dispatch = useDispatch();
  const [styles, setStyles] = useState<Style[]>([]);
  const [materialType, setMaterialType] = useState(project.material_type || 'wood');
  const [productType, setProductType] = useState(project.product_type || 'Cabinet Door');
  const [styleName, setStyleName] = useState(project.name);
  const [doorStyle, setDoorStyle] = useState(project.door_style ?? '');
  const [cornerStyle, setCornerStyle] = useState(project.corner_style ?? 'sharp');
  const [styleNotes, setStyleNotes] = useState(project.style_notes ?? '');
  const [geminiModel, setGeminiModel] = useState(project.gemini_model || 'gemini-3-pro-image-preview');
  const [learning, setLearning] = useState(project.learning_status === 'running');
  const [error, setError] = useState<string | null>(project.learning_error);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const projectIdRef = useRef(project.id);
  projectIdRef.current = project.id;

  useEffect(() => {
    api.listStyles(materialType).then(setStyles).catch(console.error);
  }, [materialType]);

  const category = productType === 'Drawer Front' ? 'drawer' : 'door';
  const filteredStyles = styles.filter((s) => s.category === category);
  const uploadLabel = productType === 'Drawer Front' ? 'drawer front' : 'door';

  // Set default door style when styles load, or when current style isn't valid for the current filter
  useEffect(() => {
    const isValid = filteredStyles.some((s) => s.key === doorStyle);
    if (!isValid && filteredStyles.length > 0) {
      setDoorStyle(filteredStyles[0].key);
    }
  }, [filteredStyles, doorStyle]);

  const handleMaterialTypeChange = useCallback(async (material: string) => {
    setMaterialType(material);
    setDoorStyle(''); // Reset door style when material changes
    try {
      const updated = await api.updateProject(project.id, {
        material_type: material,
        selected_swatches: [], // Clear wood/RTF swatches — they're different sets
      });
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
    } catch (err) {
      console.error('Failed to update material type:', err);
    }
  }, [dispatch, project.id]);

  const handleProductTypeChange = useCallback(async (type: string) => {
    setProductType(type);
    setDoorStyle(''); // Reset door style when product type changes
    try {
      const updated = await api.updateProject(project.id, { product_type: type });
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
    } catch (err) {
      console.error('Failed to update product type:', err);
    }
  }, [dispatch, project.id]);

  const uploadFile = useCallback(async (file: File) => {
    setError(null);
    try {
      const updated = await api.uploadDoorImage(project.id, file);
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      setStyleName(file.name.replace(/\.[^.]+$/, ''));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    }
  }, [dispatch, project.id]);

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
  }, [uploadFile]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && /\.(jpe?g|png|webp)$/i.test(file.name)) {
      uploadFile(file);
    }
  }, [uploadFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const { start, stop, retrying, resetErrors } = usePollingTask({
    enabled: false,
    onPoll: async () => {
      const updated = await api.getProject(projectIdRef.current);
      if (updated.learning_status !== 'running') {
        stop();
        setLearning(false);
        if (updated.learning_status === 'error') {
          setError(updated.learning_error || 'Learn failed');
        } else {
          setError(null);
        }
        dispatch({ type: 'UPDATE_PROJECT', project: updated });
        return false;
      }
      return true;
    },
    onErrorExhausted: () => {
      setLearning(false);
      setError('Lost connection to server. Click Learn to retry.');
    },
  });

  // Resume polling if learning is already running (e.g. after page refresh)
  useEffect(() => {
    if (project.learning_status === 'running') {
      setLearning(true);
      start();
    } else {
      stop();
    }
  }, [project.learning_status, start, stop]);

  const handleLearnStyle = useCallback(async () => {
    setLearning(true);
    setError(null);
    resetErrors();
    try {
      await api.updateProject(project.id, {
        name: styleName,
        material_type: materialType,
        door_style: doorStyle,
        corner_style: cornerStyle,
        style_notes: styleNotes,
        gemini_model: geminiModel,
      });
      await api.learnStyle(project.id);
      start();
    } catch (err) {
      setLearning(false);
      setError(err instanceof Error ? err.message : 'Learn failed');
    }
  }, [project.id, styleName, materialType, doorStyle, cornerStyle, styleNotes, geminiModel, resetErrors, start]);

  const canLearn = Boolean(apiKey && project.upload_filename);

  return (
    <section>
      <h3>1. Upload & Learn Style</h3>

      <div className="form-group">
        <label>Material</label>
        <div className="product-type-toggle">
          {([['wood', 'Wood'], ['rtf', 'RTF (Thermofoil)']] as const).map(([value, label]) => (
            <button
              key={value}
              className={`toggle-btn ${materialType === value ? 'active' : ''}`}
              onClick={() => handleMaterialTypeChange(value)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="product-type-toggle">
        {['Cabinet Door', 'Drawer Front'].map((type) => (
          <button
            key={type}
            className={`toggle-btn ${productType === type ? 'active' : ''}`}
            onClick={() => handleProductTypeChange(type)}
            type="button"
          >
            {type}
          </button>
        ))}
      </div>

      {!project.upload_filename ? (
        <div
          className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp"
            onChange={handleFileUpload}
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
      ) : (
        <>
          <div className="uploaded-preview">
            <img
              src={`/api/projects/${project.id}/upload`}
              alt={`Your ${uploadLabel}`}
            />
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
              onChange={handleFileUpload}
              hidden
            />
          </div>

          <div className="form-group">
            <label htmlFor={`style-name-${project.id}`}>Style name</label>
            <input
              id={`style-name-${project.id}`}
              type="text"
              value={styleName}
              onChange={(e) => setStyleName(e.target.value)}
              onBlur={async () => {
                const trimmed = styleName.trim();
                if (trimmed && trimmed !== project.name) {
                  const updated = await api.updateProject(project.id, { name: trimmed });
                  dispatch({ type: 'UPDATE_PROJECT', project: updated });
                }
              }}
            />
          </div>

          <div className="form-group">
            <label htmlFor={`style-type-${project.id}`}>Style type</label>
            <select
              id={`style-type-${project.id}`}
              value={doorStyle}
              onChange={(e) => setDoorStyle(e.target.value)}
            >
              {filteredStyles.map((s) => (
                <option key={s.key} value={s.key}>{s.name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor={`corner-style-${project.id}`}>Outer corners</label>
            <div className="product-type-toggle">
              {([['sharp', 'Sharp'], ['bullnose', 'Bullnose']] as const).map(([value, label]) => (
                <button
                  key={value}
                  className={`toggle-btn ${cornerStyle === value ? 'active' : ''}`}
                  onClick={() => {
                    setCornerStyle(value);
                    api.updateProject(project.id, { corner_style: value })
                      .then((updated) => dispatch({ type: 'UPDATE_PROJECT', project: updated }))
                      .catch(console.error);
                  }}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor={`style-notes-${project.id}`}>Style notes (optional)</label>
            <textarea
              id={`style-notes-${project.id}`}
              value={styleNotes}
              onChange={(e) => setStyleNotes(e.target.value)}
              rows={3}
              placeholder="Describe distinctive structural features..."
            />
          </div>

          <div className="form-group">
            <label htmlFor={`gemini-model-${project.id}`}>Gemini model</label>
            <select
              id={`gemini-model-${project.id}`}
              value={geminiModel}
              onChange={(e) => {
                setGeminiModel(e.target.value);
                api.updateProject(project.id, { gemini_model: e.target.value })
                  .then((updated) => dispatch({ type: 'UPDATE_PROJECT', project: updated }))
                  .catch(console.error);
              }}
            >
              <option value="gemini-3-pro-image-preview">Gemini 3.0 Pro Image</option>
              <option value="gemini-3.1-flash-image-preview">Gemini 3.1 Flash</option>
            </select>
          </div>

          <button
            className="primary"
            onClick={() => {
              if (project.has_signature) {
                if (!window.confirm(
                  'Re-learning will erase all previous variations. Are you sure?'
                )) return;
              }
              handleLearnStyle();
            }}
            disabled={!canLearn || learning}
            style={{ width: '100%' }}
          >
            {learning ? (
              <>
                <span className="spinner" /> Learning style...
              </>
            ) : project.has_signature ? (
              `Re-learn ${uploadLabel} Style`
            ) : (
              `Learn ${uploadLabel} Style`
            )}
          </button>
        </>
      )}

      {learning && retrying && (
        <div style={{ marginTop: '0.75rem', fontSize: '0.875rem', color: '#b59f3b' }}>
          Connection issue, retrying...
        </div>
      )}

      {project.has_signature && (
        <div className="status-success" style={{ marginTop: '0.75rem' }}>
          Style ready for variations
        </div>
      )}

      {project.has_signature && <SignatureHistory project={project} />}

      {error && (
        <div className="status-error" style={{ marginTop: '0.75rem' }}>
          {error}
          {error.includes('overloaded') || error.includes('503') || error.includes('high demand') ? (
            <button
              onClick={handleLearnStyle}
              disabled={learning}
              style={{ marginLeft: '0.5rem', fontSize: '0.8125rem', padding: '0.25rem 0.5rem' }}
            >
              Retry
            </button>
          ) : null}
        </div>
      )}
    </section>
  );
});
