import { useEffect, type RefObject } from "react";
import { FLOW_HEIGHT, FLOW_WIDTH, ribbonPath } from "./ribbonGeometry";

const MOTION_PROPERTIES = ["--aurora-x", "--aurora-y", "--aurora-breath", "--aurora-presence"];

/** One clock deforms three shared SVG paths, without React renders or frame-time layout reads. */
export function useAuroraMotion(sceneRef: RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || typeof window.matchMedia !== "function") return;
    const paths = [...scene.querySelectorAll<SVGPathElement>("[data-aurora-ribbon]")];

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const mouse = window.matchMedia("(hover: hover) and (pointer: fine)");
    const desktop = window.matchMedia("(min-width: 821px)");
    let bounds = scene.getBoundingClientRect();
    let frame: number | null = null;
    let previousTime: number | null = null;
    let elapsed = 0;
    let intersecting = true;
    let pointerX = 0;
    let pointerY = 0;
    let currentX = 0;
    let currentY = 0;
    let presence = 0;
    let pointerInside = false;
    let lastPointerTime = -Infinity;

    const enabled = () => !reduced.matches && mouse.matches && desktop.matches && !document.hidden && intersecting;
    const measure = () => { bounds = scene.getBoundingClientRect(); };
    const clearPointer = () => { pointerInside = false; pointerX = pointerY = 0; };
    const move = (event: PointerEvent) => {
      if (!enabled() || event.pointerType !== "mouse") return;
      const x = (event.clientX - bounds.left) / bounds.width;
      const y = (event.clientY - bounds.top) / bounds.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) { clearPointer(); return; }
      // Map through the SVG's xMidYMid slice, including its cropped margins.
      const scale = Math.max(bounds.width / FLOW_WIDTH, bounds.height / FLOW_HEIGHT);
      pointerInside = true;
      pointerX = (event.clientX - bounds.left - bounds.width / 2) / scale / (FLOW_WIDTH / 2);
      pointerY = (event.clientY - bounds.top - bounds.height / 2) / scale / (FLOW_HEIGHT / 2);
      lastPointerTime = performance.now();
    };
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) clearPointer(); };

    const animate = (time: number) => {
      frame = null;
      if (!enabled()) { sync(); return; }
      // Limit catch-up after stalls. Exponential smoothing behaves the same at 60/144 Hz.
      const delta = previousTime === null ? 0 : Math.min(Math.max((time - previousTime) / 1000, 0), 0.064);
      previousTime = time;
      elapsed += delta;
      const smoothing = 1 - Math.exp(-4.5 * delta);
      const attention = pointerInside ? Math.exp(-Math.max(0, time - lastPointerTime - 1100) / 3400) : 0;
      currentX += (pointerX * attention - currentX) * smoothing;
      currentY += (pointerY * attention - currentY) * smoothing;
      presence += (attention - presence) * (1 - Math.exp(-2.8 * delta));

      const pointer = { x: (currentX + 1) * FLOW_WIDTH / 2, y: (currentY + 1) * FLOW_HEIGHT / 2, strength: presence };
      paths.forEach((path, index) => path.setAttribute("d", ribbonPath(index, elapsed, pointer)));

      scene.style.setProperty("--aurora-x", currentX.toFixed(4));
      scene.style.setProperty("--aurora-y", currentY.toFixed(4));
      scene.style.setProperty("--aurora-breath", (0.5 + Math.sin(elapsed * 0.24) * 0.5).toFixed(4));
      scene.style.setProperty("--aurora-presence", presence.toFixed(4));
      frame = requestAnimationFrame(animate);
    };

    const sync = () => {
      if (enabled()) {
        if (frame === null) { previousTime = null; frame = requestAnimationFrame(animate); }
      } else {
        if (frame !== null) cancelAnimationFrame(frame);
        frame = null;
        previousTime = null;
        clearPointer();
        currentX = currentY = presence = 0;
        paths.forEach((path, index) => path.setAttribute("d", ribbonPath(index, 0)));
        for (const property of MOTION_PROPERTIES) scene.style.removeProperty(property);
      }
    };

    const resize = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    const visibility = typeof IntersectionObserver === "function" ? new IntersectionObserver(([entry]) => {
      intersecting = entry.isIntersecting;
      sync();
    }) : null;
    resize?.observe(scene);
    visibility?.observe(scene);
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("pointerout", leave, { passive: true });
    window.addEventListener("blur", clearPointer);
    window.addEventListener("resize", measure, { passive: true });
    document.addEventListener("visibilitychange", sync);
    for (const media of [reduced, mouse, desktop]) media.addEventListener("change", sync);
    sync();

    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      resize?.disconnect();
      visibility?.disconnect();
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerout", leave);
      window.removeEventListener("blur", clearPointer);
      window.removeEventListener("resize", measure);
      document.removeEventListener("visibilitychange", sync);
      for (const media of [reduced, mouse, desktop]) media.removeEventListener("change", sync);
    };
  }, [sceneRef]);
}
