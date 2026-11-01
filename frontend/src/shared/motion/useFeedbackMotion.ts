import { useLayoutEffect, useRef } from "react";
import { motionDuration } from "./animate";
import { registerFeedbackMotion } from "./feedbackMotion";

/** Bounded layout work only when an auth hint/error changes, never in a frame loop. */
export function useFeedbackMotion(message: string | undefined) {
  const ref = useRef<HTMLDivElement>(null);
  const previousHeight = useRef<number | null>(null);
  const current = useRef<Animation | null>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const start = current.current ? element.getBoundingClientRect().height : previousHeight.current;
    current.current?.cancel();
    const height = element.getBoundingClientRect().height;
    previousHeight.current = height;
    const duration = motionDuration(element, "--motion-fast");
    if (start === null || Math.abs(start - height) < 0.5 || !element.closest(".auth-form") || !duration || typeof element.animate !== "function") return;
    const animation = element.animate([{ height: `${start}px` }, { height: `${height}px` }], { duration, easing: getComputedStyle(element).getPropertyValue("--ease-standard").trim() || "ease-out" });
    animation.id = "motion-feedback-layout";
    const unregister = registerFeedbackMotion(animation, element);
    current.current = animation;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const finish = () => { if (animation.playState !== "idle" && (reduced?.matches || document.hidden)) animation.finish(); };
    reduced?.addEventListener("change", finish);
    document.addEventListener("visibilitychange", finish);
    void animation.finished.catch(() => {}).finally(() => {
      unregister();
      if (current.current === animation) current.current = null;
      reduced?.removeEventListener("change", finish);
      document.removeEventListener("visibilitychange", finish);
    });
  }, [message]);
  useLayoutEffect(() => () => current.current?.cancel(), []);
  return ref;
}
