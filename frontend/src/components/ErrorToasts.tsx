import { useEffect, useState } from 'react';
import { dismissToast, subscribe, type Toast } from '../notify';

export default function ErrorToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => subscribe(setToasts), []);

  // Keep the live region mounted even when empty: screen readers only announce
  // changes inside a region that already exists.
  return (
    <div className="toast-stack" role="alert" aria-live="assertive">
      {toasts.map((t) => (
        <div key={t.id} className="toast toast--error">
          <span className="toast-message">
            {t.message}
            {t.count > 1 && <span className="toast-count"> ×{t.count}</span>}
          </span>
          <button
            type="button"
            className="toast-dismiss"
            onClick={() => dismissToast(t.id)}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
