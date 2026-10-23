// Pipeline reliability at a glance: how often the pipeline's decisive
// verdicts agree with the operator's. This is the evidence for unlocking
// bulk generation — deferrals are shown separately so they can't inflate it.
import { useEffect, useState } from 'react';
import type { ReliabilityAggregates, ReliabilityRates } from '../types';
import * as api from '../api';
import { onError } from '../notify';



function pct(v: number | null): string {
  return v === null ? '—' : `${Math.round(v * 100)}%`;
}

function Row({ label, r }: { label: string; r: ReliabilityRates }) {
  return (
    <div className="reliability-row">
      <span className="reliability-label">{label}</span>
      <span title={`${r.decisive_n} decisive verdicts, ${r.disagreements} disagreements`}>
        agree {pct(r.agreement_rate)} ({r.decisive_n})
      </span>
      <span title={`${r.deferral_n} deferred to human`}>defer {pct(r.deferral_rate)}</span>
    </div>
  );
}

export default function ReliabilityPanel() {
  const [stats, setStats] = useState<ReliabilityAggregates | null>(null);

  useEffect(() => {
    let alive = true;
    api.getReliability()
      .then((st) => { if (alive) setStats(st); })
      .catch(onError("Couldn't load pipeline reliability"));
    return () => { alive = false; };
  }, []);

  if (!stats) return null;
  const hasData = stats.total.decisive_n + stats.total.deferral_n + stats.total.null_n > 0;

  return (
    <details className="reliability-panel">
      <summary>Pipeline reliability</summary>
      {!hasData ? (
        <div className="status-info" style={{ marginTop: '0.5rem' }}>
          No comparisons yet — approve or reject judged images to build evidence.
        </div>
      ) : (
        <div style={{ marginTop: '0.5rem' }}>
          <Row label="overall" r={stats.total} />
          {Object.entries(stats.by_kind).map(([k, r]) => (
            <Row key={k} label={k} r={r} />
          ))}
          {Object.entries(stats.by_style_class).map(([k, r]) => (
            <Row key={`s-${k}`} label={k.replace(/_/g, ' ')} r={r} />
          ))}
          <div className="reliability-note">
            Agreement counts only decisive pipeline verdicts (pass/regenerate).
            Unlock bulk in trust_config.json when these numbers convince you.
          </div>
        </div>
      )}
    </details>
  );
}
