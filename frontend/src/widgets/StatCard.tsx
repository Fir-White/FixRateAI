import type { ReactNode } from "react";
import { Card } from "@/shared/ui/Card";

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  icon,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "danger" | "warning" | "success";
  icon?: ReactNode;
}) {
  const toneClasses = {
    default: "text-slate-950",
    danger: "text-rose-700",
    warning: "text-amber-700",
    success: "text-emerald-700",
  }[tone];

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-slate-500">{label}</p>
        {icon ? <span className="text-slate-400">{icon}</span> : null}
      </div>
      <p className={`mt-3 text-3xl font-black tracking-tight ${toneClasses}`}>
        {value}
      </p>
      {hint ? <p className="mt-2 text-xs text-slate-500">{hint}</p> : null}
    </Card>
  );
}
