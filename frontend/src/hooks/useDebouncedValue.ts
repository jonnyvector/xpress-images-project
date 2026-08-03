import { useEffect, useState } from 'react';

/**
 * Follow `value`, but only after it has stopped changing for `delayMs`.
 *
 * Used to keep continuous controls (range sliders) from driving expensive work
 * on every intermediate tick. A slider dragged across its range emits a value
 * per step; if each one re-requests a server-rendered image, the backend does
 * tens of seconds of image work for frames the user never sees.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return settled;
}
