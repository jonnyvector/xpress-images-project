// The operator's review queue: everything awaiting a verdict, in one place.
// Auto-polls, so new replicas and variants land here as soon as they exist —
// no tab hunting, no stale views. Each project shows its reference pair
// (sample + replica) beside the items needing a decision.
import { useCallback, useEffect, useState } from 'react';
import type { QueueProject, ReviewQueueData } from '../types';
import { useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import ApprovalControls from './ApprovalControls';
import VariantActions from './VariantActions';
import ApproveAllButton from './ApproveAllButton';
import { showError, onError } from '../notify';




export default function ReviewQueue() {
  const dispatch = useDispatch();
  const [queue, setQueue] = useState<ReviewQueueData | null>(null);
  // Sample uploads rarely change: bust once per mount. Generated images key
  // off image_id (new per attempt), so polling never re-downloads them.
  const [bust] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    try {
      setQueue(await api.getReviewQueue());
    } catch (err) {
      showError("Couldn't load review queue", err);
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
    // Keep the cached door list in sync too.
    api.listProjects().then((list) =>
      dispatch({ type: 'SET_PROJECTS', projects: list }),
    ).catch(onError("Couldn't refresh projects"));
  }, [refresh, dispatch]);

  if (!queue) return <div className="status-info">Loading review queue…</div>;
  if (queue.total_pending === 0) {
    return (
      <div className="status-success" style={{ marginTop: '1rem' }}>
        Review queue is empty — every new image has your verdict.
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <h3 style={{ margin: 0 }}>{p.project_name}</h3>
            <ApproveAllButton
              projectId={p.project_id}
              imageIds={p.variants.map((v) => v.image_id)}
              onDone={onChanged}
            />
          </div>
          <div className="review-row">
            {p.has_sample && (
              <figure className="review-card reference">
                <img src={`/api/projects/${p.project_id}/upload?v=${bust}`} alt="Sample" />
                <figcaption>Customer sample</figcaption>
              </figure>
            )}
            <figure className={`review-card ${p.replica.pending ? 'pending' : 'reference'}`}>
              <img
                src={`/api/projects/${p.project_id}/base-image?v=${p.replica.image_id ?? bust}`}
                alt="Replica"
              />
              <figcaption>
                Replica
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
                  src={`/api/projects/${p.project_id}/results/${v.index}/image?watermark=false&v=${v.image_id}`}
                  alt={v.wood_name}
                />
                <figcaption>
                  {v.wood_name}
                  {v.attempt > 0 && <span className="review-dim"> (attempt {v.attempt})</span>}{' '}
                  <VariantActions
                    projectId={p.project_id}
                    imageId={v.image_id}
                    kept={false}
                    onKept={onChanged}
                    onDeleted={onChanged}
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
