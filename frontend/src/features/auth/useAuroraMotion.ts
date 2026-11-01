import { useEffect, useRef, type RefObject } from "react";

/** Pause CSS timelines without replacing animations or resetting their current time. */
export function useAuroraMotion(sceneRef: RefObject<HTMLDivElement | null>, animationEnabled: boolean, onReducedMotionChange?: (reduced: boolean) => void) {
  const enabled = useRef(animationEnabled);
  const synchronize = useRef<(() => void) | null>(null);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || typeof window.matchMedia !== "function") return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const mouse = window.matchMedia("(hover: hover) and (pointer: fine)");
    const desktop = window.matchMedia("(min-width: 821px)");
    let intersecting = true;
    const sync = () => {
      const eligible = !reduced.matches && mouse.matches && desktop.matches;
      onReducedMotionChange?.(reduced.matches);
      scene.dataset.motion = eligible && enabled.current && !document.hidden && intersecting ? "running" : "paused";
    };
    synchronize.current = sync;
    const observer = typeof IntersectionObserver === "function" ? new IntersectionObserver(([entry]) => {
      intersecting = entry.isIntersecting;
      sync();
    }) : null;
    observer?.observe(scene);
    document.addEventListener("visibilitychange", sync);
    for (const media of [reduced, mouse, desktop]) media.addEventListener("change", sync);
    sync();
    return () => {
      synchronize.current = null;
      scene.dataset.motion = "paused";
      observer?.disconnect();
      document.removeEventListener("visibilitychange", sync);
      for (const media of [reduced, mouse, desktop]) media.removeEventListener("change", sync);
    };
  }, [sceneRef, onReducedMotionChange]);

  useEffect(() => {
    enabled.current = animationEnabled;
    synchronize.current?.();
  }, [animationEnabled]);
}
