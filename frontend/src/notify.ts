// App-wide error reporting. Anything that fails calls showError(); the
// <ErrorToasts> component (mounted once in Layout) shows it on screen until
// dismissed.

export interface Toast {
  id: number;
  message: string;
  count: number;
}

// A toast clears itself this long after its last repeat, so a poller error
// stays visible while it keeps failing and goes away once it recovers.
const EXPIRE_MS = 20_000;
const timers = new Map<number, ReturnType<typeof setTimeout>>();

function scheduleExpiry(id: number) {
  clearTimeout(timers.get(id));
  timers.set(id, setTimeout(() => dismissToast(id), EXPIRE_MS));
}

type Listener = (toasts: Toast[]) => void;

let toasts: Toast[] = [];
let nextId = 1;
const MAX_TOASTS = 5;
const listeners = new Set<Listener>();

function emit() {
  for (const l of listeners) l(toasts);
}

function describe(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return 'Unknown error';
}

/** Log and show an error. `what` says what failed, e.g. "Couldn't save style". */
export function showError(what: string, err?: unknown): void {
  console.error(what, err);
  const message = err === undefined ? what : `${what}: ${describe(err)}`;
  // Pollers can fail every few seconds; fold repeats into one toast.
  const existing = toasts.find((t) => t.message === message);
  const id = existing?.id ?? nextId++;
  toasts = existing
    ? toasts.map((t) => (t === existing ? { ...t, count: t.count + 1 } : t))
    : [...toasts, { id, message, count: 1 }].slice(-MAX_TOASTS);
  scheduleExpiry(id);
  emit();
}

/** Curried form for promise chains: `.catch(onError("Couldn't load swatches"))`. */
export function onError(what: string) {
  return (err: unknown) => showError(what, err);
}

export function dismissToast(id: number): void {
  clearTimeout(timers.get(id));
  timers.delete(id);
  if (!toasts.some((t) => t.id === id)) return;
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  listener(toasts);
  return () => {
    listeners.delete(listener);
  };
}
