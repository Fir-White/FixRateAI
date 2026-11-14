import { lazy, Suspense, useState, type ComponentType } from "react";
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

export function lazyPage(load: PageLoader) {
  const Page = lazy(load);
  return function RoutePage() {
    // Freeze the selected type for this mount: finishing a preload must never
    // remount an active editor and erase its draft.
    const [Ready] = useState(() => load.peek() ?? Page);
    return <Suspense fallback={<LoadingState label="Загрузка страницы" />}><Ready /></Suspense>;
  };
}
