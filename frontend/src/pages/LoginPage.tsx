import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { DEMO_MODE } from "@/shared/api/request";
import { ROLE_DESCRIPTIONS, ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import type { Role } from "@/shared/types/domain";
import { Button } from "@/shared/ui/Button";
import { FormField, Input } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { AuthPasswordInput } from "@/features/auth/AuthPasswordInput";
import { describeAuthFailure, focusAuthError, type AuthErrors } from "@/features/auth/authValidation";
import { useAuthValidation } from "@/features/auth/useAuthValidation";

const ROLES: Role[] = ["dispatcher", "engineer", "executor", "admin"];

export function LoginPage() {
  const { profile, login, signIn, loading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [siteId, setSiteId] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [needsSite, setNeedsSite] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const [serverFocus, setServerFocus] = useState<AuthErrors | null>(null);
  const validation = useAuthValidation("login", { email, password, ...(needsSite ? { site_id: siteId } : {}) });
  useEffect(() => {
    if (!pending && serverFocus && formRef.current) {
      focusAuthError(formRef.current, serverFocus);
      setServerFocus(null);
    }
  }, [pending, serverFocus]);
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from;
  const destination = (role: Role) =>
    typeof from === "string" && from.startsWith("/") && !from.startsWith("//") && from.split(/[?#]/)[0] !== "/login"
      ? from : homePathForRole(role);

  if (profile) return <Navigate to={destination(profile.role)} replace />;

  return (
    <>
    <header className="auth-heading">
      {DEMO_MODE && <p className="auth-eyebrow">Демонстрационный вход</p>}
      <h1 id="login-title">{DEMO_MODE ? "Выберите роль" : "Вход в систему"}</h1>
      <p>{DEMO_MODE ? "Посмотрите, как устроено рабочее пространство каждой роли." : "Введите рабочую почту и пароль"}</p>
    </header>

    {loading ? <p role="status" className="auth-session-loading">Загрузка сессии…</p> : DEMO_MODE ? (
      <div className="auth-demo">
        {ROLES.map(role => (
          <Button key={role} variant="secondary" className="auth-demo__role" onClick={() => {
            login(role);
            navigate(destination(role), { replace: true });
          }}>
            <span><strong>{ROLE_LABELS[role]}</strong><span>{ROLE_DESCRIPTIONS[role]}</span></span>
            <Icon name="chevron" size={17} />
          </Button>
        ))}
        <p className="auth-demo__note">Демонстрация на учебных данных. Выбранная роль действует только в этом режиме.</p>
      </div>
    ) : (
      <>
        <form ref={formRef} noValidate className="auth-form" aria-label="Вход в систему" aria-busy={pending} aria-describedby={error ? "login-error" : undefined} onSubmit={async event => {
          event.preventDefault();
          if (pending) return;
          setError("");
          if (!validation.validate(event.currentTarget)) return;
          setPending(true);
          try {
            const user = await signIn(email.trim(), password, siteId.trim());
            navigate(destination(user.role), { replace: true });
          } catch (failure) {
            const result = describeAuthFailure(failure, "login");
            setError(result.message ?? "");
            validation.server(result.fields);
            if (result.requiresSite || result.fields?.site_id) setNeedsSite(true);
            if (result.fields) setServerFocus(result.fields);
          } finally { setPending(false); }
        }}>
          <fieldset disabled={pending}>
            <FormField label="Email" htmlFor="login-email" className="auth-field" error={validation.errors.email}>
              <Input id="login-email" name="email" className="auth-input" type="email" required autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder="name@company.ru" value={email} onBlur={() => validation.blur("email")} onChange={e => { setEmail(e.target.value); validation.change("email"); setError(""); }} />
            </FormField>
            <FormField label="Пароль" htmlFor="login-password" className="auth-field" error={validation.errors.password}>
              <AuthPasswordInput id="login-password" name="password" className="auth-input" required autoComplete="current-password" placeholder="Введите пароль" value={password} onBlur={() => validation.blur("password")} onChange={e => { setPassword(e.target.value); validation.change("password"); setError(""); }} />
            </FormField>

            {needsSite && <FormField label="ID объекта" htmlFor="login-site" className="auth-field" error={validation.errors.site_id}>
                <Input id="login-site" name="site_id" className="auth-input" autoComplete="off" placeholder="UUID объекта" required={needsSite} value={siteId} onBlur={() => validation.blur("site_id")} onChange={e => { setSiteId(e.target.value); validation.change("site_id"); setError(""); }} />
              </FormField>}
            {error && <p id="login-error" role="alert" className="auth-error">{error}</p>}
            <Button className="auth-submit" type="submit" disabled={pending}>
              {pending ? <><span className="auth-spinner" aria-hidden="true" />Входим…</> : "Войти"}
            </Button>
          </fieldset>
        </form>
        <p className="auth-register">Новый сотрудник? <Link to="/register">Регистрация</Link></p>
      </>
    )}
    </>
  );
}
