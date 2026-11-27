import { Suspense, useEffect, useState, type ComponentType } from "react";
import { LoadingState } from "@/shared/ui/States";

export type PageLoader = (() => Promise<{ default: ComponentType }>) & { peek: () => ComponentType | undefined };

/** A warm route renders synchronously, without suspending on an already loaded import. */
export function pageModule(load: () => Promise<{ default: ComponentType }>): PageLoader {
  let ready: ComponentType | undefined;
  let pending: Promise<{ default: ComponentType }> | undefined;
  const loader = () => pending ??= load().then(module => {
    ready = module.default;
    return module;
  }).catch(error => { pending = undefined; throw error; });
  loader.peek = () => ready;
  return loader;
}

export function lazyPage(load: PageLoader, label = "Загрузка страницы") {
  const fallback = <LoadingState label={label} />;
  return function RoutePage() {
    const [Ready, setReady] = useState(() => load.peek());
    const [failure, setFailure] = useState<{ error: unknown }>();
    useEffect(() => {
      if (Ready) return;
      let active = true;
      void load().then(
        module => { if (active) setReady(() => module.default); },
        error => { if (active) setFailure({ error }); },
      );
      return () => { active = false; };
    }, [Ready]);
    if (failure) throw failure.error;
    // Commit the loaded route directly; the initial Suspense fallback would
    // otherwise hold back even a module that has already arrived.
    return Ready ? <Suspense fallback={fallback}><Ready /></Suspense> : fallback;
  };
}
