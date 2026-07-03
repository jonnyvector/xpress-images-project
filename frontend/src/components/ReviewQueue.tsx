// The operator's review queue: everything awaiting a verdict, in one place.
// Auto-polls, so replicas and variants land here the moment they're judged —
// no tab hunting, no stale views. Each project shows its reference pair
// (sample + replica) beside the items needing a decision.
import { useCallback, useEffect, useState } from 'react';
import type { QaVerdict } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import ApprovalControls from './ApprovalControls';
import QaBadge from './QaBadge';

interface QueueVariant {
  image_id: string;
  index: number;
  wood_name: string;
  attempt: number;
  verdict: QaVerdict;
}

interface QueueProject {
  project_id: string;
  project_name: string;
  has_sample: boolean;
  replica: { image_id: string | null; pending: boolean; verdict: QaVerdict | null };
  variants: QueueVariant[];
  pending_count: number;
}

interface Queue {
  projects: QueueProject[];
  total_pending: number;
}

export default function ReviewQueue() {
  const dispatch = useDispatch();
  const [queue, setQueue] = useState<Queue | null>(null);
  const [bust, setBust] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/qa/review-queue');
      setQueue(await res.json());
      setBust(Date.now());
    } catch (err) {
      console.error('review queue fetch failed:', err);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  // ApprovalControls needs a Project-shaped object; the queue only uses id.
  const projectStub = (p: QueueProject) =>
    ({ id: p.project_id } as Parameters<typeof ApprovalControls>[0]['project']);

  const onChanged = useCallback(() => {
    refresh();
    // Keep any open project tabs in sync too.
    api.listProjects().then((list) =>
      dispatch({ type: 'SET_PROJECTS', projects: list }),
    ).catch(console.error);
  }, [refresh, dispatch]);

  if (!queue) return <div className="status-info">Loading review queue…</div>;
  if (queue.total_pending === 0) {
    return (
      <div className="status-success" style={{ marginTop: '1rem' }}>
        Review queue is empty — everything the pipeline produced has your verdict.
      </div>
    );
  }

  return (
    <div className="review-queue">
      <h2>
        Awaiting your verdict: {queue.total_pending} item
        {queue.total_pending === 1 ? '' : 's'} across {queue.projects.length} project
        {queue.projects.length === 1 ? '' : 's'}
      </h2>
      {queue.projects.map((p) => (
        <section key={p.project_id} className="review-project">
          <h3>{p.project_name}</h3>
          <div className="review-row">
            {p.has_sample && (
              <figure className="review-card reference">
                <img src={`/api/projects/${p.project_id}/upload?v=${bust}`} alt="Sample" />
                <figcaption>Customer sample</figcaption>
              </figure>
            )}
            <figure className={`review-card ${p.replica.pending ? 'pending' : 'reference'}`}>
              <img
                src={`/api/projects/${p.project_id}/base-image?v=${bust}`}
                alt="Replica"
              />
              <figcaption>
                Replica <QaBadge verdict={p.replica.verdict ?? undefined} />
                {p.replica.pending && p.replica.image_id ? (
                  <ApprovalControls
                    project={projectStub(p)}
                    imageId={p.replica.image_id}
                    verdict={null}
                    onChanged={onChanged}
                    compact
                  />
                ) : (
                  <div className="review-ok">✓ approved anchor</div>
                )}
              </figcaption>
            </figure>
            {p.variants.map((v) => (
              <figure key={v.image_id} className="review-card pending">
                <img
                  src={`/api/projects/${p.project_id}/results/${v.index}/image?watermark=false&v=${bust}`}
                  alt={v.wood_name}
                />
                <figcaption>
                  {v.wood_name}
                  {v.attempt > 0 && <span className="review-dim"> (attempt {v.attempt})</span>}{' '}
                  <QaBadge verdict={v.verdict} />
                  <ApprovalControls
                    project={projectStub(p)}
                    imageId={v.image_id}
                    verdict={null}
                    onChanged={onChanged}
                    compact
                  />
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
