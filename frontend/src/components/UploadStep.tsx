import { useState, useEffect, useCallback, useRef, memo } from 'react';
import type { Project, Style } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import SignatureHistory from './SignatureHistory';
import UploadDropzone from './UploadDropzone';
import StyleForm from './StyleForm';
import LearnControls from './LearnControls';
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
  const [learnInMaple, setLearnInMaple] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const projectIdRef = useRef(project.id);
  projectIdRef.current = project.id;

  // Re-sync mirrored form fields when the project changes underneath us
  // (e.g. a version restore changes door_style / material / notes). Each effect
  // keys on its own field so resyncing one never clobbers another mid-edit.
  useEffect(() => setMaterialType(project.material_type || 'wood'), [project.material_type]);
  useEffect(() => setProductType(project.product_type || 'Cabinet Door'), [project.product_type]);
  useEffect(() => setDoorStyle(project.door_style ?? ''), [project.door_style]);
  useEffect(() => setCornerStyle(project.corner_style ?? 'sharp'), [project.corner_style]);
  useEffect(() => setStyleNotes(project.style_notes ?? ''), [project.style_notes]);
  useEffect(
    () => setGeminiModel(project.gemini_model || 'gemini-3-pro-image-preview'),
    [project.gemini_model],
  );
  useEffect(() => setStyleName(project.name), [project.name]);

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
      await api.learnStyle(project.id, learnInMaple);
      start();
    } catch (err) {
      setLearning(false);
      setError(err instanceof Error ? err.message : 'Learn failed');
    }
  }, [project.id, styleName, materialType, doorStyle, cornerStyle, styleNotes, geminiModel, learnInMaple, resetErrors, start]);

  const canLearn = Boolean(apiKey && project.upload_filename);

  const handleStyleNameBlur = useCallback(async () => {
    const trimmed = styleName.trim();
    if (trimmed && trimmed !== project.name) {
      const updated = await api.updateProject(project.id, { name: trimmed });
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
    }
  }, [styleName, project.id, project.name, dispatch]);

  const handleCornerStyleChange = useCallback((value: string) => {
    setCornerStyle(value);
    api.updateProject(project.id, { corner_style: value })
      .then((updated) => dispatch({ type: 'UPDATE_PROJECT', project: updated }))
      .catch(console.error);
  }, [project.id, dispatch]);

  const handleGeminiModelChange = useCallback((value: string) => {
    setGeminiModel(value);
    api.updateProject(project.id, { gemini_model: value })
      .then((updated) => dispatch({ type: 'UPDATE_PROJECT', project: updated }))
      .catch(console.error);
  }, [project.id, dispatch]);

  const handleLearnClick = useCallback(() => {
    if (project.has_signature) {
      if (!window.confirm('Re-learning will erase all previous variations. Are you sure?')) {
        return;
      }
    }
    handleLearnStyle();
  }, [project.has_signature, handleLearnStyle]);

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

      <UploadDropzone
        project={project}
        uploadLabel={uploadLabel}
        dragOver={dragOver}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onFileUpload={handleFileUpload}
        fileInputRef={fileInputRef}
      />

      {project.upload_filename && (
        <>
          <StyleForm
            projectId={project.id}
            styleName={styleName}
            onStyleNameChange={setStyleName}
            onStyleNameBlur={handleStyleNameBlur}
            doorStyle={doorStyle}
            onDoorStyleChange={setDoorStyle}
            filteredStyles={filteredStyles}
            cornerStyle={cornerStyle}
            onCornerStyleChange={handleCornerStyleChange}
            styleNotes={styleNotes}
            onStyleNotesChange={setStyleNotes}
            geminiModel={geminiModel}
            onGeminiModelChange={handleGeminiModelChange}
          />
          <LearnControls
            materialType={materialType}
            learnInMaple={learnInMaple}
            onLearnInMapleChange={setLearnInMaple}
            learning={learning}
            canLearn={canLearn}
            hasSignature={project.has_signature}
            uploadLabel={uploadLabel}
            onLearn={handleLearnClick}
          />
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
