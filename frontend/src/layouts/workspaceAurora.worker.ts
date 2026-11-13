import { createWorkspaceAuroraRenderer } from "./workspaceAuroraRenderer";

export type AuroraCommand =
  | { type: "init"; canvas: OffscreenCanvas }
  | { type: "resize"; width: number; height: number }
  | { type: "draw"; phase: number }
  | { type: "nudge"; x: number; y: number; strength: number };

let renderer: ReturnType<typeof createWorkspaceAuroraRenderer>;
self.onmessage = ({ data }: MessageEvent<AuroraCommand>) => {
  switch (data.type) {
    case "init": renderer = createWorkspaceAuroraRenderer(data.canvas); break;
    case "resize": renderer?.resize(data.width, data.height); break;
    case "nudge": renderer?.nudge(data.x, data.y, data.strength); break;
    case "draw": renderer?.draw(data.phase); self.postMessage("drawn"); break;
  }
};
