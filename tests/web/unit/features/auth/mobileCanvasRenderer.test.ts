import { afterEach, expect, it, vi } from "vitest";
import { createAuroraRenderer, sceneMapping } from "@/features/auth/canvasRenderer";
import { createMobileCanvasRenderer, mobileRasterSize } from "@/features/auth/mobileCanvasRenderer";
import { ribbonFrame } from "@/features/auth/ribbonGeometry";

function recordingContext() {
  const strokes: { width: number; opacity: number }[] = [];
  const context = {
    lineWidth: 1, globalAlpha: 1, lineCap: "", lineJoin: "", strokeStyle: "",
    setTransform: vi.fn(), clearRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), bezierCurveTo: vi.fn(),
    createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    stroke: vi.fn(() => strokes.push({ width: context.lineWidth, opacity: context.globalAlpha })),
  };
  const filter = vi.fn(), shadow = vi.fn();
  Object.defineProperty(context, "filter", { set: filter });
  Object.defineProperty(context, "shadowBlur", { set: shadow });
  return { context, strokes, filter, shadow };
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("bounds the mobile raster independently of a high device pixel ratio", () => {
  for (const [width, height] of [[360,800],[390,844],[412,915],[430,932],[820,1366],[1000,500]]) {
    const size = mobileRasterSize(width,height,3);
    expect(size.width).toBeLessThanOrEqual(960);expect(size.height).toBeLessThanOrEqual(1280);
    expect(size.width).toBeLessThanOrEqual(Math.round(width*1.25));expect(size.height).toBeLessThanOrEqual(Math.round(height*1.25));
  }
});

it("shares each exact Bezier across its soft layers and caches gradients and ambient outside frame work", () => {
  const main=recordingContext(),ambient=recordingContext(),canvas=document.createElement("canvas"),scene=document.createElement("div");
  vi.spyOn(HTMLCanvasElement.prototype,"getContext").mockReturnValue(ambient.context as unknown as CanvasRenderingContext2D);
  const styles=vi.spyOn(window,"getComputedStyle"),bounds=vi.spyOn(scene,"getBoundingClientRect");
  const renderer=createMobileCanvasRenderer(scene,canvas,main.context as unknown as CanvasRenderingContext2D)!;
  renderer.resize(390,844,3,sceneMapping(390,844));
  const gradientCount=main.context.createLinearGradient.mock.calls.length,styleCount=styles.mock.calls.length,ambientCount=ambient.context.stroke.mock.calls.length;
  const waves=[ribbonFrame(0,7,"mobile"),ribbonFrame(1,7,"mobile")];
  renderer.render(waves);
  expect(main.context.beginPath).toHaveBeenCalledTimes(2);expect(main.context.bezierCurveTo).toHaveBeenCalledTimes(4);
  expect(main.context.moveTo).toHaveBeenNthCalledWith(1,...waves[1].cubics[0][0]);
  expect(main.context.moveTo).toHaveBeenNthCalledWith(2,...waves[0].cubics[0][0]);
  expect(main.context.stroke.mock.calls.length).toBeLessThanOrEqual(64);
  // Optical bounds detect malformed Gaussian tails or source-over accumulation.
  const opacity=(strokes:typeof main.strokes)=>1-strokes.reduce((alpha,stroke)=>alpha*(1-stroke.opacity),1);
  expect(opacity(main.strokes.slice(0,32))).toBeGreaterThan(.4);expect(opacity(main.strokes.slice(0,32))).toBeLessThan(.6);
  expect(opacity(main.strokes.slice(32))).toBeGreaterThan(.7);expect(opacity(main.strokes.slice(32))).toBeLessThan(.85);
  expect(main.strokes.every(stroke=>stroke.width>0&&stroke.opacity>0&&stroke.opacity<1)).toBe(true);
  renderer.render([ribbonFrame(0,8,"mobile"),ribbonFrame(1,8,"mobile")]);
  expect(main.context.createLinearGradient).toHaveBeenCalledTimes(gradientCount);expect(styles).toHaveBeenCalledTimes(styleCount);
  expect(ambient.context.stroke).toHaveBeenCalledTimes(ambientCount);expect(bounds).not.toHaveBeenCalled();
  expect(main.filter).not.toHaveBeenCalled();expect(main.shadow).not.toHaveBeenCalled();
  expect(main.context.drawImage).toHaveBeenCalledTimes(2);
  renderer.destroy();
  expect([canvas.width,canvas.height]).toEqual([1,1]);
});

it("uses no hidden SVG path writes on mobile and restores the SVG and tiny canvas on desktop", () => {
  vi.stubGlobal("innerWidth",390);vi.stubGlobal("innerHeight",844);
  const record=recordingContext();vi.spyOn(HTMLCanvasElement.prototype,"getContext").mockReturnValue(record.context as unknown as CanvasRenderingContext2D);
  const scene=document.createElement("div");
  scene.innerHTML='<svg><path data-aurora-ribbon="0"></path><path data-aurora-ribbon="1"></path><path data-aurora-ribbon="2"></path></svg><canvas data-aurora-particles></canvas>';
  const path=scene.querySelector("path")!,attribute=vi.spyOn(path,"setAttribute"),canvas=scene.querySelector("canvas")!;
  const renderer=createAuroraRenderer(scene)!;renderer.resize(390,844,3);renderer.render(1,true,"mobile");renderer.render(2,true,"mobile");
  expect(scene.dataset.renderer).toBe("canvas");expect(attribute).not.toHaveBeenCalled();
  expect(canvas.width).toBeGreaterThan(1);expect(canvas.width).toBeLessThanOrEqual(488);
  vi.stubGlobal("innerWidth",1024);vi.stubGlobal("innerHeight",768);
  renderer.resize(604,768,1);renderer.render(2,true);
  expect(scene.dataset.renderer).toBe("svg");expect(attribute).toHaveBeenCalledWith("d",expect.stringMatching(/^M /));
  expect([canvas.width,canvas.height]).toEqual([1,1]);renderer.destroy();
});

it("leaves the SVG fallback available if a mobile drawing context cannot be created", () => {
  vi.spyOn(HTMLCanvasElement.prototype,"getContext").mockReturnValue(null);
  expect(createMobileCanvasRenderer(document.createElement("div"),document.createElement("canvas"),{} as CanvasRenderingContext2D)).toBeNull();
});
