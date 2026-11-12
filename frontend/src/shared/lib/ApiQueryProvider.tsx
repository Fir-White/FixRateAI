import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { ApiQueryCache, onApiQueryInvalidation, QUERY_INVALIDATION_EVENT } from "./apiQueryCache";

const Context = createContext<ApiQueryCache | null>(null);
export const useApiQueryCache = () => useContext(Context);

export function ApiQueryProvider({ scope, children, enabled = true }: { scope: string; children: ReactNode; enabled?: boolean }) {
  const cache = useMemo(() => new ApiQueryCache(), [scope]);
  useEffect(() => {
    if (!enabled) return;
    const unsubscribe = onApiQueryInvalidation(() => cache.clear());
    const storage = (event: StorageEvent) => { if (event.key === QUERY_INVALIDATION_EVENT) cache.clear(); };
    window.addEventListener("storage", storage);
    return () => { unsubscribe(); window.removeEventListener("storage", storage); };
  }, [cache, enabled]);
  return <Context.Provider value={enabled ? cache : null}>{children}</Context.Provider>;
}
