export type MotionRun = { finished: Promise<boolean>; cancel: () => void };

export function motionDuration(element: Element, token: string): number {
  if (document.hidden || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return 0;
  const value = getComputedStyle(element).getPropertyValue(token).trim();
  return (Number.parseFloat(value) || 0) * (value.endsWith("ms") ? 1 : 1000);
}

/** One bounded browser animation, with immediate reduced-motion/hidden fallback. */
export function animateMotion(element: HTMLElement, frames: Keyframe[], token: string, exit = false): MotionRun {
  const duration = motionDuration(element, token);
  if (!duration || typeof element.animate !== "function") return { finished: Promise.resolve(true), cancel: () => {} };
  const easing = getComputedStyle(element).getPropertyValue(exit ? "--ease-exit" : "--ease-standard").trim() || "ease-out";
  const animation = element.animate(frames, { duration, easing, fill: "both" });
  animation.id = token.slice(2);
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  let cancelled = false;
  const finish = () => { if (!cancelled && (document.hidden || reduced?.matches)) animation.finish(); };
  const cleanup = () => {
    reduced?.removeEventListener("change", finish);
    document.removeEventListener("visibilitychange", finish);
  };
  reduced?.addEventListener("change", finish);
  document.addEventListener("visibilitychange", finish);
  const finished = animation.finished.then(() => true, () => false).finally(cleanup);
  return { finished, cancel: () => { cancelled = true; cleanup(); animation.cancel(); } };
}
