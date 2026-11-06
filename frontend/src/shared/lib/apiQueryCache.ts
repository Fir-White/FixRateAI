export const QUERY_FRESH_MS = 10_000;
const QUERY_MAX_AGE_MS = 60_000;
const MAX_ENTRIES = 64;

interface Entry { data: unknown; updatedAt: number }

/** Session-owned read snapshots. No persistence, credentials or failed results. */
export class ApiQueryCache {
  private entries = new Map<string, Entry>();
  private pending = new Map<string, Promise<unknown>>();
  generation = 0;

  peek<T>(key: string): { data: T; updatedAt: number } | undefined {
    const entry = this.entries.get(key);
    if (!entry) return;
    if (Date.now() - entry.updatedAt >= QUERY_MAX_AGE_MS) {
      this.entries.delete(key);
      return;
    }
    this.entries.delete(key);
    this.entries.set(key, entry);
    return entry as { data: T; updatedAt: number };
  }

  load<T>(key: string, loader: () => Promise<T>, force = false): Promise<T> {
    const entry = this.peek<T>(key);
    if (!force && entry && Date.now() - entry.updatedAt < QUERY_FRESH_MS) return Promise.resolve(entry.data);
    const pending = this.pending.get(key);
    if (pending) return pending as Promise<T>;
    const generation = this.generation;
    const promise = Promise.resolve().then(loader).then(data => {
      if (this.generation === generation) {
        this.entries.delete(key);
        this.entries.set(key, { data, updatedAt: Date.now() });
        if (this.entries.size > MAX_ENTRIES) this.entries.delete(this.entries.keys().next().value!);
      }
      return data;
    }).catch(error => {
      if (this.generation === generation) this.entries.delete(key);
      throw error;
    }).finally(() => {
      if (this.pending.get(key) === promise) this.pending.delete(key);
    });
    this.pending.set(key, promise);
    return promise;
  }

  clear() {
    this.generation++;
    this.entries.clear();
    this.pending.clear();
  }
}

const invalidationListeners = new Set<() => void>();
export const QUERY_INVALIDATION_EVENT = "fixrate.data.changed.v1";

export function onApiQueryInvalidation(listener: () => void) {
  invalidationListeners.add(listener);
  return () => { invalidationListeners.delete(listener); };
}

/** Clear future reads without remounting an editor or discarding its draft. */
export function invalidateApiQueries() {
  invalidationListeners.forEach(listener => listener());
  try { window.localStorage.setItem(QUERY_INVALIDATION_EVENT, `${Date.now()}:${Math.random()}`); } catch { /* In-memory invalidation still applies. */ }
}
