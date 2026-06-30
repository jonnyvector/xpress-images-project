// The learn trigger: the optional "Learn in Maple Select" toggle (wood only)
// and the primary Learn / Re-learn button. Presentational — the learn action
// (including the re-learn confirm) and learning state live in the parent
// UploadStep and are passed in via onLearn.
interface Props {
  materialType: string;
  learnInMaple: boolean;
  onLearnInMapleChange: (value: boolean) => void;
  learning: boolean;
  canLearn: boolean;
  hasSignature: boolean;
  uploadLabel: string;
  onLearn: () => void;
}

export default function LearnControls({
  materialType,
  learnInMaple,
  onLearnInMapleChange,
  learning,
  canLearn,
  hasSignature,
  uploadLabel,
  onLearn,
}: Props) {
  return (
    <>
      {materialType === 'wood' && (
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.8125rem',
            color: '#aaa',
            cursor: 'pointer',
            marginBottom: '0.5rem',
          }}
        >
          <input
            type="checkbox"
            checked={learnInMaple}
            onChange={(e) => onLearnInMapleChange(e.target.checked)}
            disabled={learning}
          />
          Learn in Maple Select
          <span
            title="Forces Gemini to generate a new image in maple select instead of replicating the original material. Can produce a stronger thought signature."
            style={{ cursor: 'help', opacity: 0.6 }}
          >
            (?)
          </span>
        </label>
      )}

      <button
        className="primary"
        onClick={onLearn}
        disabled={!canLearn || learning}
        style={{ width: '100%' }}
      >
        {learning ? (
          <>
            <span className="spinner" /> Learning style...
          </>
        ) : hasSignature ? (
          `Re-learn ${uploadLabel} Style`
        ) : (
          `Learn ${uploadLabel} Style`
        )}
      </button>
    </>
  );
}
