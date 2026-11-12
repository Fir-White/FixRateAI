import { useState } from "react";
import { planningApi } from "@/shared/api/planning";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { Button } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { Card, CardHeader } from "@/shared/ui/Card";
import { Input } from "@/shared/ui/Form";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import "./workload.css";

const hours = (value: string | null) => value === null ? "Неизвестно" : `${Number(value).toLocaleString("ru-RU", {maximumFractionDigits: 3})} чел.-ч`;
const stateLabels = {
  hours_deficit: "Не хватает часов", hours_sufficient: "Часов достаточно — нужен подбор",
  incomplete: "Нужны данные", no_work: "Нет работ к назначению",
};
const demandStates = {unassigned: "К назначению", assigned: "Назначено", reported: "Выполнено / на проверке", incomplete: "Назначение требует проверки"};

export function WorkloadPanel({year, month}: {year: number; month: number}) {
  const [input, setInput] = useState("24");
  const [capacity, setCapacity] = useState("24");
  const [revision, setRevision] = useState(0);
  const scope = `${year}:${month}:${capacity}:${revision}`;
  const query = useApiQuery(async () => ({scope, result: await planningApi.workload(year, month, capacity)}), [scope]);
  const data = query.status === "success" && query.data.scope === scope ? query.data.result : null;
  return <section className="fr-workload" aria-label="Нагрузка и персонал">
    <Card><CardHeader title="Нагрузка и персонал" description="Обязательные работы и дополнительная потребность по дням."/>
      <form className="fr-workload-policy" onSubmit={event => {event.preventDefault(); setCapacity(input); setRevision(value => value + 1);}}>
        <label>Полезные часы за 24 часа присутствия<Input aria-label="Полезные часы за 24 часа присутствия" type="number" min="0.001" max="24" step="0.001" required value={input} onChange={event => setInput(event.target.value)}/></label>
        <Button type="submit">Пересчитать нагрузку</Button>
      </form>
      <p className="fr-workload-note">Начальное допущение — 24 часа. Короткие свободные интервалы учитываются пропорционально. Это предварительный расчёт; назначения он не создаёт.</p>
    </Card>
    {(query.status === "loading" || (query.status === "success" && !data)) && <LoadingState label="Расчёт нагрузки"/>}
    {query.status === "error" && <ErrorState description={query.error}/>}
    {data && <>
      <div className="fr-workload-summary" aria-label="Итоги расчёта">
        <Card><span>Обязательных работ</span><strong>{data.total_occurrences}</strong></Card>
        <Card><span>К назначению</span><strong>{data.unassigned_occurrences}</strong></Card>
        <Card><span>Дней с дефицитом часов</span><strong>{data.deficit_days}</strong></Card>
        <Card><span>Дней с неполными данными</span><strong>{data.incomplete_days}</strong></Card>
      </div>
      <Callout tone="warning">Количество людей — нижняя оценка. Свободные часы учитывают занятость на других объектах. Квалификации и общий свободный интервал бригады проверяются при подборе конкретной работы.</Callout>
      {data.source_incomplete && <Callout tone="warning">Часть регламентов не рассчитана. Известные работы показаны, полная потребность требует уточнения.</Callout>}
      <div className="fr-workload-days">{data.days.map(day => <Card key={day.date} className={`fr-workload-day state-${day.status}`}>
        <div className="fr-workload-day-heading"><h3>{formatDate(day.date)}</h3><span>{stateLabels[day.status]}</span></div>
        <dl className="fr-workload-facts">
          <div><dt>Всего по работам</dt><dd>{hours(day.total_person_hours)}</dd></div>
          <div><dt>Осталось обеспечить</dt><dd>{hours(day.unassigned_person_hours)}</dd></div>
          <div><dt>Дополнительно людей, минимум</dt><dd>{day.required_workers_lower_bound ?? "Неизвестно"}</dd></div>
          <div><dt>Свободная ёмкость</dt><dd>{hours(day.free_person_hours)}</dd></div>
          <div><dt>Свободных / назначенных</dt><dd>{day.free_workers} / {day.assigned_workers}</dd></div>
          <div><dt>Дефицит часов</dt><dd>{hours(day.deficit_person_hours)}</dd></div>
        </dl>
        {(day.unknown_norms > 0 || day.unknown_workers > 0) && <p className="fr-workload-note">Неизвестных норм: {day.unknown_norms}. Неполных календарей или назначений сотрудников: {day.unknown_workers}. Известная нагрузка: {hours(day.known_person_hours)}, свободная ёмкость: {hours(day.known_free_person_hours)}.</p>}
        {day.occurrences.length > 0 && <details><summary>Работы и основания расчёта ({day.occurrences.length})</summary><ul>{day.occurrences.map(work => <li key={work.occurrence_id}><strong>{work.operation_title}</strong><span>{work.equipment_name} · {hours(work.person_hours)} · бригада от {work.crew_size} чел. · {demandStates[work.state]}</span></li>)}</ul></details>}
      </Card>)}</div>
    </>}
  </section>;
}
