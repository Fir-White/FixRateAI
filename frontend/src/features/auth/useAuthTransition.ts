import { useCallback, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { animateMotion, type MotionRun } from "@/shared/motion/animate";

export function useAuthTransition(pathname: string, outlet: ReactNode, content: RefObject<HTMLDivElement | null>, main: RefObject<HTMLElement | null>, routeKey: string, navigationType: "POP" | "PUSH" | "REPLACE") {
  const [view, setView] = useState({ pathname, outlet, navigationType });
  const [phase, setPhase] = useState<"idle" | "exit" | "enter" | "success">("idle");
  const latest = useRef({ pathname, outlet, navigationType });
  latest.current = { pathname, outlet, navigationType };
  const animation = useRef<MotionRun | null>(null);
  const generation = useRef(0);
  const entering = useRef(false);
  const alive = useRef(false);
  useLayoutEffect(() => {
    alive.current = true;
    return () => { alive.current = false; generation.current++; animation.current?.cancel(); };
  }, []);
  useLayoutEffect(() => {
    const id = ++generation.current;
    const element = content.current;
    const start = element ? { opacity: getComputedStyle(element).opacity, transform: getComputedStyle(element).transform } : {};
    animation.current?.cancel();
    if (pathname === view.pathname) { setPhase("idle"); return; }
    if (element?.contains(document.activeElement)) main.current?.focus({ preventScroll: true });
    setPhase("exit");
    const run = element ? animateMotion(element, [start, { opacity: 0, transform: "translateY(-8px)" }], "--motion-auth-exit", true) : null;
    animation.current = run;
    const commit = () => {
      if (!alive.current || generation.current !== id) return;
      entering.current = true;
      setPhase("enter");
      setView(latest.current);
    };
    if (run) void run.finished.then(completed => { if (completed) commit(); });
    else commit();
    return () => run?.cancel();
  }, [pathname, view.pathname, routeKey, content, main]);
  useLayoutEffect(() => {
    if (!entering.current) return;
    entering.current = false;
    if (latest.current.pathname !== view.pathname) return;
    const element = content.current;
    if (!element) { setPhase("idle"); return; }
    const heading = element.querySelector<HTMLElement>("h1");
    // Place a new auth page before exposing it. POP keeps its scroll context
    // unless that would leave the focused heading outside the visible viewport.
    if (view.navigationType !== "POP") window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    if (heading) {
      const bounds = heading.getBoundingClientRect();
      const top = window.visualViewport?.offsetTop ?? 0;
      const bottom = top + (window.visualViewport?.height ?? window.innerHeight);
      if (bounds.top < top + 16 || bounds.bottom > bottom - 16) heading.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "instant" });
    }
    heading?.focus({ preventScroll: true });
    setPhase("enter");
    const id = generation.current;
    const run = animateMotion(element, [{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }], "--motion-auth-enter");
    animation.current = run;
    void run.finished.then(completed => {
      if (completed && alive.current && generation.current === id) { run.cancel(); setPhase("idle"); }
    });
    return () => run.cancel();
  }, [view.pathname, view.navigationType, content]);
  const leaveAfterSuccess = useCallback(async (navigate: () => void) => {
    const id = ++generation.current, path = latest.current.pathname;
    animation.current?.cancel();
    const element = content.current;
    if (element?.contains(document.activeElement)) main.current?.focus({ preventScroll: true });
    setPhase("success");
    const run = element ? animateMotion(element, [{ opacity: 1, transform: "translateY(0)" }, { opacity: 0, transform: "translateY(-8px)" }], "--motion-success-exit", true) : null;
    animation.current = run;
    const completed = run ? await run.finished : true;
    if (!completed || !alive.current || generation.current !== id || latest.current.pathname !== path) return false;
    navigate();
    return true;
  }, [content, main]);
  return { view, phase, leaveAfterSuccess };
}
