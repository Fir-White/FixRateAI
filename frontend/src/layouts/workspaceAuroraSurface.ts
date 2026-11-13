import { createWorkspaceAuroraRenderer } from "./workspaceAuroraRenderer";
import type { AuroraCommand } from "./workspaceAurora.worker";

/** Keep decorative rasterization off the UI thread where supported. */
export function createWorkspaceAuroraSurface(canvas: HTMLCanvasElement, allowWorker = true, onFailure?: () => void) {
  if (allowWorker && typeof Worker === "function" && typeof canvas.transferControlToOffscreen === "function") {
    let worker: Worker | undefined;
    let transferred = false;
    try {
      worker = new Worker(new URL("./workspaceAurora.worker.ts", import.meta.url), { type: "module" });
      const offscreen = canvas.transferControlToOffscreen();
      transferred = true;
      const send = (message: AuroraCommand, transfer: Transferable[] = []) => worker!.postMessage(message, transfer);
      send({ type: "init", canvas: offscreen }, [offscreen]);
      let drawing = false;
      let pendingPhase: number | null = null;
      const draw = (phase: number) => {
        if (drawing) { pendingPhase = phase; return; }
        drawing = true;
        send({ type: "draw", phase });
      };
      worker.onmessage = () => {
        drawing = false;
        if (pendingPhase !== null) { const next = pendingPhase; pendingPhase = null; draw(next); }
      };
      worker.onerror = () => { worker!.terminate(); onFailure?.(); };
      canvas.dataset.renderer = "worker";
      return {
        resize: (width: number, height: number) => send({ type: "resize", width, height }),
        // At most one pending frame; resize/reduced-motion redraws must not be lost.
        draw,
        nudge: (x: number, y: number, strength: number) => send({ type: "nudge", x, y, strength }),
        destroy: () => { worker!.onerror = null; worker!.onmessage = null; worker!.terminate(); },
      };
    } catch {
      worker?.terminate();
      if (transferred) { onFailure?.(); return null; }
    }
  }
  canvas.dataset.renderer = "main";
  return createWorkspaceAuroraRenderer(canvas);
}
