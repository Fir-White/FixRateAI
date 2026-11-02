import { useEffect, useState } from "react";
import "./AuthHeroCopy.css";

/** Persistent secondary copy, independent of the decorative scene and auth forms. */
export function AuthHeroCopy({ reducedMotion = false }: { reducedMotion?: boolean }) {
  const [revealed, setRevealed] = useState(false);
  useEffect(() => { if (reducedMotion) setRevealed(true); }, [reducedMotion]);

  return (
    <section className="auth-hero-copy" aria-labelledby="auth-hero-title" data-revealed={revealed || undefined}>
      <div className="auth-hero-copy__content">
        <h2 id="auth-hero-title" onAnimationEnd={() => setRevealed(true)}>
          <span>Интеллектуальная</span>{" "}
          <span>система прогнозирования</span>{" "}
          <span className="auth-hero-copy__accent">ТО и ППР.</span>
        </h2>
        <span className="auth-hero-copy__line" aria-hidden="true" />
        <p>Планирование обслуживания, анализ состояния оборудования и контроль выполнения работ в единой системе.</p>
      </div>
    </section>
  );
}
