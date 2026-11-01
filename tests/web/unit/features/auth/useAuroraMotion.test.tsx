import { StrictMode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuroraScene } from "@/features/auth/AuroraScene";

class Media extends EventTarget {
  constructor(public matches: boolean) { super(); }
  set(value: boolean) { this.matches = value; this.dispatchEvent(new Event("change")); }
}
let reduced: Media, mouse: Media, desktop: Media;
let hidden: boolean;
let intersect: IntersectionObserverCallback;
const disconnect = vi.fn();
beforeEach(() => {
  reduced = new Media(false); mouse = new Media(true); desktop = new Media(true); hidden = false;
  vi.stubGlobal("matchMedia", (query: string) => query.includes("reduced-motion") ? reduced : query.includes("pointer") ? mouse : desktop);
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: IntersectionObserverCallback) { intersect = callback; }
    observe() {} disconnect = disconnect;
  });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const visibility = (value: boolean) => act(() => { hidden = value; document.dispatchEvent(new Event("visibilitychange")); });
const offscreen = (value: boolean) => act(() => intersect([{ isIntersecting: !value } as IntersectionObserverEntry], {} as IntersectionObserver));

it("uses static shared paths without a JS frame loop or pointer writes; logo is outside the light container", () => {
  const raf = vi.spyOn(window, "requestAnimationFrame");
  const view = render(<AuroraScene />);
  const scene = view.container.querySelector(".auth-aurora")!;
  const paths = [...scene.querySelectorAll("[data-aurora-ribbon]")];
  const initial = paths.map(path => path.getAttribute("d"));
  fireEvent.pointerMove(window, { clientX: 1200, clientY: 650, pointerType: "mouse" });
  expect(raf).not.toHaveBeenCalled();
  expect(scene.getAttribute("style")).toBeNull();
  expect(paths.map(path => path.getAttribute("d"))).toEqual(initial);
  expect(scene.querySelector(".auth-light-motion .auth-aurora__brand")).toBeNull();
  expect(scene.querySelectorAll(".auth-light-motion")).toHaveLength(2);
  for (const wrapper of scene.querySelectorAll(".auth-light-motion")) {
    expect(wrapper.querySelectorAll("[data-aurora-ribbon]")).toHaveLength(1);
  }
  expect(paths).toHaveLength(3);
});

it("replaces the orbs with ten deterministic peripheral particles and no scene control", () => {
  const view = render(<AuroraScene />);
  expect(view.container.querySelectorAll('.auth-particle[aria-hidden="true"]')).toHaveLength(10);
  expect(view.container.querySelector(".auth-orb, .auth-motion-toggle")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
  expect(view.container.querySelector(".auth-aurora__scrim")).not.toBeNull();
});

it("retains manual pause across hidden/offscreen/media changes without replacing the light node", () => {
  const view = render(<AuroraScene />);
  const scene = view.container.querySelector(".auth-aurora")!;
  const light = scene.querySelector(".auth-light-motion");
  expect(scene).toHaveAttribute("data-motion", "running");
  view.rerender(<AuroraScene animationEnabled={false} />);
  visibility(true); visibility(false); offscreen(true); offscreen(false);
  act(() => { reduced.set(true); reduced.set(false); desktop.set(false); desktop.set(true); });
  expect(scene).toHaveAttribute("data-motion", "paused");
  expect(scene.querySelector(".auth-light-motion")).toBe(light);
  view.rerender(<AuroraScene animationEnabled />);
  expect(scene).toHaveAttribute("data-motion", "running");
  visibility(true); expect(scene).toHaveAttribute("data-motion", "paused");
  visibility(false); expect(scene).toHaveAttribute("data-motion", "running");
  offscreen(true); expect(scene).toHaveAttribute("data-motion", "paused");
  offscreen(false); expect(scene).toHaveAttribute("data-motion", "running");
});

it("stays static for reduced motion, coarse pointer and mobile; cleans up StrictMode listeners", () => {
  const add = vi.spyOn(document, "addEventListener");
  const remove = vi.spyOn(document, "removeEventListener");
  const mediaListeners = [reduced, mouse, desktop].map(media => ({ add: vi.spyOn(media, "addEventListener"), remove: vi.spyOn(media, "removeEventListener") }));
  const view = render(<StrictMode><AuroraScene /></StrictMode>);
  const scene = view.container.querySelector(".auth-aurora")!;
  for (const media of [reduced, mouse, desktop]) {
    act(() => media.set(media === reduced));
    expect(scene).toHaveAttribute("data-motion", "paused");
    expect(screen.queryByRole("button")).toBeNull();
    act(() => media.set(media !== reduced));
  }
  view.unmount();
  expect(disconnect).toHaveBeenCalled();
  for (const [type, listener] of add.mock.calls.filter(([type]) => type === "visibilitychange")) {
    expect(remove.mock.calls.some(([removedType, removedListener]) => removedType === type && removedListener === listener)).toBe(true);
  }
  for (const media of mediaListeners) {
    for (const [type, listener] of media.add.mock.calls) {
      expect(media.remove.mock.calls.some(([removedType, removedListener]) => removedType === type && removedListener === listener)).toBe(true);
    }
  }
  visibility(true);
  act(() => reduced.set(true));
  expect(scene).toHaveAttribute("data-motion", "paused");
});
