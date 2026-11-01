import { StrictMode } from "react";
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuroraScene } from "./AuroraScene";

class Media extends EventTarget {
  constructor(public matches: boolean) { super(); }
  set(value: boolean) { this.matches = value; this.dispatchEvent(new Event("change")); }
}

let reduced: Media;
let mouse: Media;
let desktop: Media;
let hidden: boolean;
let callbacks: Map<number, FrameRequestCallback>;

beforeEach(() => {
  reduced = new Media(false);
  mouse = new Media(true);
  desktop = new Media(true);
  hidden = false;
  callbacks = new Map();
  let nextId = 0;
  vi.stubGlobal("matchMedia", (query: string) => query.includes("reduced-motion") ? reduced : query.includes("pointer") ? mouse : desktop);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { callbacks.set(++nextId, callback); return nextId; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => callbacks.delete(id));
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  vi.spyOn(performance, "now").mockReturnValue(0);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ left: 460, top: 0, width: 980, height: 900, right: 1440, bottom: 900, x: 460, y: 0, toJSON: () => ({}) });
});

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function tick(time: number) {
  const pending = [...callbacks.values()];
  callbacks.clear();
  for (const callback of pending) callback(time);
}

function moveMouse() {
  const event = new MouseEvent("pointermove", { clientX: 1195, clientY: 675 });
  Object.defineProperty(event, "pointerType", { value: "mouse" });
  window.dispatchEvent(event);
}

describe("aurora motion lifecycle", () => {
  it("has the same pointer response after one second at 60 and 144 Hz without measuring layout per frame", () => {
    const positions = [60, 144].map(fps => {
      const view = render(<AuroraScene />);
      const scene = view.container.firstElementChild as HTMLElement;
      const reads = vi.mocked(HTMLElement.prototype.getBoundingClientRect).mock.calls.length;
      moveMouse();
      for (let index = 0; index <= fps; index++) {
        tick(index * 1000 / fps);
        expect(callbacks.size).toBe(1);
      }
      expect(vi.mocked(HTMLElement.prototype.getBoundingClientRect).mock.calls.length).toBe(reads);
      const position = Number(scene.style.getPropertyValue("--aurora-x"));
      view.unmount();
      expect(callbacks.size).toBe(0);
      return position;
    });
    expect(positions[0]).toBeGreaterThan(0.45);
    expect(Math.abs(positions[0] - positions[1])).toBeLessThan(0.0002);
  });

  it("runs no animation for reduced motion, touch devices or a hidden mobile scene", () => {
    reduced.set(true);
    const view = render(<AuroraScene />);
    moveMouse();
    expect(callbacks.size).toBe(0);
    mouse.set(false);
    reduced.set(false);
    expect(callbacks.size).toBe(0);
    desktop.set(false);
    mouse.set(true);
    expect(callbacks.size).toBe(0);
    desktop.set(true);
    expect(callbacks.size).toBe(1);
    tick(0);
    tick(100);
    reduced.set(true);
    expect(callbacks.size).toBe(0);
    expect(view.container.firstElementChild?.getAttribute("style")).toBe("");
  });

  it("pauses a hidden tab and resumes with a single clock", () => {
    const view = render(<AuroraScene />);
    tick(0);
    hidden = true;
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(callbacks.size).toBe(0);
    hidden = false;
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(callbacks.size).toBe(1);
    view.unmount();
    expect(callbacks.size).toBe(0);
  });

  it("clears the last animated frame even when a browser updates media matches before its change event", () => {
    const view = render(<AuroraScene />);
    moveMouse();
    tick(0);
    tick(100);
    reduced.matches = true;
    tick(116);
    expect(callbacks.size).toBe(0);
    expect(view.container.firstElementChild?.getAttribute("style")).toBe("");
  });

  it("does not leave duplicate RAFs or event listeners after Strict Mode remounts", () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    const view = render(<StrictMode><AuroraScene /></StrictMode>);
    expect(callbacks.size).toBe(1);
    view.unmount();
    expect(callbacks.size).toBe(0);
    for (const [type, listener] of add.mock.calls.filter(([type]) => ["pointermove", "pointerout", "resize", "blur"].includes(type))) {
      expect(remove.mock.calls.some(([removedType, removedListener]) => removedType === type && removedListener === listener)).toBe(true);
    }
    reduced.set(true);
    reduced.set(false);
    desktop.set(false);
    desktop.set(true);
    expect(callbacks.size).toBe(0);
  });
});
