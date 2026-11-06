import type { ForecastResult } from "@/shared/types/domain";
import { formatDate } from "@/shared/lib/format";
import { exceedsDeadline, forecastUnavailableLabel } from "@/shared/lib/forecastPresentation";
import { Callout } from "@/shared/ui/Callout";
import { ForecastStatusBadge } from "@/shared/ui/StatusBadge";

export function ForecastResultCard({ result, accent }: { result: ForecastResult; accent: "algorithmic" | "ai" }) {
  const hasDate = result.status === "ok" && !!result.recommendedDate;
  const late = exceedsDeadline(result.recommendedDate, result.mandatoryDueDate);
  return <section className={`forecast-method forecast-method--${accent}`}>
    <header><div><span className="ops-kicker">{accent === "algorithmic" ? "01 / Правила и регламент" : "02 / Экспериментальный метод"}</span>
      <h2>{accent === "algorithmic" ? "Алгоритмический расчёт" : "AI-прогноз"}</h2></div><ForecastStatusBadge status={result.status} /></header>
    <div className={`forecast-date ${!hasDate ? "forecast-date--empty" : ""}`}>
      <span>Исходная рекомендация</span>
      <strong>{hasDate ? formatDate(result.recommendedDate) : forecastUnavailableLabel(result)}</strong>
      {result.status !== "ok" && result.recommendedDate && <small>В ответе передана дата {formatDate(result.recommendedDate)}, но статус расчёта не допускает её использование.</small>}
    </div>
    {late && <Callout tone="warning">Дата позже обязательного срока. Она показана как исходный результат метода, а не как допустимый перенос ТО.</Callout>}
    <p className="forecast-explanation">{result.explanation || "Объяснение не передано источником."}</p>
    <dl className="forecast-meta"><div><dt>Неопределённость</dt><dd>{result.uncertaintyNote || "Не оценена источником"}</dd></div></dl>
    {result.warnings.length > 0 && <Callout tone="warning" title="Ограничения метода"><ul>{[...new Set(result.warnings)].map(w => <li key={w}>{w}</li>)}</ul></Callout>}
    <details className="mt-4"><summary>Метод, версия и диагностика</summary><dl className="forecast-meta">
      <div><dt>Метод / версия</dt><dd>{result.methodVersion}</dd></div>
      <div><dt>Модель</dt><dd>{result.modelRef || "Модель не указана"}</dd></div>
      <div><dt>Время расчёта</dt><dd>{result.elapsedMs} мс</dd></div></dl>
    {result.errorCode && <p className="forecast-error">Код: {result.errorCode}</p>}</details>
  </section>;
}
