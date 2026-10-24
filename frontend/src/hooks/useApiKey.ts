// The Gemini API key lives in localStorage (api.ts reads it for every request).
// This hook lets any component read and update it and re-render on change.
import { useCallback, useSyncExternalStore } from 'react';
import { API_KEY_STORAGE_KEY, getApiKey } from '../api';

const EVENT = 'gemini-api-key-change';

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener('storage', onChange); // other browser tabs
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

export function useApiKey(): [string, (value: string) => void] {
  const apiKey = useSyncExternalStore(subscribe, getApiKey);
  const setApiKey = useCallback((value: string) => {
    try {
      localStorage.setItem(API_KEY_STORAGE_KEY, value);
    } catch {
      /* storage unavailable */
    }
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [apiKey, setApiKey];
}
