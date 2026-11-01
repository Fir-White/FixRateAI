import type { ReactNode } from "react";
import { Card } from "@/shared/ui/Card";

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  icon,
  compact = false,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "danger" | "warning" | "success";
  icon?: ReactNode;
  compact?: boolean;
}) {
  const toneClasses = {
    default: "text-ink",
    danger: "text-rose-300",
    warning: "text-amber-200",
    success: "text-accent",
  }[tone];

  return (
    <Card className={compact ? "p-4" : "p-5"}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold text-muted">{label}</p>
        {icon ? <span className="text-muted">{icon}</span> : null}
      </div>
      <p
        className={`${compact ? "mt-2 text-2xl" : "mt-3 text-3xl"} leading-none font-semibold tracking-[-0.04em] ${toneClasses}`}
      >
        {value}
      </p>
      {hint ? <p className="mt-3 text-xs leading-5 text-muted">{hint}</p> : null}
    </Card>
  );
}
