import { useCallback, useEffect, useRef, useState, type RefObject, type PointerEvent } from "react";
import { isAuthGestureEnabled } from "./authGesture";

/** Keep a native press target fixed until its click has dispatched. */
export function useInitialReveal(main: RefObject<HTMLElement | null>) {
  const [revealing, setRevealing] = useState(true);
  const pressed = useRef<Element | null>(null);
  const paused = useRef<Animation[]>([]);
  const settle = useCallback(() => {
    pressed.current = null;
    for (const animation of main.current?.getAnimations?.({ subtree: true }) ?? []) {
      if (animation.id === "motion-auth-enter" && animation.playState !== "idle") animation.finish();
    }
    paused.current = [];
    setRevealing(false);
  }, [main]);
  useEffect(() => {
    const release = (event: Event) => { if (!isAuthGestureEnabled(pressed.current) || !(event.target instanceof Node) || !pressed.current.contains(event.target)) settle(); };
    document.addEventListener("click", settle);
    document.addEventListener("pointerup", release, true);
    document.addEventListener("pointercancel", settle, true);
    document.addEventListener("keydown", settle, true);
    window.addEventListener("blur", settle);
    return () => {
      document.removeEventListener("click", settle);
      document.removeEventListener("pointerup", release, true);
      document.removeEventListener("pointercancel", settle, true);
      document.removeEventListener("keydown", settle, true);
      window.removeEventListener("blur", settle);
      paused.current.forEach(animation => animation.cancel());
    };
  }, [settle]);
  return {
    revealing,
    press: (event: PointerEvent<HTMLElement>) => {
      const control = event.target instanceof Element ? event.target.closest("a,button,input,select,textarea") : null;
      if (!isAuthGestureEnabled(control)) { settle(); return; }
      pressed.current = control;
      paused.current = (main.current?.getAnimations?.({ subtree: true }) ?? []).filter(animation => animation.id === "motion-auth-enter" || ("animationName" in animation && String(animation.animationName).startsWith("auth-reveal-")));
      paused.current.forEach(animation => animation.pause());
    },
    focus: () => { if (!pressed.current) settle(); },
  };
}
