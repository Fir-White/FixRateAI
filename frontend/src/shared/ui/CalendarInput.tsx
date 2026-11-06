import { useId, useLayoutEffect, useRef, useState, type InputHTMLAttributes } from "react";
import { calendarValueIssue, DateTimeField, type CalendarMode } from "./DateTimeField";

/** Adapt existing controlled form inputs without changing their local/date-only API values. */
export function CalendarInput({ type = "date", value, defaultValue, onChange, id, className = "", disabled, readOnly, required, min, max, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const proxy = useRef<HTMLInputElement>(null);
  const root = useRef<HTMLSpanElement>(null);
  const [internal, setInternal] = useState(String(defaultValue ?? ""));
  const [validationError,setValidationError] = useState("");
  const [caption,setCaption] = useState("");
  const current = value === undefined ? internal : String(value ?? "");
  const mode = type as CalendarMode;
  const minimum = min === undefined ? undefined : String(min);
  const maximum = max === undefined ? undefined : String(max);
  const label = props["aria-label"] ?? (caption || (mode === "time" ? "Выбор времени" : mode === "month" ? "Выбор месяца" : "Выбор даты"));
  useLayoutEffect(() => {
    if(props["aria-label"])return;
    const outer = root.current?.closest("label") ?? root.current?.querySelector("button")?.labels?.[0];
    if(!outer)return;
    const clone=outer.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("[data-calendar-input]").forEach(node=>node.remove());
    setCaption(clone.textContent?.trim()??"");
  },[props["aria-label"]]);
  useLayoutEffect(() => { proxy.current?.setCustomValidity(calendarValueIssue(mode, current, minimum, maximum, required)); setValidationError(""); }, [mode, current, minimum, maximum, required]);
  return <span ref={root} className={`fr-calendar-input ${className}`} data-calendar-input>
    <DateTimeField label={label} fieldId={inputId} value={current} mode={mode} min={minimum} max={maximum} required={required} disabled={disabled || readOnly} hideLabel
      description={mode === "datetime-local" ? "Дата и время используются в часовом поясе, указанном в форме." : undefined}
      triggerProps={{ "aria-label": label, "aria-describedby": [props["aria-describedby"],validationError?`${inputId}-error`:null].filter(Boolean).join(" ")||undefined, "aria-invalid": props["aria-invalid"]||!!validationError||undefined, title: props.title }}
      onChange={next => {
        const field = proxy.current;
        if (!field || field.matches(":disabled") || readOnly) return;
        // Use the native value setter so React emits the same real change event as a text input.
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, next);
        field.dispatchEvent(new Event("input", { bubbles: true }));
      }} />
    <input {...props} id={`${inputId}-value`} ref={proxy} type="text" value={current} required={required} disabled={disabled} readOnly={readOnly} className="sr-only fr-calendar-validation" tabIndex={-1} aria-hidden="true" aria-label={undefined} data-field-label={label}
      onFocus={() => root.current?.querySelector("button")?.focus()}
      onInvalid={event => { event.preventDefault(); props.onInvalid?.(event); setValidationError(event.currentTarget.validationMessage); }}
      onChange={event => { if (value === undefined) setInternal(event.target.value); onChange?.(event); }} />
    {validationError && <span id={`${inputId}-error`} role="alert" className="fr-datetime-error">{validationError}</span>}
  </span>;
}
