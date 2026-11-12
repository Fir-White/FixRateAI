import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkspaceAuroraBackground } from "@/layouts/WorkspaceAuroraBackground";
import { workspaceRasterSize } from "@/layouts/workspaceAuroraRenderer";

const renderer = vi.hoisted(() => ({ resize: vi.fn(), draw: vi.fn(), nudge: vi.fn(), destroy: vi.fn() }));
vi.mock("@/layouts/workspaceAuroraRenderer", async importOriginal => ({
  ...await importOriginal<object>(), createWorkspaceAuroraRenderer: vi.fn(() => renderer),
}));

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.clearAllMocks(); });

function environment(reduce = false, compact = false) {
  const media = new EventTarget();
  const reduced = Object.assign(media, { matches: reduce });
  vi.stubGlobal("CanvasRenderingContext2D", class {});
  vi.stubGlobal("matchMedia", (query: string) => query.includes("reduced") ? reduced : { matches: compact, addEventListener() {}, removeEventListener() {} });
  const frames = new Map<number, FrameRequestCallback>(); let id = 0;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.set(++id, callback); return id; });
  vi.stubGlobal("cancelAnimationFrame", (frame: number) => frames.delete(frame));
  const measure = vi.spyOn(HTMLCanvasElement.prototype, "getBoundingClientRect");
  const tick = (time: number) => act(() => { const current = [...frames.values()]; frames.clear(); current.forEach(callback => callback(time)); });
  return { frames, reduced, measure, tick };
}

describe("workspace background lifecycle", () => {
  it("caps the decorative raster independently of screen DPR", () => {
    for (const [width, height] of [[1920, 1080], [390, 844], [1, 1], [3840, 2160]]) {
      const size = workspaceRasterSize(width, height);
      expect(size.width).toBeLessThanOrEqual(960);
      expect(size.height).toBeLessThanOrEqual(640);
      expect(size.width * size.height).toBeLessThanOrEqual(614400);
    }
  });

  it("runs one loop, throttles drawing and never measures layout in a frame", () => {
    const env = environment(); const view = render(<WorkspaceAuroraBackground />);
    const reads = env.measure.mock.calls.length;
    expect(renderer.draw).toHaveBeenCalledWith(0);
    for (const time of [0, 16, 32, 48]) env.tick(time);
    expect(renderer.draw).toHaveBeenCalledTimes(1);
    env.tick(64);
    expect(renderer.draw).toHaveBeenCalledTimes(2);
    expect(env.frames.size).toBe(1);
    expect(env.measure).toHaveBeenCalledTimes(reads);
    view.unmount();
    expect(env.frames.size).toBe(0);
    expect(renderer.destroy).toHaveBeenCalledOnce();
  });

  it("freezes for reduced motion and a hidden tab, resumes phase and clamps long deltas", () => {
    const env = environment(true); const view = render(<WorkspaceAuroraBackground />);
    expect(env.frames.size).toBe(0);
    expect(view.container.querySelector("canvas")).toHaveAttribute("data-state", "paused");
    act(() => { env.reduced.matches = false; env.reduced.dispatchEvent(new Event("change")); });
    env.tick(0); env.tick(64);
    const phase = renderer.draw.mock.lastCall![0];
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(env.frames.size).toBe(0);
    hidden.mockReturnValue(false);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    env.tick(90000);
    expect(renderer.draw.mock.lastCall![0]).toBe(phase);
    env.tick(190000);
    expect(renderer.draw.mock.lastCall![0] - phase).toBeCloseTo(.064);
    view.unmount();
  });

  it("reacts to clicks and text input only inside the workspace, limits bursts and respects reduced motion", () => {
    const env = environment();
    env.measure.mockReturnValue({ width: 1000, height: 800 } as DOMRect);
    const view = render(<div className="workspace-root"><WorkspaceAuroraBackground /><input aria-label="Text" /></div>);
    const canvas = view.container.querySelector("canvas")!;
    fireEvent.mouseMove(canvas, { clientX: 250, clientY: 200 });
    expect(renderer.nudge).not.toHaveBeenCalled();
    fireEvent.click(canvas, { clientX: 250, clientY: 200, detail: 1, button: 0 });
    expect(renderer.nudge).toHaveBeenLastCalledWith(.25, .25, 1);
    fireEvent.click(canvas, { detail: 1, button: 0 });
    expect(renderer.nudge).toHaveBeenCalledTimes(1);
    fireEvent.input(view.getByLabelText("Text"));
    expect(renderer.nudge.mock.lastCall![2]).toBe(.3);
    fireEvent.input(view.getByLabelText("Text"));
    expect(renderer.nudge).toHaveBeenCalledTimes(2);
    act(() => { env.reduced.matches = true; env.reduced.dispatchEvent(new Event("change")); });
    fireEvent.click(canvas, { detail: 1 });
    fireEvent.input(view.getByLabelText("Text"));
    fireEvent.click(document.body);
    expect(renderer.nudge).toHaveBeenCalledTimes(2);
    view.unmount();
    fireEvent.click(canvas);
    expect(renderer.nudge).toHaveBeenCalledTimes(2);
  });
});
