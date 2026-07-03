// Pending-review counter on the Review tab — polls the queue total so the
// operator can see at a glance that something needs their verdict.
import { useEffect, useState } from 'react';

export default function ReviewCountBadge() {
  const [count, setCount] = useState<number>(0);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      fetch('/api/qa/review-queue')
        .then((r) => r.json())
        .then((q) => { if (alive) setCount(q.total_pending ?? 0); })
        .catch(() => {});
    poll();
    const t = setInterval(poll, 7000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!count) return null;
  return <span className="review-count">{count}</span>;
}
