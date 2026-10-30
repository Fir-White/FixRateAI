import type { ReactNode } from "react";
import { Icon, type IconName } from "@/shared/ui/Icon";

export type CalloutTone =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "violet";

const TONE_CLASSES: Record<CalloutTone, string> = {
  neutral: "border-line bg-white/[0.025] text-ink-soft",
  info: "border-sky-400/25 bg-sky-400/[0.07] text-sky-100",
  success: "border-accent/25 bg-accent/[0.07] text-accent",
  warning: "border-amber-300/25 bg-amber-300/[0.07] text-amber-200",
  danger: "border-rose-400/25 bg-rose-400/[0.06] text-rose-100",
  violet: "border-violet-400/25 bg-violet-400/[0.07] text-violet-100",
};

const TONE_ICONS: Record<CalloutTone, IconName> = {
  neutral: "alert",
  info: "alert",
  success: "check",
  warning: "alert",
  danger: "alert",
  violet: "camera",
};

export function Callout({
  tone = "neutral",
  title,
  children,
  icon,
  className = "",
}: {
  tone?: CalloutTone;
  title?: string;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border px-4 py-3.5 text-sm leading-6 ${TONE_CLASSES[tone]} ${className}`}
    >
      <div className="flex gap-3">
        <span className="mt-0.5 shrink-0 opacity-80">
          {icon ?? <Icon name={TONE_ICONS[tone]} size={17} />}
        </span>
        <div className="min-w-0">
          {title ? (
            <p className="font-semibold text-current">{title}</p>
          ) : null}
          <div className={title ? "mt-1" : ""}>{children}</div>
        </div>
      </div>
    </div>
  );
}
