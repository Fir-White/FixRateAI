import { cloneElement, isValidElement, useId } from "react";
import { useFeedbackMotion } from "@/shared/motion/useFeedbackMotion";
import type {
  ComponentPropsWithoutRef,
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

const CONTROL_CLASSES =
  "motion-input w-full rounded-xl border border-line-strong bg-white/[0.035] text-sm text-ink placeholder:text-muted/60 transition-colors hover:border-muted/50 focus:border-accent focus:ring-2 focus:ring-accent/15 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50";

export function FormField({
  label,
  htmlFor,
  hint,
  error,
  required = false,
  children,
  className = "",
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  const generatedId = useId();
  const descriptionId = `${htmlFor ?? generatedId}-description`;
  const describedBy = error || hint ? descriptionId : undefined;
  const feedback = useFeedbackMotion(error || hint);
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        "aria-describedby": describedBy,
        ...(error ? { "aria-invalid": true } : {}),
      })
    : children;

  return (
    <div className={className}>
      <label
        htmlFor={htmlFor}
        className="mb-1.5 block text-xs font-semibold text-ink-soft"
      >
        {label}
        {required ? (
          <span aria-hidden="true" className="ml-1 text-rose-300">
            *
          </span>
        ) : null}
      </label>
      {control}
      <div ref={feedback} className="form-feedback">
      {error ? (
        <p
          id={descriptionId}
          role="alert"
          className="mt-1.5 text-xs leading-5 text-rose-300"
        >
          {error}
        </p>
      ) : hint ? (
        <p
          id={descriptionId}
          className="mt-1.5 text-xs leading-5 text-muted"
        >
          {hint}
        </p>
      ) : null}
      </div>
    </div>
  );
}

export function Input({
  leadingIcon,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  leadingIcon?: ReactNode;
}) {
  const input = (
    <input
      className={`${CONTROL_CLASSES} h-10 px-3 ${leadingIcon ? "pl-10" : ""} ${className}`}
      {...props}
    />
  );

  if (!leadingIcon) {
    return input;
  }

  return (
    <span className="relative block">
      <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted">
        {leadingIcon}
      </span>
      {input}
    </span>
  );
}

export function Select({
  className = "",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`${CONTROL_CLASSES} h-10 px-3 pr-9 ${className}`}
      {...props}
    />
  );
}

export function Textarea({
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`${CONTROL_CLASSES} min-h-24 resize-y px-3 py-2.5 ${className}`}
      {...props}
    />
  );
}

export function Checkbox({
  label,
  className = "",
  ...props
}: Omit<ComponentPropsWithoutRef<"input">, "type"> & { label: string }) {
  return (
    <label
      className={`inline-flex items-center gap-2.5 text-sm text-ink-soft ${className}`}
    >
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-line-strong bg-white/[0.04] accent-accent"
        {...props}
      />
      {label}
    </label>
  );
}
