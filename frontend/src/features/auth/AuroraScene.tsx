import { useId, useRef } from "react";
import { useAuroraMotion } from "./useAuroraMotion";
import { FLOW_HEIGHT, FLOW_WIDTH, ribbonPath } from "./ribbonGeometry";
import logoMark from "@/assets/fixrate-mark.svg";

const RIBBONS = [0, 1, 2];
const PARTICLES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
const LAYERS = [
  { name: "outer", blur: 28, widths: [156, 220, 300], opacity: [0.19, 0.15, 0.09] },
  { name: "inner", blur: 11, widths: [48, 84, 140], opacity: [0.42, 0.25, 0.1] },
  { name: "core", blur: 3, widths: [9, 16, 38], opacity: [0.72, 0.3, 0.07] },
];

export function AuroraScene({ animationEnabled = true, onReducedMotionChange }: { animationEnabled?: boolean; onReducedMotionChange?: (reduced: boolean) => void }) {
  const sceneRef = useRef<HTMLDivElement>(null);
  const prefix = useId().replace(/:/g, "");
  useAuroraMotion(sceneRef, animationEnabled, onReducedMotionChange);

  return (
    <div className="auth-aurora" ref={sceneRef} aria-hidden="true">
      {RIBBONS.map(index => <div key={index} className={index < 2 ? `auth-light-motion auth-light-motion--${index}` : "auth-light-static"}>
        <Ribbon index={index} prefix={`${prefix}-${index}`} />
      </div>)}
      {PARTICLES.map(index => <div key={index} className={`auth-particle auth-particle--${index}`} aria-hidden="true" />)}
      <div className="auth-aurora__vignette" />
      <div className="auth-aurora__scrim" />
      <div className="auth-aurora__brand">
        <div className="auth-aurora__logo">
          <img src={logoMark} alt="" width="360" height="360" draggable={false} />
        </div>
      </div>
    </div>
  );
}

function Ribbon({ index, prefix }: { index: number; prefix: string }) {
  return <svg className="auth-ribbons" viewBox={`0 0 ${FLOW_WIDTH} ${FLOW_HEIGHT}`} preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <path id={`${prefix}-ribbon`} data-aurora-ribbon={index} d={ribbonPath(index, 0)} />
      {LAYERS.map(layer => <filter key={layer.name} id={`${prefix}-${layer.name}`} filterUnits="userSpaceOnUse" x="-160" y="-160" width="1520" height="1320" colorInterpolationFilters="sRGB">
        <feGaussianBlur stdDeviation={layer.blur} />
      </filter>)}
      {index === 0 ? <linearGradient id={`${prefix}-color`} gradientUnits="userSpaceOnUse" x1="0" y1="1000" x2="860" y2="0">
        <stop stopColor="var(--aurora-primary)" stopOpacity="0" />
        <stop offset="0.2" stopColor="var(--aurora-primary)" stopOpacity="0.65" />
        <stop offset="0.48" stopColor="var(--aurora-primary)" />
        <stop offset="0.68" stopColor="#b6fffa" />
        <stop offset="0.9" stopColor="var(--aurora-primary)" stopOpacity="0.65" />
        <stop offset="1" stopColor="var(--aurora-primary)" stopOpacity="0.1" />
      </linearGradient> : index === 1 ? <linearGradient id={`${prefix}-color`} gradientUnits="userSpaceOnUse" x1="380" y1="1100" x2="1200" y2="470">
        <stop stopColor="var(--aurora-secondary)" stopOpacity="0" />
        <stop offset="0.35" stopColor="var(--aurora-secondary)" />
        <stop offset="0.7" stopColor="#46c4cf" />
        <stop offset="1" stopColor="var(--aurora-secondary)" stopOpacity="0.25" />
      </linearGradient> : <linearGradient id={`${prefix}-color`} gradientUnits="userSpaceOnUse" x1="0" y1="540" x2="1200" y2="100">
        <stop stopColor="var(--aurora-ambient)" stopOpacity="0" />
        <stop offset="0.5" stopColor="var(--aurora-ambient)" />
        <stop offset="1" stopColor="var(--aurora-ambient)" stopOpacity="0.2" />
      </linearGradient>}
    </defs>
    {LAYERS.map(layer => <g key={layer.name} filter={`url(#${prefix}-${layer.name})`} className={`auth-ribbons__${layer.name}`} strokeLinecap="round">
      <use href={`#${prefix}-ribbon`} stroke={`url(#${prefix}-color)`} strokeWidth={layer.widths[index]} opacity={layer.opacity[index]} />
    </g>)}
  </svg>;
}
