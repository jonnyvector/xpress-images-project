// Pending-review counter on the Review tab — polls the queue total so the
// operator can see at a glance that something needs their verdict.
import { useEffect, useState } from 'react';
import * as api from '../api';

export default function ReviewCountBadge() {
  const [count, setCount] = useState<number>(0);

  useEffect(() => {
    let alive = true;
    const poll = () => {
      // Skip while the browser tab is in the background.
      if (document.hidden) return;
      api
        .getReviewQueue()
        .then((q) => { if (alive) setCount(q.total_pending ?? 0); })
        .catch(() => {});
    };
    poll();
    document.addEventListener('visibilitychange', poll);
    const t = setInterval(poll, 7000);
    return () => { alive = false; clearInterval(t); document.removeEventListener('visibilitychange', poll); };
  }, []);

  if (!count) return null;
  return <span className="review-count">{count}</span>;
}
