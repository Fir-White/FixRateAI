import { useEffect, useRef, useState, type DependencyList } from "react";
import { useApiQueryCache } from "./ApiQueryProvider";
import { QUERY_FRESH_MS } from "./apiQueryCache";

export type ApiQuery<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: string };

const loading = { status: "loading", data: null, error: null } as const;
const sameDependencies = (a: DependencyList, b: DependencyList) => a.length === b.length && a.every((value, index) => Object.is(value, b[index]));

export function useApiQuery<T>(
  loader: () => Promise<T>,
  dependencies: DependencyList,
  pollWhile?: (data: T) => boolean,
  cacheKey?: string,
): ApiQuery<T> {
  const cache = useApiQueryCache();
  const snapshot = (): ApiQuery<T> => {
    const entry = cacheKey ? cache?.peek<T>(cacheKey) : undefined;
    return entry ? { status: "success", data: entry.data, error: null } : loading;
  };
  const [state, setState] = useState(() => ({ cache, cacheKey, dependencies: [...dependencies], query: snapshot() }));
  const previous = useRef<{ cache: typeof cache; cacheKey: typeof cacheKey; dependencies: DependencyList } | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const force = previous.current?.cache === cache && previous.current.cacheKey === cacheKey && !sameDependencies(previous.current.dependencies, dependencies);
    previous.current = { cache, cacheKey, dependencies: [...dependencies] };
    const publish = (query: ApiQuery<T>) => {
      if (active) setState(previous => previous.cache === cache && previous.cacheKey === cacheKey && sameDependencies(previous.dependencies, dependencies)
        && previous.query.status === query.status && Object.is(previous.query.data, query.data) && previous.query.error === query.error
        ? previous : { cache, cacheKey, dependencies: [...dependencies], query });
    };
    publish(force ? loading : snapshot());
    const load = (fresh = false) => {
      const generation = cache?.generation;
      const result = cache && cacheKey ? cache.load(cacheKey, loader, fresh) : Promise.resolve().then(loader);
      void result.then(data => {
        if (!active) return;
        // A write overtook this read. Never publish its earlier snapshot.
        if (cache && cacheKey && cache.generation !== generation) { load(true); return; }
        publish({ status: "success", data, error: null });
        if (pollWhile?.(data)) timer = setTimeout(() => load(true), 3000);
      }).catch((error: unknown) => {
        publish({ status: "error", data: null, error: error instanceof Error ? error.message : "Не удалось загрузить данные" });
      });
    };
    load(force);
    const refresh = () => {
      if (!cache || !cacheKey || document.hidden) return;
      const entry = cache.peek(cacheKey);
      if (!entry || Date.now() - entry.updatedAt >= QUERY_FRESH_MS) load(true);
    };
    if (cache && cacheKey) {
      window.addEventListener("focus", refresh);
      document.addEventListener("visibilitychange", refresh);
    }
    return () => {
      active = false;
      clearTimeout(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [cache, cacheKey, ...dependencies]);

  // Changing a route/filter never exposes the previous key's data for a frame.
  return state.cache === cache && state.cacheKey === cacheKey && sameDependencies(state.dependencies, dependencies) ? state.query : snapshot();
}
