import { useState, type InputHTMLAttributes } from "react";
import { IconButton } from "@/shared/ui/Button";
import { Input } from "@/shared/ui/Form";

export function AuthPasswordInput({
  id,
  visibilityLabel = "пароль",
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { id: string; visibilityLabel?: string }) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="auth-password">
      <Input {...props} id={id} type={visible ? "text" : "password"} />
      <IconButton variant="ghost" className="auth-password__toggle" label={`${visible ? "Скрыть" : "Показать"} ${visibilityLabel}`} aria-controls={id} aria-pressed={visible} onClick={() => setVisible(value => !value)}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {visible ? <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>
            : <><path d="m3 3 18 18M10.6 5.1A12 12 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.1 4.1M6.3 6.3A19 19 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.7-1.7M10 10a3 3 0 0 0 4 4" /></>}
        </svg>
      </IconButton>
    </div>
  );
}
