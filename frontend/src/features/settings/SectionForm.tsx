import { useRef, type ReactNode } from "react";
import { Button } from "@/shared/ui/Button";
import "./settings-workspace.css";

export type FieldError = { field: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement; label: string; message: string };

export function sectionErrors(form: HTMLFormElement): FieldError[] {
  return Array.from(form.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input,select,textarea"))
    .filter(field => !field.matches(":disabled") && !field.validity.valid)
    .map(field => ({ field, label: field.getAttribute("aria-label") || field.labels?.[0]?.textContent?.trim() || "Поле формы", message: field.validationMessage }));
}

export function revealField(field: HTMLElement) {
  let parent = field.parentElement;
  while (parent) {
    if (parent instanceof HTMLDetailsElement) parent.open = true;
    parent = parent.parentElement;
  }
  field.focus();
  field.scrollIntoView?.({ block: "center", behavior: "auto" });
}

export function FormErrors({ errors }: { errors: FieldError[] }) {
  if (!errors.length) return null;
  return <div role="alert" className="fr-form-errors"><p>Проверьте обязательные поля: {errors.length}</p><ul>{errors.map((error, index) => <li key={index}><Button type="button" variant="ghost" onClick={() => revealField(error.field)}>{error.label}: {error.message}</Button></li>)}</ul></div>;
}

export function RuleSection({ title, summary, children, open = false, errors = [] }: { title: string; summary: string; children: ReactNode; open?: boolean; errors?: FieldError[] }) {
  const ref = useRef<HTMLDetailsElement>(null);
  const count = errors.filter(error => ref.current?.contains(error.field)).length;
  return <details ref={ref} className="fr-rule-section" open={open || undefined}>
    <summary><span>{title}</span><small>{summary}</small>{count > 0 && <strong className="fr-section-error-count">Ошибок: {count}</strong>}</summary>
    <div className="fr-rule-fields">{children}</div>
  </details>;
}
