import { Link, useSearchParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { exceedsDeadline, forecastUnavailableLabel } from "@/shared/lib/forecastPresentation";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { DecisionStatusBadge, ForecastStatusBadge } from "@/shared/ui/StatusBadge";
import type { ForecastResult } from "@/shared/types/domain";

export function ComparisonsPage() {
  const query = useApiQuery(() => maintenanceApi.listComparisons(), []);
  const [params, setParams] = useSearchParams();
  const search = params.get("q") ?? "";
  const equipment = params.get("equipment") ?? "";
  const setFilter = (key: string, value: string) => { const next = new URLSearchParams(params); value ? next.set(key, value) : next.delete(key); setParams(next, { replace: true }); };
  const all = query.data ?? [];
  const options = Array.from(new Map(all.filter(r => r.equipmentId).map(r => [r.equipmentId!, r.equipmentName])));
  const items = all.filter(r => (!equipment || r.equipmentId === equipment) && `${r.equipmentName} ${r.operationTitle} ${r.runId}`.toLocaleLowerCase("ru").includes(search.trim().toLocaleLowerCase("ru"))).sort((a,b) => b.createdAt.localeCompare(a.createdAt));
  return <div className="space-y-6">
    <PageHeader eyebrow="Планирование / Поддержка решений" title="Сравнение прогнозов" description="Один снимок данных. Два метода. Объяснимое решение — без переноса обязательного срока." actions={<Link to="/equipment" className={buttonClassName("secondary")}>Оборудование<Icon name="chevron" size={16}/></Link>} />
    <div className="forecast-rule"><Icon name="quality" size={20}/><p><strong>Регламент — граница, а не рекомендация.</strong><span>Исходный ответ AI сохраняется отдельно. Недостаток данных не заменяется вымышленной датой или точностью.</span></p></div>
    {query.status === "loading" && <LoadingState/>}{query.status === "error" && <ErrorState description={query.error}/>}
    {query.status === "success" && <><div className="ops-register-tools"><label className="ops-search"><Icon name="search" size={17}/><input aria-label="Поиск сравнения" placeholder="Оборудование или операция" value={search} onChange={e => setFilter("q", e.target.value)}/></label>
      <select aria-label="Оборудование для сравнения" value={equipment} onChange={e => setFilter("equipment",e.target.value)}><option value="">Всё оборудование</option>{options.map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select><span className="text-xs text-muted">{items.length} из {all.length}</span></div>
      {items.length === 0 ? <EmptyState title={all.length ? "Нет подходящих сравнений" : "Запусков сравнения нет"} description={all.length ? "Измените поиск или фильтр оборудования." : "Сравнение запускается из карточки наряда для подтверждённой привязки регламента."}/> : <div className="forecast-register">{items.map(run => <article key={run.runId} className="forecast-row">
        <header><div><span className="ops-kicker">Снимок на {formatDate(run.asOf)}</span><h2><Link to={`/comparisons/${run.runId}`}>{run.equipmentName}</Link></h2><p>{run.operationTitle}</p></div><DecisionStatusBadge status={run.decision.status}/></header>
        <div className="forecast-lanes"><Result label="Алгоритмический" result={run.algorithmic}/><Result label="AI-прогноз" result={run.ai}/><div className="forecast-lane forecast-lane--decision"><span>Решение оркестратора</span><strong>{run.decision.selectedDate ? formatDate(run.decision.selectedDate) : "Нужно уточнение"}</strong>{exceedsDeadline(run.decision.selectedDate,run.mandatoryDueDate) && <b className="text-warning">Нарушение нормативной границы</b>}</div></div>
        <footer><span><Icon name="clock" size={14}/>Обязательный срок <b>{formatDate(run.mandatoryDueDate)}</b></span><Link to={`/comparisons/${run.runId}`}>Разобрать решение<Icon name="chevron" size={16}/></Link></footer>
      </article>)}</div>}
    </>}
  </div>;
}
function Result({label,result}:{label:string;result:ForecastResult}) {
  return <div className="forecast-lane"><span>{label}</span><strong className={result.status === "ok" && result.recommendedDate ? "" : "forecast-unavailable"}>{result.status === "ok" && result.recommendedDate ? formatDate(result.recommendedDate) : forecastUnavailableLabel(result)}</strong><ForecastStatusBadge status={result.status}/>{exceedsDeadline(result.recommendedDate,result.mandatoryDueDate) && <small className="text-warning">Позже обязательного срока</small>}</div>;
}
