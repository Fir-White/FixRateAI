import {memo,useState} from 'react';
import {Link} from 'react-router-dom';
import {assistantApi,type ChatAction} from '@/shared/api/assistant';
import {Button} from '@/shared/ui/Button';
import {Callout} from '@/shared/ui/Callout';
const labels:Record<string,string>={name:'Название',asset_code:'Инвентарный код',location:'Расположение',status:'Состояние',reason:'Причина',title:'Название плана',expected_revision:'Исходная версия',system_id:'Система',equipment_type_id:'Тип оборудования',equipment_id:'Оборудование',task_id:'Задание',identity:'План',serial_number:'Серийный номер',commissioned_on:'Дата ввода',start_at:'Начало',end_at:'Окончание',start_local:'Начало (время объекта)',end_local:'Окончание (время объекта)',executor_ids:'Исполнители',worker_ids:'Исполнители',comparability_confirmed:'Сопоставимость фото подтверждена',locked:'Закрепить',unlock:'Разрешить снятие закрепления',narrative:'Описание выполнения',verdict:'Решение',policy:'Условия расчёта',input:'Исходные данные',answers:'Ответы чек-листа',readings:'Показания',actual:'Фактическое выполнение',parent_equipment_id:'Родительское оборудование',properties:'Свойства',data_origin:'Происхождение',idempotency_key:'Ключ защиты от повтора'};
const states:Record<ChatAction['status'],string>={proposed:'Нужно ваше подтверждение',rejected:'Отклонено',executing:'Выполняется',succeeded:'Выполнено',failed:'Действие отклонено системой',uncertain:'Результат требует проверки',stale:'Предложение устарело'};
const values:Record<string,string>={active:'В работе',under_repair:'На ремонте',retired:'Выведено из эксплуатации',customer:'Данные заказчика',synthetic_demo:'Тестовые данные',accepted:'Принять',rejected:'Вернуть на доработку'};
function value(v:unknown){return v===null?'Не задано':typeof v==='boolean'?v?'Да':'Нет':typeof v==='object'?JSON.stringify(v,null,2):values[String(v)]??String(v);}
export const ActionCard=memo(function ActionCard({action:original,title,onChanged}:{action:ChatAction;title:string;onChanged:()=>void}){
  const [resolved,setResolved]=useState<ChatAction|null>(null);const action=resolved??original;
  const [consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const expired=Date.parse(action.expires_at)<Date.now();
  const fields=Object.entries({...action.arguments.path,...action.arguments.query,...action.arguments.body}).filter(([k,v])=>k!=='idempotency_key'&&v!==null&&v!==undefined&&!(typeof v==='object'&&Object.keys(v).length===0));
  const before=action.before_snapshot?.preview;
  const run=async(confirm:boolean)=>{setBusy(true);setError('');try{setResolved(confirm?await assistantApi.confirm(action):await assistantApi.reject(action.action_id));onChanged();}catch(e){setError(e instanceof Error?e.message:'Не удалось выполнить действие');onChanged();}finally{setBusy(false);}};
  const target=action.arguments.path?.equipment_id;
  return <section className="min-w-0 space-y-4 rounded-2xl border border-accent/30 bg-surface p-4 sm:p-5" aria-label={`Предложение: ${title}`}>
    <div className="flex flex-wrap items-start justify-between gap-2"><h3 className="font-semibold">{title}</h3><span role="status" className="text-xs text-muted">{states[action.status]}</span></div>
    <p className="whitespace-pre-wrap text-sm">{action.explanation}</p>
    {typeof target==='string'&&<Link className="text-sm text-accent underline" to={`/equipment/${encodeURIComponent(target)}`}>Открыть оборудование</Link>}
    <dl className="space-y-2 text-sm">{fields.map(([key,v])=><div key={key} className="grid min-w-0 gap-1 border-t border-line pt-2 sm:grid-cols-[160px_minmax(0,1fr)]"><dt className="text-muted">{labels[key]??key}</dt><dd className="min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{value(v)}</dd></div>)}</dl>
    <details className="text-sm"><summary className="cursor-pointer text-muted">Все параметры команды</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs [overflow-wrap:anywhere]">{JSON.stringify(action.arguments,null,2)}</pre></details>
    {before!==null&&before!==undefined&&<details className="text-sm"><summary className="cursor-pointer text-muted">Данные до изменения</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs [overflow-wrap:anywhere]">{JSON.stringify(before,null,2)}</pre></details>}
    {action.status==='proposed'&&<><p className="text-xs text-muted">Проверяйте объект, значения и причину. Подтверждение относится только к этому предложению; срок действия — 15 минут.</p>{expired?<Callout>Предложение истекло. Попросите подготовить новое.</Callout>:<fieldset disabled={busy} className="space-y-3"><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} className="mt-1"/>Я проверил параметры и подтверждаю это изменение</label><div className="flex flex-wrap gap-2"><Button disabled={!consent} onClick={()=>void run(true)}>{busy?'Выполнение…':'Подтвердить и выполнить'}</Button><Button variant="secondary" onClick={()=>void run(false)}>Отклонить</Button></div></fieldset>}</>}
    {action.status==='uncertain'&&<Callout tone="warning">Ответ после выполнения потерян. Проверьте состояние в системе перед новой командой. Повторное подтверждение не запустит действие ещё раз.</Callout>}
    {action.result?.message&&<p className="text-sm whitespace-pre-wrap">{action.result.message}</p>}
    {action.result?.data!==undefined&&<details className="text-sm"><summary className="cursor-pointer text-accent">Результат действия</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs [overflow-wrap:anywhere]">{JSON.stringify(action.result.data,null,2)}</pre></details>}
    {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}
  </section>;
});
