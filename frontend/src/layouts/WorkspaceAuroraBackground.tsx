import { useEffect, useRef, useState } from "react";
import { createWorkspaceAuroraSurface } from "./workspaceAuroraSurface";

export function WorkspaceAuroraBackground() {
  const hostRef = useRef<HTMLDivElement>(null);
  const [workerFailed, setWorkerFailed] = useState(false);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // Offscreen transfer is one-shot. Each effect lifetime owns its own canvas,
    // including React StrictMode's setup/cleanup/setup cycle in development.
    const canvas = document.createElement("canvas");
    host.appendChild(canvas);
    if (typeof window.CanvasRenderingContext2D === "undefined") return () => canvas.remove();
    const renderer = createWorkspaceAuroraSurface(canvas, !workerFailed, () => setWorkerFailed(true));
    if (!renderer) return () => canvas.remove();
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const compact = window.matchMedia?.("(max-width: 820px)");
    let frame: number | null = null;
    let previous: number | null = null;
    let phase = 0;
    let sinceDraw = 0;
    let sceneWidth = 1;
    let sceneHeight = 1;
    let lastClick = -1;
    let lastInput = -1;
    const root = canvas.closest(".workspace-root");
    const canReact = () => !document.hidden && !reduced?.matches;
    const click = (event: Event) => {
      const pointer = event as MouseEvent;
      if (!canReact() || pointer.button !== 0 || phase - lastClick < .12) return;
      lastClick = phase;
      let x = pointer.clientX;
      let y = pointer.clientY;
      if (!pointer.detail && event.target instanceof Element) {
        const bounds = event.target.getBoundingClientRect();
        x = bounds.left + bounds.width / 2;
        y = bounds.top + bounds.height / 2;
      }
      renderer.nudge(x / sceneWidth, y / sceneHeight, compact?.matches ? .65 : 1);
    };
    const input = (event: Event) => {
      if (!canReact() || phase - lastInput < .25 || (event as InputEvent).isComposing) return;
      const target = event.target;
      if (!(target instanceof HTMLElement) || !(target instanceof HTMLTextAreaElement || target.isContentEditable || (target instanceof HTMLInputElement && /^(text|email|password|search|tel|url|number)$/.test(target.type)))) return;
      lastInput = phase;
      // Read only the field's position, never its value or the entered text.
      const bounds = target.getBoundingClientRect();
      renderer.nudge((bounds.left + bounds.width / 2) / sceneWidth, (bounds.top + bounds.height / 2) / sceneHeight, .3);
    };

    const tick = (now: number) => {
      frame = null;
      const delta = previous === null ? 0 : Math.min(Math.max((now - previous) / 1000, 0), .064);
      previous = now;
      phase += delta;
      sinceDraw += delta;
      const interval = 1 / (compact?.matches ? 15 : 20);
      if (sinceDraw >= interval) {
        sinceDraw %= interval;
        renderer.draw(phase);
      }
      frame = requestAnimationFrame(tick);
    };
    const synchronize = () => {
      const running = !document.hidden && !reduced?.matches;
      canvas.dataset.state = running ? "running" : "paused";
      if (!running && frame !== null) { cancelAnimationFrame(frame); frame = null; previous = null; }
      if (running && frame === null) { previous = null; frame = requestAnimationFrame(tick); }
    };
    const resize = (width: number, height: number) => {
      sceneWidth = Math.max(1, width);
      sceneHeight = Math.max(1, height);
      renderer.resize(width, height);
      renderer.draw(phase);
    };
    const measure = () => { const bounds = canvas.getBoundingClientRect(); resize(bounds.width, bounds.height); };
    measure();
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(([entry]) => resize(entry.contentRect.width, entry.contentRect.height)) : null;
    observer?.observe(canvas);
    if (!observer) window.addEventListener("resize", measure, { passive: true });
    reduced?.addEventListener("change", synchronize);
    compact?.addEventListener("change", synchronize);
    document.addEventListener("visibilitychange", synchronize);
    root?.addEventListener("click", click, { capture: true, passive: true });
    root?.addEventListener("input", input, { passive: true });
    synchronize();
    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      reduced?.removeEventListener("change", synchronize);
      compact?.removeEventListener("change", synchronize);
      document.removeEventListener("visibilitychange", synchronize);
      root?.removeEventListener("click", click, true);
      root?.removeEventListener("input", input);
      renderer.destroy();
      canvas.remove();
    };
  }, [workerFailed]);

  return <div ref={hostRef} className="workspace-aurora" aria-hidden="true" />;
}
