import { useLayoutEffect, useRef } from "react";

let initialOwner: object | undefined;
const MOBILE_QUERY = "(max-width: 820px), (max-width: 1000px) and (max-height: 500px)";

/** Native reload restoration must not reopen a fresh auth document midway down
 * its form. Claim that document once; subsequent SPA/POP entries keep their
 * normal scroll behavior. Nothing subscribes to resize, focus or touch. */
export function useMobileAuthViewport(navigationType: "POP" | "PUSH" | "REPLACE") {
  const owner = useRef({});
  const initialNavigation = useRef(navigationType);
  useLayoutEffect(() => {
    const entry = performance.getEntriesByType?.("navigation")[0] as PerformanceNavigationTiming | undefined;
    if (!entry || initialNavigation.current !== "POP" || !["navigate", "reload"].includes(entry.type)) return;
    if (new URL(entry.name).pathname !== window.location.pathname || !/^\/(login|register)\/?$/.test(window.location.pathname)) return;
    if (!window.matchMedia(MOBILE_QUERY).matches || (initialOwner && initialOwner !== owner.current)) return;
    initialOwner = owner.current;
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    const restore = () => { window.history.scrollRestoration = previous; };
    window.addEventListener("pagehide", restore);
    return () => { window.removeEventListener("pagehide", restore); restore(); };
  }, []);
}
