import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { dateDifference, formatDate, formatDays } from "@/shared/lib/format";
import { exceedsDeadline } from "@/shared/lib/forecastPresentation";
import { PageHeader } from "@/shared/ui/PageHeader";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { Icon } from "@/shared/ui/Icon";
import { ForecastResultCard } from "@/entities/forecast/ForecastResultCard";
import { DecisionStatusBadge, OriginBadge } from "@/shared/ui/StatusBadge";
export function ComparisonDetailPage() {
  const {runId=""}=useParams();
  const query=useApiQuery(()=>maintenanceApi.getComparison(runId),[runId]);
  if(query.status==="loading") return <LoadingState label="Загрузка результата сравнения"/>;
  if(query.status==="error") return <ErrorState description={query.error} action={<Link to="/comparisons" className={buttonClassName("secondary")}>Вернуться к сравнениям</Link>}/>;
  const {run}=query.data;
  const validDates=run.algorithmic.status==="ok" && run.ai.status==="ok" && run.algorithmic.recommendedDate && run.ai.recommendedDate;
  const difference=validDates ? dateDifference(run.algorithmic.recommendedDate!,run.ai.recommendedDate!) : null;
  const late=exceedsDeadline(run.decision.selectedDate,run.mandatoryDueDate);
  return <div className="space-y-6"><Link to="/comparisons" className="ops-back"><Icon name="back" size={17}/>Сравнение прогнозов</Link>
    <PageHeader eyebrow="Один снимок / Два метода" title={run.equipmentName} description={run.operationTitle} actions={run.equipmentId ? <Link to={`/equipment/${run.equipmentId}`} className={buttonClassName("secondary")}>Карточка оборудования</Link> : undefined}/>
    <section className="forecast-decision"><div><span className="ops-kicker">Решение оркестратора</span><div className="forecast-decision-title"><strong>{run.decision.selectedDate ? formatDate(run.decision.selectedDate) : "Требуется уточнение"}</strong><DecisionStatusBadge status={run.decision.status}/></div><ul>{run.decision.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul><p className="text-xs text-muted">Рекомендация не создаёт наряд автоматически · Политика {run.decision.policyVersion}</p></div>
      <aside><Icon name="quality" size={23}/><span>Обязательный срок</span><strong>{formatDate(run.mandatoryDueDate)}</strong><p>{run.mandatoryDueDate ? "Не переносится на более позднюю дату по рекомендации модели." : "Нормативная дата не передана. Допустимость рекомендации нужно уточнить."}</p></aside></section>
    {late && <Callout tone="danger" title="Нарушена нормативная граница">Полученное решение позже обязательного срока. Не используйте его для назначения работ; требуется проверка инженером. Данные ответа сохранены без подмены.</Callout>}
    <div className="forecast-methods"><ForecastResultCard result={run.algorithmic} accent="algorithmic"/><ForecastResultCard result={run.ai} accent="ai"/></div>
    <div className="forecast-difference"><strong>Разница исходных дат</strong><span>{difference === null ? "Не вычисляется: нужны два успешных прогноза с датами." : formatDays(difference)}</span><small>Это расхождение рекомендаций, а не показатель точности модели.</small></div>
    <details className="forecast-snapshot"><summary>Входной снимок и происхождение данных<OriginBadge origin={run.dataOrigin}/></summary><dl><div><dt>Состояние на</dt><dd>{formatDate(run.asOf)}</dd></div><div><dt>Горизонт</dt><dd>{formatDate(run.horizonEnd)}</dd></div><div><dt>Ранняя граница</dt><dd>{formatDate(run.earliestDate)}</dd></div><div><dt>Snapshot ID</dt><dd>{run.snapshotId}</dd></div><div className="forecast-snapshot-hash"><dt>Snapshot hash · одинаковый для двух методов</dt><dd>{run.snapshotHash}</dd></div></dl></details>
  </div>;
}
