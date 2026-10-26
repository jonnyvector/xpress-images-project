// Keep / Delete for one generated variant. Keep records an approval (the
// image is good); Delete moves it to the project trash on the server.
import { useState } from 'react';
import * as api from '../api';
import { showError } from '../notify';

interface Props {
  projectId: string;
  imageId: string;
  kept: boolean;
  onKept: () => void;
  onDeleted: () => void;
}

export default function VariantActions({ projectId, imageId, kept, onKept, onDeleted }: Props) {
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<unknown>, done: () => void, what: string) => {
    setBusy(true);
    try {
      await action();
      done();
    } catch (err) {
      showError(`Couldn't ${what}`, err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="variant-actions">
      {kept ? (
        <span className="approval-badge approved">✓ Kept</span>
      ) : (
        <button
          type="button"
          className="approve-btn"
          disabled={busy}
          onClick={() => run(() => api.setApproval(projectId, imageId, 'approved'), onKept, 'keep the image')}
        >
          Keep
        </button>
      )}
      <button
        type="button"
        className="danger"
        disabled={busy}
        title="Moves the image to the project trash"
        onClick={() => run(() => api.deleteImage(projectId, imageId), onDeleted, 'delete the image')}
      >
        Delete
      </button>
    </div>
  );
}
