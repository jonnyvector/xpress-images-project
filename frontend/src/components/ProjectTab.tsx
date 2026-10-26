// One door's workspace: a header and three steps in order (Style → Replica →
// Variants). The step lives in the URL (?step=) so refresh and back keep it;
// with no step given, the door opens on whatever needs doing next.
import { memo, useState } from 'react';
import { useSearchParams } from 'react-router';
import type { Project } from '../types';
import { displayName } from '../doorNames';
import { doorStage, materialLabel, productLabel, stageLabel } from '../doorStatus';
import UploadStep from './UploadStep';
import SwatchGrid from './SwatchGrid';
import GenerateStep from './GenerateStep';
import ResultsGrid from './ResultsGrid';
import ImageViewer from './ImageViewer';

const STEPS = ['style', 'replica', 'variants'] as const;
type Step = (typeof STEPS)[number];

function isStep(value: string | null): value is Step {
  return STEPS.includes(value as Step);
}

interface Props {
  project: Project;
  apiKey: string;
}

function nextStep(p: Project): Step {
  const stage = doorStage(p);
  if (stage === 'empty' || stage === 'not_learned') return 'style';
  if (stage === 'replica_pending') return 'replica';
  return 'variants';
}

export default memo(function ProjectTab({ project, apiKey }: Props) {
  const [params, setParams] = useSearchParams();
  const requested = params.get('step');
  const step: Step = isStep(requested) ? requested : nextStep(project);

  const tabs: { key: Step; label: string; done: boolean; note?: string }[] = [
    { key: 'style', label: 'Style', done: project.has_signature },
    { key: 'replica', label: 'Replica', done: project.replica_approved },
    {
      key: 'variants',
      label: 'Variants',
      done: false,
      note: project.results.length > 0 ? String(project.results.length) : undefined,
    },
  ];

  return (
    <div className="door">
      <header className="door-header">
        <div>
          <h1 title={project.name}>{displayName(project.name)}</h1>
          <div className="door-meta">
            {materialLabel(project)} · {productLabel(project)} · {stageLabel(project)}
          </div>
        </div>
        <nav className="door-steps" aria-label="Door steps">
          {tabs.map((t, i) => (
            <button
              key={t.key}
              type="button"
              className={`door-step${step === t.key ? ' door-step--active' : ''}`}
              aria-current={step === t.key ? 'step' : undefined}
              onClick={() => setParams({ step: t.key }, { replace: true })}
            >
              <span className={`door-step-num${t.done ? ' door-step-num--done' : ''}`}>
                {t.done ? '✓' : i + 1}
              </span>
              {t.label}
              {t.note && <span className="door-step-note">{t.note}</span>}
            </button>
          ))}
        </nav>
      </header>

      {/* All steps stay mounted (inactive ones hidden): learning and generation
          progress are polled inside them and must keep running across tabs. */}
      <div className="door-panel door-panel--narrow" hidden={step !== 'style'}>
        <UploadStep project={project} apiKey={apiKey} />
      </div>

      <div className="door-panel" hidden={step !== 'replica'}>
        <ResultsGrid project={project} part="replica" />
      </div>

      <div className="door-variants" hidden={step !== 'variants'}>
          <aside className="door-variants-side">
            {project.has_base_image && <ReplicaReference project={project} />}
            <GenerateStep project={project} apiKey={apiKey} />
            <SwatchGrid project={project} />
          </aside>
          <div className="door-panel">
            {project.results.length === 0 && (
              <div className="status-info">No variants yet. Pick swatches and generate.</div>
            )}
            <ResultsGrid project={project} part="variants" />
          </div>
      </div>
    </div>
  );
});

// The replica every variant is built from, kept in view while generating.
function ReplicaReference({ project }: { project: Project }) {
  const [open, setOpen] = useState(false);
  // learning_status changes when a re-learn finishes, so the image refreshes.
  const src = `/api/projects/${project.id}/base-image?v=${project.base_image_id ?? project.learning_status}`;
  return (
    <figure className="replica-ref">
      <img src={src} alt="Replica" className="zoomable" title="Click to zoom" onClick={() => setOpen(true)} />
      <figcaption>
        Replica {project.replica_approved ? '· approved' : '· not approved yet'}
      </figcaption>
      {open && (
        <ImageViewer
          images={[{ src, caption: 'Replica' }]}
          index={0}
          onClose={() => setOpen(false)}
        />
      )}
    </figure>
  );
}
