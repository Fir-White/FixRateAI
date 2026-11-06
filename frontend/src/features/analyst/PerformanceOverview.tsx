import { useId, useState } from "react";
import residentialScene from "@/assets/residential-overview-v1.webp";
import { DEMO_MODE, request } from "@/shared/api/request";
import { formatDate } from "@/shared/lib/format";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { buttonClassName } from "@/shared/ui/Button";
import { Card } from "@/shared/ui/Card";
import { Input } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import "./performance-overview.css";

interface SiteSummary {
  siteId: string;
  siteName: string;
  jobs: number;
  accepted: number;
  slaOnTime: number;
  slaEligible: number;
  plannedNormPersonHours: string | null;
  confirmedNormJobs: number;
  actualPersonHours: string | null;
  actualReports: number;
  loadPersonMinutes: Record<string, number>;
  overdue: number;
}

const base = "/api/v1/maintenance";

export function PerformanceOverview() {
  const headingId = useId();
  const query = useApiQuery(
    () => DEMO_MODE ? Promise.resolve([]) : request<SiteSummary[]>(`${base}/overview`),
    [],
    undefined,
    DEMO_MODE ? undefined : "overview",
  );
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));

  return (
    <Card className="fr-property-overview" role="region" aria-labelledby={headingId}>
      <img className="fr-property-scene" src={residentialScene} alt="" aria-hidden="true" loading="lazy" decoding="async" />
      <div className="fr-property-content">
        <h2 id={headingId} className="fr-property-heading">Показатели доступных объектов</h2>
        {query.status === "loading" && <p role="status" className="fr-property-state">Загрузка показателей…</p>}
        {query.status === "error" && <p role="alert" className="fr-property-state">{query.error}</p>}
        {query.status === "success" && !query.data.length && <p className="fr-property-state">Нет доступных объектов с показателями.</p>}
        {query.status === "success" && query.data.map(site => {
          const peaks = Object.entries(site.loadPersonMinutes).sort((a, b) => b[1] - a[1]).slice(0, 3);
          return (
            <section className="fr-property-site" key={site.siteId} aria-label={site.siteName}>
              <h3>{site.siteName}</h3>
              <dl className="fr-property-metrics">
                <div><dt>Заданий</dt><dd>{site.jobs}</dd></div>
                <div><dt>Приёмок</dt><dd className="fr-property-accepted">{site.accepted}</dd></div>
                <div><dt>Незакрытых просрочек</dt><dd className={site.overdue > 0 ? "fr-property-overdue" : undefined}>{site.overdue}</dd></div>
              </dl>
              <dl className="fr-property-facts">
                <div>
                  <dt>SLA по времени приёмки</dt>
                  <dd>{site.slaEligible ? <strong>{site.slaOnTime}<span className="fr-property-denominator"> / {site.slaEligible}</span></strong> : "Нет подтверждённых данных"}</dd>
                </div>
                <div>
                  <dt>Фактические трудозатраты</dt>
                  <dd>{site.actualPersonHours !== null ? <><strong>{site.actualPersonHours}</strong><span> чел.-ч</span></> : "Нет данных"}</dd>
                  <dd className="fr-property-caption">{site.actualReports} отчётов</dd>
                </div>
                <div>
                  <dt>Плановая норма</dt>
                  <dd>{site.plannedNormPersonHours !== null ? <><strong>{site.plannedNormPersonHours}</strong><span> чел.-ч</span></> : "Не подтверждена"}</dd>
                  <dd className="fr-property-caption">{site.confirmedNormJobs ?? 0} заданий с подтверждённой единицей</dd>
                </div>
              </dl>
              <div className="fr-property-load">
                <h4>Пиковая плановая загрузка</h4>
                {peaks.length ? <ul>{peaks.map(([day, minutes]) => <li key={day}><time dateTime={day}>{formatDate(day)}</time><span>{(minutes / 60).toFixed(2)} чел.-ч</span></li>)}</ul> : <p>Нет назначений с подтверждённой длительностью.</p>}
              </div>
            </section>
          );
        })}
      </div>
      <div className="fr-property-export">
        <label>Месяц экспорта<Input type="month" value={month} onChange={event => setMonth(event.target.value)} /></label>
        {month && !DEMO_MODE && <div className="fr-property-downloads">
          <a className={buttonClassName("secondary")} aria-label="Скачать месячный график XLSX" href={`${base}/export.xlsx?year=${+month.slice(0, 4)}&month=${+month.slice(5)}&kind=schedule`}><Icon name="calendar" size={18} />График XLSX</a>
          <a className={buttonClassName("ghost")} aria-label="Скачать задания XLSX" href={`${base}/export.xlsx?year=${+month.slice(0, 4)}&month=${+month.slice(5)}&kind=orders`}><Icon name="report" size={18} />Задания XLSX</a>
        </div>}
      </div>
    </Card>
  );
}
