import type { ConfirmationStatus,DraftPolicy,ServiceWindow } from '@/shared/api/draftPlans';
import { Button } from '@/shared/ui/Button';
import { FieldCaption,Input,Select,Textarea } from '@/shared/ui/Form';

const statuses={unknown:'Не известно',provisional:'Предварительно',confirmed:'Подтверждено'};
export const weekdays=['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье'];
export const clock=(minutes:number)=>`${String(Math.floor(minutes%1440/60)).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;
const minutes=(value:string)=>{const [h,m]=value.split(':').map(Number);return h*60+m;};
export function newPolicy():DraftPolicy{return {format_version:2,capacity_hours_per_24h:null,capacity_confirmed:false,capacity_status:'unknown',capacity_ref:'',day_start_minute:null,night_start_minute:null,access_status:'unknown',access_mode:null,access_ref:'',service_windows:[]};}
export function reviewedPolicy(policy:DraftPolicy):DraftPolicy{return {...newPolicy(),...policy,format_version:2,capacity_status:policy.capacity_status??(policy.capacity_confirmed?'confirmed':policy.capacity_hours_per_24h?'provisional':'unknown')};}

function Status({label,value,onChange,canConfirm}:{label:string;value:ConfirmationStatus;onChange:(v:ConfirmationStatus)=>void;canConfirm:boolean}) {
  return <label className="block"><FieldCaption>{label}</FieldCaption><Select aria-label={label} value={value} onChange={e=>onChange(e.target.value as ConfirmationStatus)}>{Object.entries(statuses).map(([key,text])=><option key={key} value={key} disabled={key==='confirmed'&&!canConfirm}>{text}</option>)}</Select></label>;
}

export function PolicyFields({value:p,onChange,timezone}:{value:DraftPolicy;onChange:(p:DraftPolicy)=>void;timezone:string}) {
  const update=(fields:Partial<DraftPolicy>)=>onChange({...p,...fields});
  const capacity=(fields:Partial<DraftPolicy>)=>update({...fields,capacity_confirmed:false,capacity_status:(fields.capacity_hours_per_24h===null||!p.capacity_hours_per_24h&&fields.capacity_hours_per_24h===undefined)?'unknown':'provisional'});
  const access=(fields:Partial<DraftPolicy>)=>update({...fields,access_status:'provisional'});
  const windows=p.service_windows??[];
  const windowChange=(index:number,fields:Partial<ServiceWindow>)=>access({service_windows:windows.map((w,i)=>i===index?{...w,...fields}:w)});
  return <div className="space-y-4">
    <div className="space-y-3 rounded-xl border border-line p-4"><h4 className="font-semibold">Полезное рабочее время</h4><p className="text-sm text-muted">Присутствие на объекте и время работы различаются. Укажите согласованную ёмкость; неизвестное значение не заменяется нормой по умолчанию.</p>
      <label className="block"><FieldCaption>Полезная ёмкость сотрудника за 24 часа присутствия</FieldCaption><Input aria-label="Полезная ёмкость сотрудника за 24 часа присутствия" type="number" min="0.001" max={24} step="0.001" value={p.capacity_hours_per_24h??''} placeholder="Уточните значение" onChange={e=>capacity({capacity_hours_per_24h:e.target.value||null})}/></label>
      <label className="block"><FieldCaption>Источник политики ёмкости</FieldCaption><Textarea aria-label="Источник политики ёмкости" value={p.capacity_ref} maxLength={2000} onChange={e=>capacity({capacity_ref:e.target.value})}/></label>
      <Status label="Статус полезной ёмкости" value={p.capacity_status??'unknown'} canConfirm={!!p.capacity_hours_per_24h&&!!p.capacity_ref.trim()} onChange={v=>update({capacity_status:v,capacity_confirmed:v==='confirmed'})}/>
    </div>
    <div className="space-y-3 rounded-xl border border-line p-4"><h4 className="font-semibold">Когда разрешено обслуживать объект</h4><p className="text-sm text-muted">Часовой пояс: {timezone}. Эти часы ограничивают доступ к объекту. Смены сотрудников и сроки ТО проверяются отдельно.</p>
      <label className="block"><FieldCaption>Режим доступа к объекту</FieldCaption><Select aria-label="Режим доступа к объекту" value={p.access_mode??''} onChange={e=>{const mode=e.target.value as DraftPolicy['access_mode'];access({access_mode:mode||null,service_windows:mode==='weekly'?[{weekday:1,start_minute:480,end_minute:1020}]:[]});}}><option value="">Нужно уточнить</option><option value="unrestricted">Без дополнительных ограничений по времени</option><option value="weekly">По дням недели и часам</option></Select></label>
      {p.access_mode==='weekly'&&<><p className="text-sm text-muted">Настройте предварительные интервалы и подтвердите их по источнику. Ночное окончание относится к следующему дню.</p><ol className="space-y-3">{windows.map((w,i)=><li key={i} className="space-y-2 rounded-lg border border-line p-3"><div className="grid gap-2 sm:grid-cols-3">
        <label><FieldCaption>День недели, окно {i+1}</FieldCaption><Select aria-label={`День недели, окно ${i+1}`} value={w.weekday} onChange={e=>windowChange(i,{weekday:Number(e.target.value)})}>{weekdays.map((day,j)=><option key={day} value={j+1}>{day}</option>)}</Select></label>
        <label><FieldCaption>С, окно {i+1}</FieldCaption><Input aria-label={`С, окно ${i+1}`} type="time" required value={clock(w.start_minute)} onChange={e=>{if(e.target.value)windowChange(i,{start_minute:minutes(e.target.value)});}}/></label>
        <label><FieldCaption>До, окно {i+1}</FieldCaption><Input aria-label={`До, окно ${i+1}`} type="time" required value={clock(w.end_minute)} onChange={e=>{if(e.target.value)windowChange(i,{end_minute:minutes(e.target.value)+(w.end_minute>=1440?1440:0)});}}/></label>
      </div><label className="flex gap-2 text-sm"><input type="checkbox" checked={w.end_minute>=1440} onChange={e=>windowChange(i,{end_minute:w.end_minute%1440+(e.target.checked?1440:0)})}/>Окончание на следующий день, окно {i+1}</label><Button variant="ghost" onClick={()=>access({service_windows:windows.filter((_,j)=>j!==i)})}>Убрать окно {i+1}</Button></li>)}</ol><Button variant="secondary" disabled={windows.length>=28} onClick={()=>access({service_windows:[...windows,{weekday:1,start_minute:480,end_minute:1020}]})}>Добавить окно доступа</Button></>}
      <label className="block"><FieldCaption>Основание режима доступа</FieldCaption><Textarea aria-label="Основание режима доступа" value={p.access_ref??''} maxLength={2000} onChange={e=>access({access_ref:e.target.value})}/></label>
      <Status label="Статус доступа к объекту" value={p.access_status??'unknown'} canConfirm={!!p.access_mode&&!!p.access_ref?.trim()&&(p.access_mode!=='weekly'||!!windows.length)} onChange={v=>update({access_status:v})}/>
    </div>
  </div>;
}

export function PolicySummary({value:p,timezone}:{value:DraftPolicy;timezone:string}) {
  return <div className="space-y-2 text-sm" aria-label="Условия расчёта версии"><p>Полезная ёмкость: {p.capacity_hours_per_24h??'не указана'} ч / 24 ч присутствия · {statuses[p.capacity_status??(p.capacity_confirmed?'confirmed':'unknown')]}</p>{p.capacity_ref&&<p className="whitespace-pre-wrap break-words text-muted">Основание ёмкости: {p.capacity_ref}</p>}
    <p>Доступ: {p.format_version!==2?'требует проверки для нового выпуска':p.access_mode==='unrestricted'?'без дополнительных ограничений':p.access_mode==='weekly'?'по недельным окнам':'не определён'} · {statuses[p.access_status??'unknown']} · {timezone}</p>
    {!!p.service_windows?.length&&<ul>{p.service_windows.map((w,i)=><li key={i}>{weekdays[w.weekday-1]}: {clock(w.start_minute)}–{clock(w.end_minute)}{w.end_minute>=1440?' следующего дня':''}</li>)}</ul>}{p.access_ref&&<p className="whitespace-pre-wrap break-words text-muted">Основание доступа: {p.access_ref}</p>}
  </div>;
}
