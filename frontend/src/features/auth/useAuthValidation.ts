import { useEffect, useRef, useState, type FocusEvent } from "react";
import { focusAuthError, validateAuth, validateAuthField, type AuthErrors, type AuthField, type AuthMode, type AuthValues } from "./authValidation";
import { holdFeedbackMotion, releaseFeedbackMotion } from "@/shared/motion/feedbackMotion";
import { isAuthGestureEnabled } from "./authGesture";

export function useAuthValidation(mode: AuthMode, values: AuthValues) {
  const [revealed, setRevealed] = useState<Partial<Record<AuthField, boolean>>>({});
  const [serverErrors, setServerErrors] = useState<AuthErrors>({});
  const pressedAction = useRef<Element | null>(null);
  const gestureAction = useRef<Element | null>(null);
  const heldFeedbackRoot = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const action = (target: EventTarget | null) => {
      const candidate = target instanceof Element ? target.closest("a[href], button") : null;
      return isAuthGestureEnabled(candidate) ? candidate : null;
    };
    const resume = () => { if (heldFeedbackRoot.current) releaseFeedbackMotion(heldFeedbackRoot.current); heldFeedbackRoot.current = null; };
    const clear = () => { pressedAction.current = null; gestureAction.current = null; resume(); };
    const press = (event: Event) => {
      const control = event.target instanceof Element ? event.target.closest("a,button,input,select,textarea") : null;
      if (!isAuthGestureEnabled(control)) { clear(); return; }
      const target = action(event.target);
      if (gestureAction.current !== target) resume();
      pressedAction.current = target;
      gestureAction.current = target;
      const root = control?.closest<HTMLElement>(".auth-panel") ?? null;
      if (root !== heldFeedbackRoot.current) { resume(); heldFeedbackRoot.current = root; if (root) holdFeedbackMotion(root); }
    };
    const release = (event: Event) => {
      if (!isAuthGestureEnabled(gestureAction.current) || !(event.target instanceof Node) || !gestureAction.current.contains(event.target)) clear();
    };
    // Blur can run before a link/button click, and rendering an error then moves
    // the pressed target. Keep its native gesture intact; submit still validates.
    // Compatibility mousedown covers touch browsers that blur after pointerup.
    document.addEventListener("pointerdown", press, true);
    document.addEventListener("mousedown", press, true);
    document.addEventListener("pointerup", release, true);
    document.addEventListener("pointercancel", clear, true);
    document.addEventListener("click", clear);
    document.addEventListener("keydown", clear, true);
    window.addEventListener("blur", clear);
    return () => {
      document.removeEventListener("pointerdown", press, true);
      document.removeEventListener("mousedown", press, true);
      document.removeEventListener("pointerup", release, true);
      document.removeEventListener("pointercancel", clear, true);
      document.removeEventListener("click", clear);
      document.removeEventListener("keydown", clear, true);
      window.removeEventListener("blur", clear);
      clear();
    };
  }, []);
  const errors: AuthErrors = { ...serverErrors };
  for (const field of Object.keys(values) as AuthField[]) {
    if (revealed[field]) {
      const error = validateAuthField(field, values, mode);
      if (error) errors[field] = error;
    }
  }
  return {
    errors,
    reset: () => { setRevealed({}); setServerErrors({}); },
    state: (field: AuthField) => errors[field] ? "invalid" : revealed[field] ? "valid" : undefined,
    blur: (field: AuthField, event: FocusEvent<HTMLInputElement>) => {
      const candidate = event.relatedTarget instanceof Element ? event.relatedTarget.closest("a[href], button") : null;
      const focusAction = isAuthGestureEnabled(candidate);
      const pointerAction = pressedAction.current;
      pressedAction.current = null;
      if (!focusAction && !pointerAction) setRevealed(previous => ({ ...previous, [field]: true }));
    },
    change: (field: AuthField) => setServerErrors(previous => ({ ...previous, [field]: undefined })),
    server: (next: AuthErrors = {}) => {
      setServerErrors(next);
      setRevealed(previous => ({ ...previous, ...Object.fromEntries(Object.keys(next).map(field => [field, true])) }));
    },
    validate: (form: HTMLFormElement) => {
      const next = validateAuth(values, mode);
      setServerErrors({});
      setRevealed(Object.fromEntries(Object.keys(values).map(field => [field, true])));
      focusAuthError(form, next);
      return Object.keys(next).length === 0;
    },
  };
}
