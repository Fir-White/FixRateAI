import {useEffect,useState} from 'react';
import {planLoadApi as api} from '@/shared/api/planLoad';
import type {DraftRecord} from '@/shared/api/draftPlans';
import {useApiQuery} from '@/shared/lib/useApiQuery';
import {formatDate,formatDateTime} from '@/shared/lib/format';
import {Button} from '@/shared/ui/Button';
import {LoadingState,ErrorState} from '@/shared/ui/States';
import {Callout} from '@/shared/ui/Callout';
import {PlanningPages} from './PlanningChoices';

const number=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:3});
const hours=(value:string|null)=>value===null?'Неизвестно':`${number.format(Number(value))} чел.-ч`;

export default function PlanLoadPanel({record,timezone,month,onMonth}:{record:DraftRecord;timezone:string;month?:string;onMonth?:(month:string)=>void}) {
  const [retry,setRetry]=useState(0),[localMonth,setLocalMonth]=useState(''),[offset,setOffset]=useState(0);
  const selected=month??localMonth;
  useEffect(()=>setOffset(0),[selected]);
  const query=useApiQuery(()=>api.preview(record.draft_id,record.revision),[record.draft_id,record.revision,retry],undefined,`plan-load:${record.draft_id}:${record.revision}`);
  if(query.status==='loading')return <LoadingState label="Расчёт нагрузки выбранной версии"/>;
  if(query.status==='error')return <section className="space-y-3"><ErrorState description={query.error}/><Button variant="secondary" onClick={()=>setRetry(n=>n+1)}>Повторить расчёт нагрузки</Button></section>;
  const data=query.data,t=data.totals,days=data.days.filter(d=>!selected||d.date.startsWith(selected));
  const pick=(value:string)=>{setLocalMonth(value);onMonth?.(value);setOffset(0);};
  return <section className="space-y-4" aria-label="Нагрузка выбранной версии плана"><div><h3 className="text-lg font-semibold">Нагрузка и обеспеченность людьми</h3><p className="mt-2 text-sm text-muted">Только «{record.title}», версия {record.revision}. Альтернативные планы не суммируются. Часовой пояс: {data.timezone}.</p></div>
    <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-line p-4"><p className="text-sm text-muted">Подтверждённый объём</p><strong>{hours(t.total_person_hours)}</strong></div><div className="rounded-xl border border-line p-4"><p className="text-sm text-muted">Распределено по датам</p><strong>{hours(t.placed_person_hours)}</strong></div><div className="rounded-xl border border-line p-4"><p className="text-sm text-muted">Осталось распределить</p><strong>{hours(t.unplaced_person_hours)}</strong></div></div>
    {data.source_state==='published_snapshot'?<Callout>Опубликованная версия: часы и состав бригад показаны из согласованного плана. Собственные назначения учтены один раз; свободная ёмкость проверена по текущим сменам и другим работам. Выполнение смотрите в заданиях.</Callout>:data.source_state==='stale'?<Callout tone="danger">Источник изменился. Сводка показывает сохранённый объём; перед новым размещением и выпуском нужен актуальный расчёт.</Callout>:null}
    {Number(t.unplaced_person_hours)>0&&<Callout>Неразмещённые часы показаны отдельно по конечным срокам. Их ещё нельзя считать нагрузкой конкретного дня или точной потребностью в людях.</Callout>}
    {Number(t.due_outside_view_person_hours)>0&&<Callout>Срок за пределами показанных дат: {hours(t.due_outside_view_person_hours)}; из них не размещено {hours(t.unplaced_outside_view_person_hours)}. Этот объём сохраняется в составе версии.</Callout>}
    <p className="text-sm">Полезная ёмкость, доступная этой версии: {hours(t.available_person_hours)}. Нехватка ёмкости для размещённых интервалов: {hours(t.deficit_person_hours)}.</p>
    {data.unknown_workers>0&&<p className="text-sm">У сотрудников с неполными сведениями о сменах или занятости: {data.unknown_workers}. Доступность не заменяется нулём.</p>}
    <p className="text-sm text-muted">Ёмкость включает свободных сотрудников объекта и учитывает занятость на других объектах. Совпадение окон, допуски и полный состав проверяются отдельно; общая сумма часов не доказывает обеспеченность конкретной работы.</p>
    <div className="flex flex-wrap items-center gap-3"><Button variant="secondary" onClick={()=>setRetry(n=>n+1)}>Обновить сводку нагрузки</Button><span className="text-xs text-muted">Снимок {formatDateTime(data.checked_at,timezone)}</span></div>
    <div className="grid gap-2 sm:grid-cols-3" aria-label="Период сводки нагрузки"><Button variant={!selected?'primary':'secondary'} onClick={()=>pick('')}>Весь горизонт нагрузки</Button>{data.months.map(m=><Button key={m.month} variant={selected===m.month?'primary':'secondary'} onClick={()=>pick(m.month)}>{m.month} · размещено {m.planned_person_hours} чел.-ч · по срокам {m.due_person_hours} чел.-ч</Button>)}</div>
    {data.total_issues>0&&<details><summary>Результат проверки ограничений: {data.total_issues}</summary><p className="my-2 text-sm">Проверка пригодности для нового размещения: {data.validation_status==='valid'?'ограничения соблюдены':data.validation_status==='incomplete'?'требуются данные или размещение':'есть нарушения'}. Для опубликованной версии это не отменяет историю выпуска.</p><ul className="space-y-2 text-sm">{data.issues.map((i,n)=><li key={n}>{i.message}</li>)}</ul></details>}
    <ul className="grid gap-3 lg:grid-cols-2" aria-label="Подневная нагрузка">{days.slice(offset,offset+25).map(d=><li key={d.date} className="space-y-2 rounded-xl border border-line p-4"><h4 className="font-semibold">{formatDate(d.date)}</h4><p className="text-sm">Размещено: {hours(d.planned_person_hours)}. Зарезервировано присутствия: {hours(d.reserved_person_hours)}.</p><dl className="grid grid-cols-3 gap-2 break-words text-sm"><div><dt>Требуется одновременно</dt><dd className="mt-1 font-semibold">{d.required_people_peak}</dd></div><div><dt>{data.source_state==='published_snapshot'?'Назначено по плану':'Выбрано в черновике'}</dt><dd className="mt-1 font-semibold">{d.selected_people_peak}</dd></div><div><dt>Пик свободных людей</dt><dd className="mt-1 font-semibold">{d.available_people_peak??'Неизвестно'}</dd></div></dl><p className="text-xs text-muted">Пики могут приходиться на разные часы; это не подтверждение подходящей бригады.</p><p className="text-sm">Свободная ёмкость: {hours(d.available_person_hours)}. Нехватка: {hours(d.deficit_person_hours)}.</p>{Number(d.unplaced_due_person_hours)>0&&<p className="text-sm text-accent">Осталось с конечным сроком в эту дату: {hours(d.unplaced_due_person_hours)}</p>}</li>)}</ul>{!days.length&&<p>В выбранном месяце нет дат этого горизонта.</p>}<PlanningPages offset={offset} total={days.length} onPage={setOffset}/>
  </section>;
}
