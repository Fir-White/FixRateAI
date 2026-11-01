import type { ForecastResult } from "@/shared/types/domain";
import { formatDate } from "@/shared/lib/format";
import { Card } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";
import { ForecastStatusBadge } from "@/shared/ui/StatusBadge";

export function ForecastResultCard({
  result,
  accent,
}: {
  result: ForecastResult;
  accent: "algorithmic" | "ai";
}) {
  const unavailable = result.status !== "ok";
  const accentClasses =
    accent === "algorithmic"
      ? "border-l-sky-400/70"
      : "border-l-violet-400/70";

  return (
    <Card className={`border-l-4 ${accentClasses} p-5`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.14em] text-muted uppercase">
            {accent === "algorithmic" ? "Алгоритмический" : "AI-прогноз"}
          </p>
          <p className="mt-1 text-sm font-semibold text-ink">
            {result.methodVersion}
          </p>
          {result.modelRef ? (
            <p className="mt-1 font-mono text-xs break-all text-muted">
              {result.modelRef}
            </p>
          ) : null}
        </div>
        <ForecastStatusBadge status={result.status} />
      </div>

      <div className="mt-5 rounded-xl bg-white/[0.035] p-4">
        <p className="text-xs font-semibold text-muted">
          Рекомендованная дата
        </p>
        <p
          className={`mt-1 text-2xl font-semibold ${
            unavailable ? "text-muted/60" : "text-ink"
          }`}
        >
          {unavailable ? "Нет даты" : formatDate(result.recommendedDate)}
        </p>
        {result.errorCode ? (
          <p className="mt-1 font-mono text-xs text-rose-300">
            {result.errorCode}
          </p>
        ) : null}
      </div>

      <p className="mt-4 text-sm leading-6 text-ink-soft">
        {result.explanation}
      </p>

      <div className="mt-4 space-y-2 border-t border-line pt-4 text-xs text-muted">
        <p>
          <span className="font-semibold text-ink-soft">Неопределённость:</span>{" "}
          {result.uncertaintyNote}
        </p>
        <p>
          <span className="font-semibold text-ink-soft">Время расчёта:</span>{" "}
          {result.elapsedMs} мс
        </p>
      </div>

      {result.warnings.length ? (
        <Callout tone="warning" title="Предупреждения" className="mt-4 text-xs">
          <ul className="space-y-1">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Callout>
      ) : null}
    </Card>
  );
}
