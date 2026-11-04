import { useLayoutEffect, type RefObject } from "react";
import { useLocation, useNavigationType } from "react-router-dom";
import { readWorkspaceValue, workspaceKey, writeWorkspaceValue } from "./workspaceState";

interface Position { x: number; y: number }
interface View { page: Position; scrolls: Record<string, Position>; details: Record<string, boolean> }
const position = (value: unknown): value is Position => !!value && typeof value === "object" &&
  ["x", "y"].every(key => { const n = (value as Record<string, unknown>)[key]; return typeof n === "number" && Number.isFinite(n) && n >= 0 && n < 1e7; });
const validView = (value: unknown): value is View => {
  if (!value || typeof value !== "object") return false;
  const view = value as View;
  return position(view.page) && !!view.scrolls && typeof view.scrolls === "object" && Object.values(view.scrolls).every(position) &&
    !!view.details && typeof view.details === "object" && Object.values(view.details).every(open => typeof open === "boolean");
};
const detailsKey = (element: HTMLDetailsElement, index: number) => `${index}:${element.querySelector("summary")?.textContent?.trim() ?? ""}`;

/** Restore after asynchronous page layout settles, without caching business data. */
export function useWorkspaceView(rootRef: RefObject<HTMLDivElement | null>, scope: string) {
  const location = useLocation();
  const navigation = useNavigationType();
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const key = workspaceKey(scope, `view:${location.pathname}${location.search}${location.hash}`);
    const navKey = workspaceKey(scope, "sidebar.scroll");
    const empty: View = { page: { x: 0, y: 0 }, scrolls: {}, details: {} };
    const saved = readWorkspaceValue<View | null>(key, null, (value): value is View => validView(value), true);
    let pending = navigation === "POP" && saved !== null;
    let last: View = { ...empty, page: { x: window.scrollX, y: window.scrollY } };
    let nav = readWorkspaceValue(navKey, { x: 0, y: 0 }, position, true);
    let timer: ReturnType<typeof setTimeout> | null = null;
    let resize: ResizeObserver | null = null;
    let mutation: MutationObserver | null = null;
    let restoreTimer: ReturnType<typeof setTimeout> | null = null;
    const previousRestoration = history.scrollRestoration;
    history.scrollRestoration = "manual";

    const snapshot = (): View => {
      const view: View = { page: { x: window.scrollX, y: window.scrollY }, scrolls: {}, details: {} };
      root.querySelectorAll<HTMLElement>("[data-scroll-key]").forEach(element => {
        const at = { x: element.scrollLeft, y: element.scrollTop };
        if (element.dataset.scrollKey === "sidebar") nav = at;
        else view.scrolls[element.dataset.scrollKey!] = at;
      });
      root.querySelectorAll("details").forEach((element, index) => { view.details[detailsKey(element, index)] = element.open; });
      return view;
    };
    const save = () => {
      if (pending) return;
      writeWorkspaceValue(key, last, true);
      writeWorkspaceValue(navKey, nav, true);
    };
    const restore = () => {
      if (!pending || !saved) return;
      root.querySelectorAll("details").forEach((element, index) => {
        const open = saved.details[detailsKey(element, index)];
        if (typeof open === "boolean" && element.open !== open) element.open = open;
      });
      root.querySelectorAll<HTMLElement>("[data-scroll-key]").forEach(element => {
        const at = element.dataset.scrollKey === "sidebar" ? nav : saved.scrolls[element.dataset.scrollKey!];
        if (at) { element.scrollLeft = at.x; element.scrollTop = at.y; }
      });
      window.scrollTo({ left: saved.page.x, top: saved.page.y, behavior: "instant" });
      if (!root.querySelector("[data-workspace-loading]")) {
        pending = false;
        resize?.disconnect(); mutation?.disconnect();
        last = snapshot();
      }
    };
    const scheduleRestore = () => {
      if (pending && restoreTimer === null) restoreTimer = setTimeout(() => { restoreTimer = null; restore(); }, 0);
    };
    const record = (event: Event) => {
      if (pending) return;
      if (event.type === "toggle") {
        root.querySelectorAll("details").forEach((element, index) => { last.details[detailsKey(element, index)] = element.open; });
      } else if (event.target instanceof HTMLElement && event.target.dataset.scrollKey) {
        const element = event.target;
        const at = { x: element.scrollLeft, y: element.scrollTop };
        if (element.dataset.scrollKey === "sidebar") nav = at;
        else last.scrolls[element.dataset.scrollKey!] = at;
      } else last.page = { x: window.scrollX, y: window.scrollY };
      if (timer === null) timer = setTimeout(() => { timer = null; save(); }, 150);
    };
    const cancelRestore = () => {
      if (pending) { pending = false; resize?.disconnect(); mutation?.disconnect(); last = snapshot(); }
    };
    const keydown = (event: KeyboardEvent) => {
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " ", "Tab"].includes(event.key)) cancelRestore();
    };
    const flush = () => { if (!pending) { last = snapshot(); save(); } };
    const visibility = () => { if (document.hidden) flush(); };

    if (pending) {
      if (typeof ResizeObserver === "function") { resize = new ResizeObserver(scheduleRestore); resize.observe(root); }
      mutation = new MutationObserver(scheduleRestore); mutation.observe(root, { subtree: true, childList: true });
      restore();
    } else {
      const element = root.querySelector<HTMLElement>('[data-scroll-key="sidebar"]');
      if (element) { element.scrollLeft = nav.x; element.scrollTop = nav.y; }
      last = snapshot();
    }
    root.addEventListener("scroll", record, true);
    window.addEventListener("scroll", record, { passive: true });
    root.addEventListener("toggle", record, true);
    root.addEventListener("wheel", cancelRestore, { passive: true, capture: true });
    root.addEventListener("touchstart", cancelRestore, { passive: true, capture: true });
    root.addEventListener("pointerdown", cancelRestore, true);
    document.addEventListener("keydown", keydown);
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      if (timer !== null) clearTimeout(timer);
      if (restoreTimer !== null) clearTimeout(restoreTimer);
      save(); resize?.disconnect(); mutation?.disconnect();
      history.scrollRestoration = previousRestoration;
      root.removeEventListener("scroll", record, true);
      window.removeEventListener("scroll", record);
      root.removeEventListener("toggle", record, true);
      root.removeEventListener("wheel", cancelRestore, true);
      root.removeEventListener("touchstart", cancelRestore, true);
      root.removeEventListener("pointerdown", cancelRestore, true);
      document.removeEventListener("keydown", keydown);
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [rootRef, scope, location.pathname, location.search, location.hash, navigation]);
}
