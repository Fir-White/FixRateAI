import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigationType, useOutlet } from "react-router-dom";
import { AuroraScene } from "@/features/auth/AuroraScene";
import { Modal } from "@/shared/ui/Modal";
import logoMark from "@/assets/fixrate-mark.svg";
import logoWordmark from "@/assets/fixrate-wordmark.svg";
import "./LoginPage.css";
import { AuthMotionContext } from "@/features/auth/AuthMotionContext";
import { useAuthTransition } from "@/features/auth/useAuthTransition";
import { useInitialReveal } from "@/features/auth/useInitialReveal";

/** Shared public-auth shell stays mounted while moving between entry and registration. */
export function AuthLayout() {
  const { pathname, key } = useLocation();
  const outlet = useOutlet();
  const navigationType = useNavigationType();
  const mainRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const transition = useAuthTransition(pathname, outlet, contentRef, mainRef, key, navigationType);
  const registration = /^\/register\/?$/.test(transition.view.pathname);
  const initial = useInitialReveal(mainRef);
  const [showHelp, setShowHelp] = useState(false);
  const [backgroundAnimation, setBackgroundAnimation] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => { setShowHelp(false); }, [pathname]);

  return (
    <AuthMotionContext.Provider value={{ leaveAfterSuccess: transition.leaveAfterSuccess }}>
    <main ref={mainRef} tabIndex={-1} data-reveal={initial.revealing ? "initial" : undefined} data-transition={transition.phase} className={`auth-page${registration ? " auth-page--registration" : ""}`} onPointerDownCapture={initial.press} onFocusCapture={initial.focus}>
      <section className="auth-panel" aria-labelledby={registration ? "register-title" : "login-title"}>
        <div className="auth-brand">
          <img src={logoMark} className="auth-brand__mark" alt="" width="44" height="44" />
          <img src={logoWordmark} className="auth-brand__wordmark" alt="FixRate AI" width="157" height="24" />
        </div>
        <div ref={contentRef} className="auth-panel__content" inert={transition.phase === "exit" || transition.phase === "success"} aria-hidden={transition.phase === "exit" || transition.phase === "success" ? true : undefined}>
        <div className="auth-panel__body">{transition.view.outlet}</div>
        <footer className="auth-footer">
          <p>{registration ? "Нужна помощь с регистрацией?" : "Проблемы со входом?"}</p>
          <button type="button" onClick={() => setShowHelp(true)}>Обратитесь к администратору <span aria-hidden="true">↗</span></button>
        </footer>
        </div>
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
    </AuthMotionContext.Provider>
  );
}
