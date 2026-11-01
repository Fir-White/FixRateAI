import { useEffect, useRef, type RefObject } from "react";
import { createAuroraRenderer } from "./canvasRenderer";

const LIGHT_INTERVAL = 1 / 30;
const PARTICLE_INTERVAL = 1 / 60;

/** One lifecycle-managed clock; bounded SVG geometry updates and existing particles. */
export function useAuroraMotion(sceneRef: RefObject<HTMLDivElement | null>, animationEnabled: boolean, onReducedMotionChange?: (reduced: boolean) => void) {
  const enabled = useRef(animationEnabled);
  const synchronize = useRef<(() => void) | null>(null);
  const elapsed = useRef(0);
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || typeof window.matchMedia !== "function") return;
    const renderer = createAuroraRenderer(scene);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const desktop = window.matchMedia("(min-width: 821px)");
    const compactLandscape = window.matchMedia("(max-width: 1000px) and (max-height: 500px)");
    let intersecting = true;
    let frame: number | null = null;
    let previousTime: number | null = null;
    let lastLightUpdate = elapsed.current;
    let lastParticleUpdate = elapsed.current;
    let displayedParticleTime = elapsed.current;
    const running = () => !!renderer && !reduced.matches && desktop.matches && !compactLandscape.matches && enabled.current && !document.hidden && intersecting;
    const resize = (width: number, height: number) => {
      renderer?.resize(width, height, window.devicePixelRatio || 1);
      // Repaint the displayed phase rather than the newer clock value, so a
      // deferred resize cannot advance particles while paused or reduced.
      renderer?.render(displayedParticleTime, false);
    };
    const measure = () => { const bounds = scene.getBoundingClientRect(); resize(bounds.width, bounds.height); };
    const animate = (time: number) => {
      frame = null;
      if (!running()) { sync(); return; }
      const delta = previousTime === null ? 0 : Math.min(Math.max((time - previousTime) / 1000, 0), 0.064);
      previousTime = time;
      elapsed.current += delta;
      const lightUpdate = elapsed.current - lastLightUpdate >= LIGHT_INTERVAL - 1e-9;
      if (lightUpdate) lastLightUpdate += Math.floor((elapsed.current - lastLightUpdate + 1e-9) / LIGHT_INTERVAL) * LIGHT_INTERVAL;
      const particleUpdate = elapsed.current - lastParticleUpdate >= PARTICLE_INTERVAL - 1e-9;
      if (particleUpdate) lastParticleUpdate += Math.floor((elapsed.current - lastParticleUpdate + 1e-9) / PARTICLE_INTERVAL) * PARTICLE_INTERVAL;
      if (lightUpdate || particleUpdate) {
        renderer?.render(elapsed.current, lightUpdate);
        displayedParticleTime = elapsed.current;
      }
      frame = requestAnimationFrame(animate);
    };
    const sync = () => {
      onReducedMotionChange?.(reduced.matches);
      scene.dataset.motion = running() ? "running" : "paused";
      if (running()) {
        if (frame === null) { previousTime = null; frame = requestAnimationFrame(animate); }
      } else {
        if (frame !== null) cancelAnimationFrame(frame);
        frame = null;
        previousTime = null;
      }
    };
    synchronize.current = sync;
    const visibility = typeof IntersectionObserver === "function" ? new IntersectionObserver(([entry]) => {
      intersecting = entry.isIntersecting; sync();
    }) : null;
    const sizing = typeof ResizeObserver === "function" ? new ResizeObserver(([entry]) => resize(entry.contentRect.width, entry.contentRect.height)) : null;
    measure();
    sizing?.observe(scene);
    visibility?.observe(scene);
    window.addEventListener("resize", measure, { passive: true });
    document.addEventListener("visibilitychange", sync);
    for (const media of [reduced, desktop, compactLandscape]) media.addEventListener("change", sync);
    sync();
    return () => {
      synchronize.current = null;
      if (frame !== null) cancelAnimationFrame(frame);
      scene.dataset.motion = "paused";
      sizing?.disconnect(); visibility?.disconnect();
      window.removeEventListener("resize", measure);
      document.removeEventListener("visibilitychange", sync);
      for (const media of [reduced, desktop, compactLandscape]) media.removeEventListener("change", sync);
      renderer?.destroy();
    };
  }, [sceneRef, onReducedMotionChange]);
  useEffect(() => { enabled.current = animationEnabled; synchronize.current?.(); }, [animationEnabled]);
}
