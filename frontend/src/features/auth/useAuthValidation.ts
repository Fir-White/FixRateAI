import { useState } from "react";
import { focusAuthError, validateAuth, validateAuthField, type AuthErrors, type AuthField, type AuthMode, type AuthValues } from "./authValidation";

export function useAuthValidation(mode: AuthMode, values: AuthValues) {
  const [revealed, setRevealed] = useState<Partial<Record<AuthField, boolean>>>({});
  const [serverErrors, setServerErrors] = useState<AuthErrors>({});
  const errors: AuthErrors = { ...serverErrors };
  for (const field of Object.keys(values) as AuthField[]) {
    if (revealed[field]) {
      const error = validateAuthField(field, values, mode);
      if (error) errors[field] = error;
    }
  }
  return {
    errors,
    blur: (field: AuthField) => setRevealed(previous => ({ ...previous, [field]: true })),
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
