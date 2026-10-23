import { useCallback, useEffect, useRef, useState } from 'react';
import { showError } from '../notify';

interface UsePollingTaskOptions {
  enabled: boolean;
  intervalMs?: number;
  maxErrors?: number;
  onPoll: () => Promise<boolean | void>;
  onErrorExhausted?: () => void;
}

export function usePollingTask({
  enabled,
  intervalMs = 2000,
  maxErrors = 5,
  onPoll,
  onErrorExhausted,
}: UsePollingTaskOptions) {
  const [retrying, setRetrying] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollFnRef = useRef(onPoll);
  const errorCountRef = useRef(0);

  pollFnRef.current = onPoll;
  const onExhaustedRef = useRef(onErrorExhausted);
  onExhaustedRef.current = onErrorExhausted;

  const stop = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const tick = useCallback(async () => {
    try {
      const keepRunning = await pollFnRef.current();
      errorCountRef.current = 0;
      setRetrying(false);
      if (keepRunning === false) {
        stop();
      }
    } catch {
      errorCountRef.current += 1;
      if (errorCountRef.current >= maxErrors) {
        stop();
        setRetrying(false);
        if (onExhaustedRef.current) onExhaustedRef.current();
        else showError('Lost contact with the server, so updates stopped. Reload the page to resume.');
      } else {
        setRetrying(true);
      }
    }
  }, [maxErrors, stop]);

  const start = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => {
      void tick();
    }, intervalMs);
  }, [intervalMs, tick]);

  const resetErrors = useCallback(() => {
    errorCountRef.current = 0;
    setRetrying(false);
  }, []);

  useEffect(() => {
    if (enabled) {
      start();
    } else {
      stop();
    }
    return () => stop();
  }, [enabled, start, stop]);

  return { start, stop, retrying, resetErrors };
}
