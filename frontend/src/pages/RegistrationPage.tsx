import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { managementApi } from "@/shared/api/management";
import { FormField, Input } from "@/shared/ui/Form";
import { Button } from "@/shared/ui/Button";
import { AuthPasswordInput } from "@/features/auth/AuthPasswordInput";
import { describeAuthFailure, focusAuthError, type AuthErrors } from "@/features/auth/authValidation";
import { useAuthValidation } from "@/features/auth/useAuthValidation";

export function RegistrationPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const [serverFocus, setServerFocus] = useState<AuthErrors | null>(null);
  const validation = useAuthValidation("register", { full_name: name, email, password, password_confirmation: confirmation, company_code: code });
  useEffect(() => {
    if (!busy && serverFocus && formRef.current) {
      focusAuthError(formRef.current, serverFocus);
      setServerFocus(null);
    }
  }, [busy, serverFocus]);

  return (
    <>
      <header className="auth-heading">
        <h1 id="register-title">Регистрация</h1>
        <p>После регистрации администратор выдаст вам роль и доступ к объекту</p>
      </header>

      {done ? (
        <div className="auth-success" role="status">{done}</div>
      ) : (
        <form ref={formRef} noValidate className="auth-form auth-form--registration" aria-label="Регистрация сотрудника" aria-busy={busy} aria-describedby={error ? "register-error" : undefined} onSubmit={async event => {
          event.preventDefault();
          if (busy) return;
          setError("");
          if (!validation.validate(event.currentTarget)) return;
          setBusy(true);
          try {
            const result = await managementApi.register({ full_name: name, email, password, company_code: code });
            setPassword("");
            setConfirmation("");
            setDone(result.message);
          } catch (failure) {
            const result = describeAuthFailure(failure, "register");
            setError(result.message ?? "");
            validation.server(result.fields);
            if (result.fields) setServerFocus(result.fields);
          } finally {
            setBusy(false);
          }
        }}>
          <fieldset disabled={busy}>
            <FormField label="Имя и фамилия" htmlFor="register-name" className="auth-field" error={validation.errors.full_name}>
              <Input id="register-name" name="full_name" className="auth-input" required autoComplete="name" placeholder="Как к вам обращаться" value={name} onBlur={() => validation.blur("full_name")} onChange={e => { setName(e.target.value); validation.change("full_name"); setError(""); }} />
            </FormField>
            <FormField label="Email" htmlFor="register-email" className="auth-field" error={validation.errors.email}>
              <Input id="register-email" name="email" className="auth-input" type="email" required autoComplete="email" autoCapitalize="none" spellCheck={false} placeholder="name@company.ru" value={email} onBlur={() => validation.blur("email")} onChange={e => { setEmail(e.target.value); validation.change("email"); setError(""); }} />
            </FormField>
            <FormField label="Пароль" htmlFor="register-password" className="auth-field" hint="От 12 символов" error={validation.errors.password}>
              <AuthPasswordInput id="register-password" name="password" className="auth-input" required minLength={12} maxLength={128} autoComplete="new-password" placeholder="Придумайте пароль" value={password} onBlur={() => validation.blur("password")} onChange={e => { setPassword(e.target.value); validation.change("password"); setError(""); }} />
            </FormField>
            <FormField label="Подтвердите пароль" htmlFor="register-password-confirmation" className="auth-field" error={validation.errors.password_confirmation}>
              <AuthPasswordInput id="register-password-confirmation" name="password_confirmation" className="auth-input" visibilityLabel="подтверждение пароля" required maxLength={128} autoComplete="new-password" placeholder="Повторите пароль" value={confirmation} onBlur={() => validation.blur("password_confirmation")} onChange={e => { setConfirmation(e.target.value); validation.change("password_confirmation"); setError(""); }} />
            </FormField>
            <FormField label="Код компании" htmlFor="register-code" className="auth-field" hint="Код компании выдаёт администратор" error={validation.errors.company_code}>
              <Input id="register-code" name="company_code" className="auth-input" required minLength={16} autoComplete="off" placeholder="Введите код компании" value={code} onBlur={() => validation.blur("company_code")} onChange={e => { setCode(e.target.value); validation.change("company_code"); setError(""); }} />
            </FormField>
            {error && <p id="register-error" role="alert" className="auth-error">{error}</p>}
            <Button className="auth-submit" type="submit" disabled={busy}>{busy ? "Регистрация…" : "Зарегистрироваться"}</Button>
          </fieldset>
        </form>
      )}
      <p className="auth-register">Уже есть аккаунт? <Link to="/login">Перейти ко входу</Link></p>
    </>
  );
}
