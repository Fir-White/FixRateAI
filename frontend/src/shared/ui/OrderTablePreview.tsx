import type { WorksheetPreview } from '@/shared/api/orderTable';

const actions={update:'Обновится',create:'Будет создан',reschedule:'Перенос назначения'};
export const orderNormUnits:Record<string,string>={person_hour:'чел.-ч',elapsed_hour:'ч'};
export const formatOrderTime=(value?:string|null)=>value?.replace('T',' ')||'—';

export function OrderTablePreview({items}:{items:WorksheetPreview['items']}){
  return <ol className="space-y-3">{items.map(item=><li className="rounded-lg border border-line p-3 text-sm" key={item.index}>
    {item.action==='blocked'?<p className="text-danger">Строка {item.index+1}: {item.issue}</p>:<>
      <p className="break-words"><strong>{actions[item.action]}:</strong> {item.title} {item.equipment&&`· ${item.equipment}`}</p>
      <p>Наряд: {item.task_id.slice(0,8)}</p>
      {item.due_date&&<p>Обязательный срок: {item.due_date}</p>}
      {item.normative_hours&&<p>Норма: {item.normative_hours} {item.normative_unit?orderNormUnits[item.normative_unit]??'':''}</p>}
      <p>Интервал: {item.before_start?`${formatOrderTime(item.before_start)} — ${formatOrderTime(item.before_end)} → `:''}{formatOrderTime(item.planned_start)} — {formatOrderTime(item.planned_end)}</p>
      {(item.planned_person_hours??null)!==(item.before_hours??null)&&<p>План, чел.-ч: {item.before_hours??'—'} → {item.planned_person_hours??'—'}</p>}
      {(item.note??'')!==(item.before_note??'')&&<p className="break-words">Примечание: {item.before_note||'—'} → {item.note||'—'}</p>}
      {Boolean(item.worker_names?.length)&&<p>Бригада: {item.worker_names!.join(', ')}</p>}
    </>}
  </li>)}</ol>;
}
