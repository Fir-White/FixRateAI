import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuroraScene } from "@/features/auth/AuroraScene";
import { DEMO_MODE } from "@/shared/api/request";
import { ROLE_DESCRIPTIONS, ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import type { Role } from "@/shared/types/domain";
import { Button, IconButton } from "@/shared/ui/Button";
import { FormField, Input } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { Modal } from "@/shared/ui/Modal";
import logoMark from "@/assets/fixrate-mark.svg";
import logoWordmark from "@/assets/fixrate-wordmark.svg";
import "./LoginPage.css";

const ROLES: Role[] = ["dispatcher", "engineer", "executor", "admin"];

export function LoginPage() {
  const { profile, login, signIn, loading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [siteId, setSiteId] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [needsSite, setNeedsSite] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from;
  const destination = (role: Role) =>
    typeof from === "string" && from.startsWith("/") && !from.startsWith("//") && from.split(/[?#]/)[0] !== "/login"
      ? from : homePathForRole(role);

  if (profile) return <Navigate to={destination(profile.role)} replace />;

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="login-title">
        <div className="auth-brand">
          <img src={logoMark} className="auth-brand__mark" alt="" width="44" height="44" />
          <img src={logoWordmark} className="auth-brand__wordmark" alt="FixRate AI" width="157" height="24" />
        </div>

        <div className="auth-panel__body">
          <header className="auth-heading">
            {DEMO_MODE && <p className="auth-eyebrow">Демонстрационный вход</p>}
            <h1 id="login-title">{DEMO_MODE ? "Выберите роль" : "С возвращением"}</h1>
            <p>{DEMO_MODE ? "Посмотрите, как устроено рабочее пространство каждой роли." : "Войдите в рабочее пространство FixRate AI"}</p>
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
              <form className="auth-form" aria-label="Вход в систему" aria-busy={pending} aria-describedby={error ? "login-error" : undefined} onSubmit={async event => {
                event.preventDefault();
                if (pending) return;
                setPending(true);
                setError("");
                try {
                  const user = await signIn(email.trim(), password, siteId.trim());
                  navigate(destination(user.role), { replace: true });
                } catch (failure) {
                  const message = failure instanceof Error ? failure.message : "Ошибка входа";
                  setError(message);
                  if (message.includes("site_id") || message.includes("несколько объектов")) setNeedsSite(true);
                } finally { setPending(false); }
              }}>
                <fieldset disabled={pending}>
                  <FormField label="Email" htmlFor="login-email" className="auth-field">
                    <Input id="login-email" name="email" className="auth-input" type="email" required autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder="name@company.ru" value={email} onChange={e => setEmail(e.target.value)} />
                  </FormField>
                  <FormField label="Пароль" htmlFor="login-password" className="auth-field">
                    <div className="auth-password">
                      <Input id="login-password" name="password" className="auth-input" type={showPassword ? "text" : "password"} required autoComplete="current-password" placeholder="Введите пароль" value={password} onChange={e => setPassword(e.target.value)} />
                      <IconButton variant="ghost" className="auth-password__toggle" label={showPassword ? "Скрыть пароль" : "Показать пароль"} aria-controls="login-password" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>
                        <PasswordEye visible={showPassword} />
                      </IconButton>
                    </div>
                  </FormField>

                  <details className="auth-site" open={needsSite || undefined}>
                    <summary>Доступ к нескольким объектам</summary>
                    <FormField label="ID объекта" htmlFor="login-site">
                      <Input id="login-site" name="site_id" className="auth-input" autoComplete="off" placeholder="UUID объекта" required={needsSite} value={siteId} onChange={e => setSiteId(e.target.value)} />
                    </FormField>
                  </details>
                  {error && <p id="login-error" role="alert" className="auth-error">{error}</p>}
                  <Button className="auth-submit" type="submit" disabled={pending}>
                    {pending ? <><span className="auth-spinner" aria-hidden="true" />Входим…</> : "Войти"}
                  </Button>
                </fieldset>
              </form>
              <p className="auth-register">Новый сотрудник? <Link to="/register">Регистрация</Link></p>
            </>
          )}
        </div>

        <footer className="auth-footer">
          <p>Проблемы со входом?</p>
          <button type="button" onClick={() => setShowHelp(true)}>Обратитесь к администратору <span aria-hidden="true">↗</span></button>
        </footer>
      </section>

      <AuroraScene />

      <Modal open={showHelp} title="Помощь со входом" onClose={() => setShowHelp(false)}>
        <div className="space-y-4 text-sm leading-7 text-ink-soft">
          <p>По вопросам учётной записи, пароля и доступа обратитесь к администратору вашего объекта. Он проверит вашу регистрацию, назначенную роль и доступ к системе.</p>
          <p>Для входа используйте рабочую электронную почту. Самостоятельный сброс пароля пока недоступен. Новому сотруднику потребуется код компании от администратора.</p>
          <Link className="text-accent underline underline-offset-4" to="/register">Регистрация сотрудника</Link>
        </div>
      </Modal>
    </main>
  );
}

function PasswordEye({ visible }: { visible: boolean }) {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {visible ? <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>
        : <><path d="m3 3 18 18M10.6 5.1A12 12 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.1 4.1M6.3 6.3A19 19 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.7-1.7M10 10a3 3 0 0 0 4 4" /></>}
    </svg>
  );
}
