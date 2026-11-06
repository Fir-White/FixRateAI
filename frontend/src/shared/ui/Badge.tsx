import type { ReactNode } from "react";

export type BadgeTone =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "violet";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "border-line-strong bg-white/[0.045] text-ink-soft",
  info: "border-sky-400/25 bg-sky-400/10 text-sky-200",
  success: "border-accent/25 bg-accent/10 text-accent",
  warning: "border-amber-300/25 bg-amber-300/10 text-amber-200",
  danger: "border-rose-400/25 bg-rose-400/10 text-rose-200",
  violet: "border-violet-400/25 bg-violet-400/10 text-violet-200",
};

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return (
    <span
      data-content-tone={tone}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold whitespace-nowrap ${TONE_CLASSES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
