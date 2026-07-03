// Pipeline verdict badge for one image. Hover shows the judge's reasoning
// and rubric scores — the pipeline's opinion sits beside the operator's.
import type { QaVerdict } from '../types';

const LABELS: Record<string, { text: string; cls: string }> = {
  pass: { text: 'QA: pass', cls: 'qa-pass' },
  regenerate: { text: 'QA: regenerate', cls: 'qa-regenerate' },
  needs_human: { text: 'QA: needs human', cls: 'qa-needs-human' },
  error: { text: 'QA: error', cls: 'qa-error' },
};

export default function QaBadge({ verdict }: { verdict: QaVerdict | undefined }) {
  if (!verdict) return null;
  if (verdict.qa_status !== 'done') {
    return <span className="qa-badge qa-judging">QA: judging…</span>;
  }
  const label = LABELS[verdict.verdict ?? ''] ?? null;
  if (!label) return null;
  const scores = verdict.scores
    ? Object.entries(verdict.scores)
        .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
        .join('\n')
    : '';
  const title = [
    verdict.reason ?? '',
    scores,
    verdict.geometry ? `geometry: ${verdict.geometry}` : '',
  ]
    .filter(Boolean)
    .join('\n\n');
  return (
    <span className={`qa-badge ${label.cls}`} title={title}>
      {label.text}
    </span>
  );
}
