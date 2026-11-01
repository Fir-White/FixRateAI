import { useRef } from "react";
import { useAuroraMotion } from "./useAuroraMotion";
import logoMark from "@/assets/fixrate-mark.svg";

export function AuroraScene() {
  const sceneRef = useRef<HTMLDivElement>(null);
  useAuroraMotion(sceneRef);

  return (
    <div className="auth-aurora" ref={sceneRef} aria-hidden="true">
      <div className="auth-aurora__light auth-aurora__light--far" />
      <div className="auth-aurora__light auth-aurora__light--upper" />
      <div className="auth-aurora__light auth-aurora__light--main" />
      <div className="auth-aurora__light auth-aurora__light--cursor" />
      <div className="auth-aurora__grid" />
      <div className="auth-aurora__brand">
        <div className="auth-aurora__logo-motion">
          <img src={logoMark} alt="" width="360" height="360" draggable={false} />
        </div>
      </div>
      <div className="auth-aurora__vignette" />
    </div>
  );
}
