// The learned-style form fields: style name, style type, outer corners, style
// notes, and Gemini model. Controlled inputs only — all state and persistence
// (debounced saves, dispatch) live in the parent UploadStep, which passes
// values and change handlers down.
import type { Style } from '../types';

interface Props {
  projectId: string;
  styleName: string;
  onStyleNameChange: (value: string) => void;
  onStyleNameBlur: () => void;
  doorStyle: string;
  onDoorStyleChange: (value: string) => void;
  filteredStyles: Style[];
  cornerStyle: string;
  onCornerStyleChange: (value: string) => void;
  styleNotes: string;
  onStyleNotesChange: (value: string) => void;
  geminiModel: string;
  onGeminiModelChange: (value: string) => void;
}

export default function StyleForm({
  projectId,
  styleName,
  onStyleNameChange,
  onStyleNameBlur,
  doorStyle,
  onDoorStyleChange,
  filteredStyles,
  cornerStyle,
  onCornerStyleChange,
  styleNotes,
  onStyleNotesChange,
  geminiModel,
  onGeminiModelChange,
}: Props) {
  return (
    <>
      <div className="form-group">
        <label htmlFor={`style-name-${projectId}`}>Style name</label>
        <input
          id={`style-name-${projectId}`}
          type="text"
          value={styleName}
          onChange={(e) => onStyleNameChange(e.target.value)}
          onBlur={onStyleNameBlur}
        />
      </div>

      <div className="form-group">
        <label htmlFor={`style-type-${projectId}`}>Style type</label>
        <select
          id={`style-type-${projectId}`}
          value={doorStyle}
          onChange={(e) => onDoorStyleChange(e.target.value)}
        >
          {filteredStyles.map((s) => (
            <option key={s.key} value={s.key}>{s.name}</option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label htmlFor={`corner-style-${projectId}`}>Outer corners</label>
        <div className="product-type-toggle">
          {([['sharp', 'Sharp'], ['bullnose', 'Bullnose']] as const).map(([value, label]) => (
            <button
              key={value}
              className={`toggle-btn ${cornerStyle === value ? 'active' : ''}`}
              onClick={() => onCornerStyleChange(value)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="form-group">
        <label htmlFor={`style-notes-${projectId}`}>Style notes (optional)</label>
        <textarea
          id={`style-notes-${projectId}`}
          value={styleNotes}
          onChange={(e) => onStyleNotesChange(e.target.value)}
          rows={3}
          placeholder="Describe distinctive structural features..."
        />
      </div>

      <div className="form-group">
        <label htmlFor={`gemini-model-${projectId}`}>Gemini model</label>
        <select
          id={`gemini-model-${projectId}`}
          value={geminiModel}
          onChange={(e) => onGeminiModelChange(e.target.value)}
        >
          <option value="gemini-3-pro-image-preview">Gemini 3.0 Pro Image</option>
          <option value="gemini-3.1-flash-image-preview">Gemini 3.1 Flash</option>
        </select>
      </div>
    </>
  );
}
