import { Profiler, StrictMode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuroraScene } from "@/features/auth/AuroraScene";
const renderer = vi.hoisted(() => ({ resize: vi.fn(), render: vi.fn(), destroy: vi.fn() }));
vi.mock("@/features/auth/canvasRenderer", () => ({ createAuroraRenderer: () => renderer }));
class Media extends EventTarget { constructor(public matches: boolean) { super(); } set(value: boolean) { this.matches = value; this.dispatchEvent(new Event("change")); } }
let reduced: Media, desktop: Media, compactLandscape: Media, hidden: boolean, intersect: IntersectionObserverCallback;
let frames: Map<number, FrameRequestCallback>;
const disconnect = vi.fn();
beforeEach(() => {
  reduced = new Media(false); desktop = new Media(true); compactLandscape = new Media(false); hidden = false;
  frames = new Map(); let nextId = 0;
  renderer.resize.mockClear(); renderer.render.mockClear(); renderer.destroy.mockClear();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.set(++nextId, callback); return nextId; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => { frames.delete(id); });
  vi.stubGlobal("matchMedia", vi.fn((query: string) => query.includes("reduced-motion") ? reduced : query.includes("max-height: 500px") ? compactLandscape : desktop));
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  vi.stubGlobal("IntersectionObserver", class { constructor(callback: IntersectionObserverCallback) { intersect = callback; } observe() {} disconnect = disconnect; });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const visibility = (value: boolean) => act(() => { hidden = value; document.dispatchEvent(new Event("visibilitychange")); });
const offscreen = (value: boolean) => act(() => intersect([{ isIntersecting: !value } as IntersectionObserverEntry], {} as IntersectionObserver));
const tick = (time: number) => { const pending = [...frames.values()]; frames.clear(); pending.forEach(callback => callback(time)); };
it("renders lights at30Hz and particles at60Hz with one clock and no frame-time React or layout", () => {
  const renders = vi.fn(); const view = render(<Profiler id="aurora" onRender={renders}><AuroraScene /></Profiler>);
  const scene = view.container.querySelector(".auth-aurora")!;
  const count = renders.mock.calls.length;
  const layout = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
  const styles = vi.spyOn(CSSStyleDeclaration.prototype, "setProperty");
  const queries = vi.spyOn(scene, "querySelectorAll");
  renderer.render.mockClear(); renderer.resize.mockClear();
  for (let frame = 0; frame <= 144; frame++) { tick(frame * 1000 / 144); expect(frames.size).toBe(1); }
  expect(renderer.render.mock.calls.filter(([, lights]) => lights).length).toBe(30);
  expect(renderer.render).toHaveBeenCalledTimes(60);
  expect(renderer.resize).not.toHaveBeenCalled(); expect(layout).not.toHaveBeenCalled(); expect(styles).not.toHaveBeenCalled(); expect(queries).not.toHaveBeenCalled();
  expect(renders.mock.calls.length).toBe(count);
  expect(view.container.querySelectorAll("canvas")).toHaveLength(1);
  expect(view.container.querySelectorAll("svg filter")).toHaveLength(3);
  expect(view.container.querySelectorAll("[data-aurora-ribbon]")).toHaveLength(3);
  expect(view.container.querySelectorAll("svg use")).toHaveLength(8);
  expect(view.container.querySelector("svg mask, .auth-particle, .auth-orb")).toBeNull();
  expect(view.container.querySelector("img, .auth-aurora__brand, .auth-aurora__logo, .auth-aurora__scrim, .auth-aurora__vignette")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
});
it.each([60,90,120,240])("maintains the requested cadence at a %i Hz display", refreshRate => {
  render(<AuroraScene />);
  renderer.render.mockClear();
  for(let frame=0;frame<=refreshRate;frame++) tick(frame*1000/refreshRate);
  expect(renderer.render).toHaveBeenCalledTimes(60);
  expect(renderer.render.mock.calls.filter(([, lights])=>lights)).toHaveLength(30);
  expect(renderer.render.mock.calls.at(-1)?.[0]).toBeCloseTo(1,8);
  expect(frames.size).toBe(1);
});
it("retains manual pause across hidden/offscreen/media changes without resetting phase", () => {
  const view = render(<AuroraScene />); const scene = view.container.querySelector(".auth-aurora")!;
  tick(0); tick(100); const phase = renderer.render.mock.calls.at(-1)![0];
  view.rerender(<AuroraScene animationEnabled={false} />); expect(frames.size).toBe(0);
  visibility(true); visibility(false); offscreen(true); offscreen(false);
  act(() => { reduced.set(true); reduced.set(false); desktop.set(false); desktop.set(true); });
  expect(scene).toHaveAttribute("data-motion", "paused"); expect(frames.size).toBe(0);
  view.rerender(<AuroraScene animationEnabled />); expect(frames.size).toBe(1);
  tick(100000); expect(renderer.render.mock.calls.at(-1)![0]).toBe(phase);
  tick(100050); expect(renderer.render.mock.calls.at(-1)![0]).toBeGreaterThan(phase);
});
it("keeps reduced motion static and cleans up StrictMode", () => {
  const add = vi.spyOn(document, "addEventListener"), remove = vi.spyOn(document, "removeEventListener");
  const view = render(<StrictMode><AuroraScene /></StrictMode>); const scene = view.container.querySelector(".auth-aurora")!;
  expect(frames.size).toBe(1); expect(renderer.resize).toHaveBeenCalled();
  act(() => reduced.set(true)); expect(scene).toHaveAttribute("data-motion", "paused"); expect(frames.size).toBe(0);
  act(() => reduced.set(false));expect(frames.size).toBe(1);
  view.unmount(); expect(frames.size).toBe(0); expect(renderer.destroy).toHaveBeenCalled(); expect(disconnect).toHaveBeenCalled();
  for (const [type, listener] of add.mock.calls.filter(([type]) => type === "visibilitychange")) expect(remove.mock.calls.some(([t,l]) => t === type && l === listener)).toBe(true);
});
it("does not subscribe to cursor movement or make animation depend on mouse capability", () => {
  const addWindow=vi.spyOn(window,"addEventListener"), addDocument=vi.spyOn(document,"addEventListener");
  const view=render(<AuroraScene />);
  expect(frames.size).toBe(1);
  const types=[...addWindow.mock.calls,...addDocument.mock.calls].map(([type])=>type);
  expect(types).not.toContain("pointermove"); expect(types).not.toContain("mousemove"); expect(types).not.toContain("pointerleave");
  expect(vi.mocked(window.matchMedia).mock.calls.map(([query])=>query).some(query=>query.includes("pointer")||query.includes("hover"))).toBe(false);
  tick(0); tick(100); expect(renderer.render.mock.calls.at(-1)![0]).toBeCloseTo(.064);
  view.unmount(); expect(frames.size).toBe(0);
});
it.each(["portrait","landscape"])("runs mobile %s at30 geometry updates with1.9x phase and no extra frame work", orientation => {
  if(orientation==="portrait")desktop.matches=false;else compactLandscape.matches=true;
  const renders=vi.fn();const view=render(<Profiler id="mobile" onRender={renders}><AuroraScene /></Profiler>);
  expect(renderer.render.mock.calls.at(-1)).toEqual([0,true,"mobile"]);
  const count=renders.mock.calls.length,layout=vi.spyOn(HTMLElement.prototype,"getBoundingClientRect");
  renderer.render.mockClear();
  for(let frame=0;frame<=144;frame++){tick(frame*1000/144);expect(frames.size).toBe(1);}
  expect(renderer.render).toHaveBeenCalledTimes(30);
  expect(renderer.render.mock.calls.every(([,lights,profile])=>lights&&profile==="mobile")).toBe(true);
  expect(renderer.render.mock.calls.at(-1)?.[0]).toBeCloseTo(1.9,8);
  expect(layout).not.toHaveBeenCalled();expect(renders.mock.calls.length).toBe(count);
  expect(view.container.querySelector(".auth-aurora")).toHaveAttribute("data-profile","mobile");
  const phase=renderer.render.mock.calls.at(-1)![0];visibility(true);expect(frames.size).toBe(0);
  visibility(false);tick(60000);expect(renderer.render.mock.calls.at(-1)![0]).toBe(phase);
  tick(60050);expect(renderer.render.mock.calls.at(-1)![0]).toBeCloseTo(phase+.05*1.9,8);
});
it("changes profiles in compact landscape while retaining the integrated phase", () => {
  render(<AuroraScene />);
  tick(0); tick(50);
  const phase = renderer.render.mock.calls.at(-1)![0];
  act(() => compactLandscape.set(true));
  expect(frames.size).toBe(1);
  expect(renderer.render.mock.calls.at(-1)).toEqual([phase,true,"mobile"]);
  tick(100);
  const mobilePhase=renderer.render.mock.calls.at(-1)![0];
  expect(mobilePhase).toBeCloseTo(phase+.05*1.9,8);
  act(() => compactLandscape.set(false));
  expect(frames.size).toBe(1);
  expect(renderer.render.mock.calls.at(-1)).toEqual([mobilePhase,true]);
  tick(150);expect(renderer.render.mock.calls.at(-1)![0]).toBeCloseTo(mobilePhase+.05,8);
});
it("only resizes on resize events, and cancels immediately if reduced matches changes before its event", () => {
  const view = render(<AuroraScene />); tick(0); tick(50);
  const calls = renderer.resize.mock.calls.length;
  fireEvent(window, new Event("resize")); expect(renderer.resize.mock.calls.length).toBe(calls + 1);
  reduced.matches = true; tick(100); expect(frames.size).toBe(0);
  expect(view.container.querySelectorAll("canvas")).toHaveLength(1);
});
it("redraws only particles on deferred resize while manual pause preserves the last light frame", () => {
  const view = render(<AuroraScene />);
  tick(0); tick(36); tick(51); tick(60);
  const lastLight = renderer.render.mock.calls.filter(([, lights]) => lights).at(-1)![0];
  const particlePhase = renderer.render.mock.calls.at(-1)![0];
  expect(particlePhase).toBeGreaterThan(lastLight);
  view.rerender(<AuroraScene animationEnabled={false} />);
  renderer.render.mockClear();
  fireEvent(window,new Event("resize"));
  visibility(true); visibility(false);
  fireEvent(window,new Event("resize"));
  expect(frames.size).toBe(0);
  expect(renderer.render.mock.calls).toEqual([[particlePhase,false],[particlePhase,false]]);
});
