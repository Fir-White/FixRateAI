import { createWorkspaceAuroraInteraction } from "./workspaceAuroraInteraction";

export function workspaceRasterSize(width: number, height: number) {
  const scale = Math.min(1, 960 / Math.max(1, width), 640 / Math.max(1, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

const SAMPLES = Array.from({ length: 49 }, (_, index) => {
  const t = index / 48;
  const u = 1 - t;
  return { start: u ** 3, first: 3 * u * u * t, second: 3 * u * t * t, end: t ** 3, opacity: .069 * Math.sin(Math.PI * t) };
});

export function createWorkspaceAuroraRenderer(canvas: HTMLCanvasElement) {
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) return null;
  const interaction = createWorkspaceAuroraInteraction();
  let previousPhase = 0;
  // Cache the continuous cross-section once. Closely overlapping samples form
  // two solid ribbons, without per-frame blur or low-alpha gradient strokes.
  const glow = document.createElement("canvas");
  glow.width = glow.height = 128;
  const glowContext = glow.getContext("2d");
  if (!glowContext) return null;
  const pixels = glowContext.createImageData(128, 128);
  for (let y = 0; y < 128; y++) {
    for (let x = 0; x < 128; x++) {
      const radiusSquared = ((x - 63.5) ** 2 + (y - 63.5) ** 2) / 63.5 ** 2;
      const offset = (y * 128 + x) * 4;
      pixels.data[offset] = 103;
      pixels.data[offset + 1] = 220;
      pixels.data[offset + 2] = 205;
      pixels.data[offset + 3] = Math.round(255 * Math.max(0, (Math.exp(-5 * radiusSquared) - Math.exp(-5)) / (1 - Math.exp(-5))));
    }
  }
  glowContext.putImageData(pixels, 0, 0);

  function resize(width: number, height: number) {
    interaction.resize(width, height);
    const size = workspaceRasterSize(width, height);
    if (canvas.width === size.width && canvas.height === size.height) return;
    canvas.width = size.width;
    canvas.height = size.height;
  }

  function draw(seconds: number) {
    for (let wave = 0; wave < 2; wave++) {
      const a = Math.sin(seconds * (wave ? .059 : .073) + (wave ? 2.1 : .4));
      const b = Math.sin(seconds * (wave ? .031 : .041) + (wave ? .8 : 1.6));
      const y0 = wave ? 990 : 900;
      const x1 = wave ? 280 + 65 * b : 170 + 75 * a;
      const y1 = wave ? 550 + 75 * a : 820 + 55 * b;
      const x2 = wave ? 830 + 70 * a : 440 + 95 * b;
      const y2 = wave ? 760 + 50 * b : 210 + 70 * a;
      const x3 = wave ? 1320 : 1080;
      const y3 = wave ? 290 : -120;
      SAMPLES.forEach((sample, index) => {
        const point = interaction.ribbons[wave][index];
        point.x = sample.start * -120 + sample.first * x1 + sample.second * x2 + sample.end * x3;
        point.y = sample.start * y0 + sample.first * y1 + sample.second * y2 + sample.end * y3;
      });
    }
    interaction.step(seconds - previousPhase);
    previousPhase = seconds;
    context!.setTransform(1, 0, 0, 1, 0, 0);
    context!.clearRect(0, 0, canvas.width, canvas.height);
    context!.setTransform(canvas.width / 1200, 0, 0, canvas.height / 900, 0, 0);
    for (const points of interaction.ribbons) {
      for (let index = 0; index < points.length; index++) {
        const point = points[index];
        const x = point.x + point.dx;
        const y = point.y + point.dy;
        context!.globalAlpha = SAMPLES[index].opacity;
        context!.drawImage(glow, x - 120, y - 120, 240, 240);
      }
    }
    context!.globalAlpha = 1;
  }

  return { resize, draw, nudge: interaction.nudge, destroy() { glow.width = glow.height = canvas.width = canvas.height = 1; } };
}
