import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useMatch } from "react-router-dom";
import { AuroraScene } from "@/features/auth/AuroraScene";
import { Modal } from "@/shared/ui/Modal";
import logoMark from "@/assets/fixrate-mark.svg";
import logoWordmark from "@/assets/fixrate-wordmark.svg";
import "./LoginPage.css";

/** Shared public-auth shell stays mounted while moving between entry and registration. */
export function AuthLayout() {
  const { pathname } = useLocation();
  const registration = !!useMatch({ path: "/register", end: true });
  const [showHelp, setShowHelp] = useState(false);
  const [backgroundAnimation, setBackgroundAnimation] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => { setShowHelp(false); }, [pathname]);

  return (
    <main className={`auth-page${registration ? " auth-page--registration" : ""}`}>
      <section className="auth-panel" aria-labelledby={registration ? "register-title" : "login-title"}>
        <div className="auth-brand">
          <img src={logoMark} className="auth-brand__mark" alt="" width="44" height="44" />
          <img src={logoWordmark} className="auth-brand__wordmark" alt="FixRate AI" width="157" height="24" />
        </div>
        <div className="auth-panel__body"><Outlet /></div>
        <footer className="auth-footer">
          <p>{registration ? "Нужна помощь с регистрацией?" : "Проблемы со входом?"}</p>
          <button type="button" onClick={() => setShowHelp(true)}>Обратитесь к администратору <span aria-hidden="true">↗</span></button>
        </footer>
      </section>

      <AuroraScene animationEnabled={backgroundAnimation} onReducedMotionChange={setReducedMotion} />

      <Modal open={showHelp} title={registration ? "Помощь с регистрацией" : "Помощь со входом"} onClose={() => setShowHelp(false)}>
        <div className="space-y-4 text-sm leading-7 text-ink-soft">
          <p>По вопросам учётной записи, пароля и доступа обратитесь к администратору вашего объекта. Он проверит вашу регистрацию, назначенную роль и доступ к системе.</p>
          <p>Для входа используйте рабочую электронную почту. Самостоятельный сброс пароля пока недоступен. Новому сотруднику потребуется код компании от администратора.</p>
          {!registration && <Link className="text-accent underline underline-offset-4" to="/register" onClick={() => setShowHelp(false)}>Регистрация сотрудника</Link>}
          <div className="auth-motion-setting">
            <label htmlFor="login-background-animation">
              <input id="login-background-animation" type="checkbox" checked={backgroundAnimation && !reducedMotion} disabled={reducedMotion} aria-describedby={reducedMotion ? "login-motion-note" : undefined} onChange={event => setBackgroundAnimation(event.target.checked)} />
              Анимация фона
            </label>
            {reducedMotion && <p id="login-motion-note">Анимация отключена системной настройкой уменьшения движения.</p>}
          </div>
        </div>
      </Modal>
    </main>
  );
}
