import { useRef } from "react";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useScrollBoundary } from "@/shared/lib/useScrollBoundary";

function Harness({ enabled = true }: { enabled?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useScrollBoundary(ref, enabled);
  return <><div ref={ref} data-testid="boundary"><div data-testid="scroller" style={{ overflowY: "auto", overflowX: "auto" }}><span data-testid="target">Content</span></div></div><div data-testid="page">Main page</div></>;
}

function wheel(target: HTMLElement, init: WheelEventInit = { deltaY: 100 }) {
  const event = new WheelEvent("wheel", { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event.defaultPrevented;
}

function touch(target: HTMLElement, type: string, points: { clientX: number; clientY: number }[]) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, "touches", { value: points });
  target.dispatchEvent(event);
  return event.defaultPrevented;
}

describe("independent panel scrolling", () => {
  it("blocks the page over a static panel and releases outside, when disabled and after unmount", () => {
    const view = render(<Harness />);
    const boundary = view.getByTestId("boundary");
    expect(wheel(boundary)).toBe(true);
    expect(wheel(view.getByTestId("page"))).toBe(false);
    expect(wheel(boundary, { deltaY: 100, ctrlKey: true })).toBe(false);
    view.rerender(<Harness enabled={false} />);
    expect(wheel(boundary)).toBe(false);
    view.rerender(<Harness />);
    view.unmount();
    expect(wheel(boundary)).toBe(false);
  });

  it("allows internal scrolling but blocks chaining at both ends and on a non-scrollable axis", () => {
    const view = render(<Harness />);
    const scroller = view.getByTestId("scroller");
    const target = view.getByTestId("target");
    Object.defineProperties(scroller, { clientHeight: { value: 100 }, scrollHeight: { value: 400 }, clientWidth: { value: 100 }, scrollWidth: { value: 300 } });
    expect(wheel(target)).toBe(false);
    expect(wheel(target, { deltaY: -100 })).toBe(true);
    scroller.scrollTop = 300;
    expect(wheel(target)).toBe(true);
    expect(wheel(target, { deltaY: -100 })).toBe(false);
    expect(wheel(target, { deltaX: 100 })).toBe(false);
    expect(wheel(target, { deltaY: 100, shiftKey: true })).toBe(false);
    scroller.scrollLeft = 200;
    expect(wheel(target, { deltaX: 100 })).toBe(true);
    expect(wheel(target, { deltaY: 100, shiftKey: true })).toBe(true);
  });

  it("contains single-finger scrolling while preserving pinch zoom", () => {
    const view = render(<Harness />);
    const panel = view.getByTestId("boundary");
    touch(panel, "touchstart", [{ clientX: 20, clientY: 80 }]);
    expect(touch(panel, "touchmove", [{ clientX: 20, clientY: 30 }])).toBe(true);
    expect(touch(panel, "touchmove", [{ clientX: 10, clientY: 10 }, { clientX: 50, clientY: 50 }])).toBe(false);
  });
});
