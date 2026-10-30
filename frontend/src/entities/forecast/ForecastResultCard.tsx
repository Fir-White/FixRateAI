import type { ForecastResult } from "@/shared/types/domain";
import { formatDate } from "@/shared/lib/format";
import { Card } from "@/shared/ui/Card";
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
      ? "border-l-sky-500"
      : "border-l-violet-500";

  return (
    <Card className={`border-l-4 ${accentClasses} p-5`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold tracking-[0.14em] text-slate-500 uppercase">
            {accent === "algorithmic" ? "Алгоритмический" : "AI-прогноз"}
          </p>
          <p className="mt-1 text-sm font-semibold text-slate-900">
            {result.methodVersion}
          </p>
          {result.modelRef ? (
            <p className="mt-1 font-mono text-xs break-all text-slate-500">
              {result.modelRef}
            </p>
          ) : null}
        </div>
        <ForecastStatusBadge status={result.status} />
      </div>

      <div className="mt-5 rounded-xl bg-slate-50 p-4">
        <p className="text-xs font-semibold text-slate-500">
          Рекомендованная дата
        </p>
        <p
          className={`mt-1 text-2xl font-black ${
            unavailable ? "text-slate-400" : "text-slate-950"
          }`}
        >
          {unavailable ? "Нет даты" : formatDate(result.recommendedDate)}
        </p>
        {result.errorCode ? (
          <p className="mt-1 font-mono text-xs text-rose-700">
            {result.errorCode}
          </p>
        ) : null}
      </div>

      <p className="mt-4 text-sm leading-6 text-slate-600">
        {result.explanation}
      </p>

      <div className="mt-4 space-y-2 border-t border-slate-100 pt-4 text-xs text-slate-500">
        <p>
          <span className="font-semibold text-slate-700">Неопределённость:</span>{" "}
          {result.uncertaintyNote}
        </p>
        <p>
          <span className="font-semibold text-slate-700">Время расчёта:</span>{" "}
          {result.elapsedMs} мс
        </p>
      </div>

      {result.warnings.length ? (
        <ul className="mt-4 space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
