import { useRef, useState } from "react";
import { useLocation, useNavigationType, useOutlet } from "react-router-dom";
import { AuroraScene } from "@/features/auth/AuroraScene";
import { AuthHeroCopy } from "@/features/auth/AuthHeroCopy";
import { AccessBrand } from "@/shared/ui/Brand";
import "./LoginPage.css";
import { AuthMotionContext } from "@/features/auth/AuthMotionContext";
import { useAuthTransition } from "@/features/auth/useAuthTransition";
import { useInitialReveal } from "@/features/auth/useInitialReveal";
import { useMobileAuthViewport } from "@/features/auth/useMobileAuthViewport";

/** Shared public-auth shell stays mounted while moving between entry and registration. */
export function AuthLayout() {
  const { pathname, key } = useLocation();
  const outlet = useOutlet();
  const navigationType = useNavigationType();
  useMobileAuthViewport(navigationType);
  const mainRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const transition = useAuthTransition(pathname, outlet, contentRef, mainRef, key, navigationType);
  const registration = /^\/register\/?$/.test(transition.view.pathname);
  const setup = /^\/setup\/?$/.test(transition.view.pathname);
  const initial = useInitialReveal(mainRef);
  const [reducedMotion, setReducedMotion] = useState(false);

  return (
    <AuthMotionContext.Provider value={{ leaveAfterSuccess: transition.leaveAfterSuccess }}>
    <main ref={mainRef} tabIndex={-1} data-reveal={initial.revealing ? "initial" : undefined} data-transition={transition.phase} className={`auth-page${registration || setup ? " auth-page--compact" : ""}`} onPointerDownCapture={initial.press} onFocusCapture={initial.focus}>
      <section className="auth-panel" aria-labelledby={setup ? "setup-title" : registration ? "register-title" : "login-title"}>
        <AccessBrand />
        <div ref={contentRef} className="auth-panel__content" inert={transition.phase === "exit" || transition.phase === "success"} aria-hidden={transition.phase === "exit" || transition.phase === "success" ? true : undefined}>
        <div className="auth-panel__body">{transition.view.outlet}</div>
        <footer className="auth-footer">
          <p>{setup ? "Нужна помощь с настройкой?" : registration ? "Нужна помощь с регистрацией?" : "Не получается войти?"}</p>
          <p>{registration ? "Обратитесь к администратору вашего объекта." : "Обратитесь к администратору вашего объекта для восстановления доступа."}</p>
        </footer>
        </div>
      </section>

      <div className="auth-visual">
        <AuroraScene onReducedMotionChange={setReducedMotion} />
        <AuthHeroCopy reducedMotion={reducedMotion} />
      </div>

    </main>
    </AuthMotionContext.Provider>
  );
}
