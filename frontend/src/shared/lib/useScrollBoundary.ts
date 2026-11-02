import { useEffect, type RefObject } from "react";

/** Allow scrolling inside a panel, but never chain its wheel/touch to the page. */
export function useScrollBoundary<T extends HTMLElement>(ref: RefObject<T | null>, enabled = true) {
  useEffect(() => {
    const boundary = ref.current;
    if (!enabled || !boundary) return;
    let touch: { x: number; y: number } | null = null;

    const consume = (target: EventTarget | null, dx: number, dy: number) => {
      const vertical = Math.abs(dy) >= Math.abs(dx);
      const delta = vertical ? dy : dx;
      if (!delta) return true;
      let node = target instanceof Element ? target : null;
      while (node && boundary.contains(node)) {
        if (node instanceof HTMLElement) {
          const range = vertical ? node.scrollHeight - node.clientHeight : node.scrollWidth - node.clientWidth;
          if (range > 1) {
            const style = getComputedStyle(node);
            const overflow = vertical ? style.overflowY : style.overflowX;
            const position = vertical ? node.scrollTop : node.scrollLeft;
            if (/^(auto|scroll|overlay)$/.test(overflow) && (delta > 0 ? position < range - .5 : position > .5)) return true;
          }
        }
        if (node === boundary) break;
        node = node.parentElement;
      }
      return false;
    };
    const wheel = (event: WheelEvent) => {
      if (event.defaultPrevented || event.ctrlKey) return;
      // Preserve native select/number/range controls inside dialogs.
      if (event.target instanceof Element && event.target.closest('select,input[type="number"],input[type="range"]')) return;
      const dx = event.shiftKey && !event.deltaX ? event.deltaY : event.deltaX;
      const dy = event.shiftKey && !event.deltaX ? 0 : event.deltaY;
      if (!consume(event.target, dx, dy)) event.preventDefault();
    };
    const start = (event: TouchEvent) => {
      touch = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY } : null;
    };
    const move = (event: TouchEvent) => {
      if (event.touches.length !== 1) { touch = null; return; }
      const next = { x: event.touches[0].clientX, y: event.touches[0].clientY };
      const previous = touch;
      touch = next;
      if (previous && !event.defaultPrevented && !consume(event.target, previous.x - next.x, previous.y - next.y)) event.preventDefault();
    };
    boundary.addEventListener("wheel", wheel, { passive: false });
    boundary.addEventListener("touchstart", start, { passive: true });
    boundary.addEventListener("touchmove", move, { passive: false });
    return () => {
      boundary.removeEventListener("wheel", wheel);
      boundary.removeEventListener("touchstart", start);
      boundary.removeEventListener("touchmove", move);
    };
  }, [ref, enabled]);
}
