import { useLayoutEffect, type RefObject } from "react";
import { animateMotion } from "./animate";

/** Animate existing content after navigation without remounting it or its shell. */
export function usePageEntry(content: RefObject<HTMLElement | null>, locationKey: string, authEntry = false) {
  useLayoutEffect(() => {
    if (!content.current) return;
    if (authEntry) {
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      content.current.focus({ preventScroll: true });
    }
    if (!authEntry) return;
    const run = animateMotion(content.current, [{ opacity: 0 }, { opacity: 1 }], "--motion-app-enter");
    void run.finished.then(completed => { if (completed) run.cancel(); });
    return () => run.cancel();
  }, [content, locationKey, authEntry]);
}
