import {memo,useState} from 'react';
import {Link} from 'react-router-dom';
import {assistantApi,type ChatAction,type ChatAttachment} from '@/shared/api/assistant';
import {dateTimeFormatter} from '@/shared/lib/dateTimeFormatter';
import {Button} from '@/shared/ui/Button';
import {Callout} from '@/shared/ui/Callout';
import {Icon} from '@/shared/ui/Icon';
import {OrderTablePreview} from '@/shared/ui/OrderTablePreview';
import type {WorksheetPreview} from '@/shared/api/orderTable';
import {notifyOtherTabs} from '@/shared/session/SessionContext';
import {attachmentUrl,ChatPhoto} from './ChatPhoto';
import './action-card.css';
const labels:Record<string,string>={role:'Роль',user_id:'Сотрудник',is_active:'Доступ активен',file:'Файл',photo:'Фотография',payload:'Показание и основание',email:'Новый email',site_id:'Здание',preview_token:'Контроль предпросмотра',name:'Название',asset_code:'Инвентарный код',location:'Расположение',status:'Состояние',reason:'Причина',title:'Название плана',expected_revision:'Исходная версия',system_id:'Система',equipment_type_id:'Тип оборудования',equipment_id:'Оборудование',task_id:'Задание',identity:'План',serial_number:'Серийный номер',commissioned_on:'Дата ввода',start_at:'Начало',end_at:'Окончание',start_local:'Начало (время объекта)',end_local:'Окончание (время объекта)',executor_ids:'Исполнители',worker_ids:'Исполнители',comparability_confirmed:'Сопоставимость фото подтверждена',locked:'Закрепить',unlock:'Разрешить снятие закрепления',narrative:'Описание выполнения',verdict:'Решение',policy:'Условия расчёта',input:'Исходные данные',answers:'Ответы чек-листа',readings:'Показания',actual:'Фактическое выполнение',parent_equipment_id:'Родительское оборудование',properties:'Свойства',data_origin:'Происхождение',idempotency_key:'Ключ защиты от повтора'};
const states:Record<ChatAction['status'],string>={proposed:'Нужно ваше подтверждение',rejected:'Отклонено',executing:'Выполняется',succeeded:'Выполнено',failed:'Действие отклонено системой',uncertain:'Результат требует проверки',stale:'Предложение устарело'};
const executorActions = new Set(['task_start', 'report_save', 'report_submit', 'report_attach_and_submit']);
const technicalFields = new Set(['expected_revision','preview_token','schema_version']);
const values:Record<string,string>={director:'Руководитель',chief_engineer:'Главный инженер',admin:'Администратор',dispatcher:'Диспетчер',engineer:'Инженер',executor:'Исполнитель',before:'До работы',after:'После работы',active:'В работе',under_repair:'На ремонте',retired:'Выведено из эксплуатации',customer:'Данные заказчика',synthetic_demo:'Тестовые данные',accepted:'Принять',rejected:'Вернуть на доработку',draft:'Черновик',assigned:'Назначено',in_progress:'В работе',submitted:'На проверке',rework:'На доработке',rework_required:'На доработке',cancelled:'Отменено'};
function formatWhen(raw:unknown):string|null{
  if(typeof raw!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(raw))return null;
  const ms=Date.parse(raw);
  if(Number.isNaN(ms))return null;
  return dateTimeFormatter('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(ms);
}
function assignmentWindow(body:ChatAction['arguments']['body'],timezone:string|undefined){
  const start=typeof body?.start_at==='string'?Date.parse(body.start_at):NaN;
  const end=typeof body?.end_at==='string'?Date.parse(body.end_at):NaN;
  if(!timezone||!Number.isFinite(start)||!Number.isFinite(end))return null;
  try{
    const date=dateTimeFormatter('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:timezone});
    const clock=dateTimeFormatter('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:timezone});
    const first=date.format(start),last=date.format(end);
    return first===last?`${first} · ${clock.format(start)}–${clock.format(end)}`:
      `${first}, ${clock.format(start)} — ${last}, ${clock.format(end)}`;
  }catch{return null;}
}
function value(v:unknown){return v===null?'Не задано':typeof v==='boolean'?v?'Да':'Нет':typeof v==='object'?JSON.stringify(v,null,2):formatWhen(v)??values[String(v)]??String(v);}
function resultSummaryRows(data:unknown):Array<[string,string]>{
  if(!data||typeof data!=='object'||Array.isArray(data))return [];
  const obj=data as Record<string,unknown>;
  if(typeof obj.siteName==='string')return [['Здание',obj.siteName],...(typeof obj.role==='string'?[['Роль',values[obj.role]??obj.role] as [string,string]]:[])];
  if(obj.profile&&typeof obj.profile==='object'){
    const profile=obj.profile as Record<string,unknown>;
    if(typeof profile.siteName==='string')return resultSummaryRows(profile);
  }
  const task=obj.task&&typeof obj.task==='object'?obj.task as Record<string,unknown>:null;
  if(task){
    const rows:Array<[string,string]>=[];
    const title=typeof task.title==='string'?task.title:'';
    const code=typeof task.code==='string'?task.code:'';
    if(title||code)rows.push(['Задание',code&&title?`${title} (${code})`:title||code]);
    if(typeof task.state==='string')rows.push(['Статус',values[task.state]??task.state]);
    if(typeof task.equipmentName==='string'&&task.equipmentName)rows.push(['Оборудование',task.equipmentName]);
    if(Array.isArray(task.assignees)){
      const names=task.assignees.map(a=>a&&typeof a==='object'&&typeof (a as {name?:unknown}).name==='string'?(a as {name:string}).name:'').filter(Boolean);
      rows.push(['Исполнители',names.length?names.join(', '):'Не назначены']);
    }
    const start=formatWhen(task.scheduledStart);
    const end=formatWhen(task.scheduledEnd);
    if(start)rows.push(['Плановое время',end?`${start} — ${end}`:start]);
    return rows;
  }
  if(typeof obj.name==='string'&&(typeof obj.asset_code==='string'||typeof obj.equipment_id==='string'||typeof obj.location==='string')){
    const rows:Array<[string,string]>=[['Оборудование',obj.name]];
    if(typeof obj.asset_code==='string'&&obj.asset_code)rows.push(['Инвентарный код',obj.asset_code]);
    if(typeof obj.location==='string'&&obj.location)rows.push(['Расположение',obj.location]);
    if(typeof obj.status==='string')rows.push(['Состояние',values[obj.status]??obj.status]);
    return rows;
  }
  return [];
}
function protectedResource(data:unknown):{url:string;title:string}|null{
  if(!data||typeof data!=='object')return null;
  const resource=(data as {resource?:unknown}).resource;
  if(!resource||typeof resource!=='object')return null;
  const {url,title,protected:secured}=resource as {url?:unknown;title?:unknown;protected?:unknown};
  if(secured!==true||typeof url!=='string'||!url.startsWith('/api/v1/')||/[\\\u0000-\u0020\u007f]/.test(url))return null;
  try{
    const parsed=new URL(url,'https://fixrate.invalid');
    if(parsed.origin!=='https://fixrate.invalid'||!parsed.pathname.startsWith('/api/v1/'))return null;
  }catch{return null;}
  return {url,title:typeof title==='string'&&title.trim()?title.trim().slice(0,200):'Открыть защищённый просмотр'};
}
export const ActionCard=memo(function ActionCard({action:original,title,onChanged,attachments=[],timezone}:{action:ChatAction;title:string;onChanged:()=>void;attachments?:ChatAttachment[];timezone?:string}){
  const [resolved,setResolved]=useState<ChatAction|null>(null);
  const phase=(status:ChatAction['status'])=>status==='proposed'?0:status==='executing'?1:2;
  const action=resolved?.action_id===original.action_id&&phase(resolved.status)>phase(original.status)?resolved:original;
  const reportPhotos=action.tool_name==='report_attach_and_submit'&&!action.secret_fields?.length;
  const bindings=action.arguments.body?.photos;
  const previewPhotos=reportPhotos&&action.status==='proposed'&&Array.isArray(bindings)?bindings.flatMap((photo,index)=>{
    const id=photo?.attachment_id;
    if(typeof id!=='string'||!/^[0-9a-f-]{36}$/i.test(id))return [];
    const phase=photo.phase==='before'?'до работы':'после работы';
    return [{id,title:`Снимок ${index+1} · ${phase}`}];
  }):[];
  const [secrets,setSecrets]=useState<Record<string,string>>({});
  const [consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const expired=Date.parse(action.expires_at)<Date.now();
  const before=action.before_snapshot?.preview;
  const isAssignment=action.tool_name==='task_assign';
  const assignment=isAssignment?action.before_snapshot?.assignment:undefined;
  const assignmentBody=isAssignment?action.arguments.body:undefined;
  const assignmentTime=isAssignment?assignmentWindow(assignmentBody,assignment?.timezone??timezone):null;
  const assignmentReason=typeof assignmentBody?.reason==='string'?assignmentBody.reason:null;
  const worksheet=['order_table_apply','workbook_order_apply'].includes(action.tool_name)?before as WorksheetPreview|undefined:null;
  const move=worksheet?.requires_assigned_confirmation===true;
  const fields=isAssignment?[]:Object.entries({...action.arguments.path,...action.arguments.query,...action.arguments.body}).filter(([k,v])=>!action.secret_fields?.includes(k)&&k!=='idempotency_key'&&!technicalFields.has(k)&&
    !(executorActions.has(action.tool_name)&&['task_id','expected_revision'].includes(k))&&
    !(worksheet&&['changes','preview_digest','confirm_assigned'].includes(k))&&
    !(reportPhotos&&['execution_id','photos'].includes(k))&&v!==null&&v!==undefined&&!(typeof v==='object'&&Object.keys(v).length===0));
  const run=async(confirm:boolean)=>{setBusy(true);setError('');try{const result=confirm?(action.secret_fields?.length?await assistantApi.confirm(action,secrets):await assistantApi.confirm(action)):await assistantApi.reject(action.action_id);setResolved(result);setSecrets({});onChanged();const navigate=(result.result?.data as {navigate_to?:unknown}|undefined)?.navigate_to;if(navigate==='/assistant'||navigate==='/login'){notifyOtherTabs();window.location.assign(navigate);}}catch(e){setError(e instanceof Error?e.message:'Не удалось выполнить действие');onChanged();}finally{setBusy(false);}};
  const target=action.arguments.path?.equipment_id;
  const resultData=action.result?.data as {task?:{id?:unknown};submission?:string} | undefined;
  const taskTarget=typeof action.arguments.path?.task_id==='string'?action.arguments.path.task_id:typeof resultData?.task?.id==='string'?resultData.task.id:null;
  const verification=action.result?.verification;
  const resource=action.status==='succeeded'?protectedResource(action.result?.data):null;
  const summaryRows=action.status==='succeeded'&&!reportPhotos?resultSummaryRows(action.result?.data):[];
  const stateLabel=action.status==='succeeded'&&verification?
    verification.status!=='confirmed'?'Действие завершилось. Результат требует проверки':
      reportPhotos&&resultData?.submission==='draft_incomplete'?'Отчёт не отправлен':
      reportPhotos&&resultData?.submission==='submitted'?'Отчёт на проверке':'Выполнено и проверено':
    action.status==='proposed'&&expired?'Срок подтверждения истёк':states[action.status];
  const tone=action.status==='failed'?'danger':action.status==='stale'||action.status==='uncertain'||action.status==='proposed'&&expired||
    action.status==='succeeded'&&verification&&verification.status!=='confirmed'?'warning':
    action.status==='succeeded'?'success':action.status==='proposed'||action.status==='executing'?'accent':'muted';
  const detailsPresent=Object.keys(action.arguments).length>0||!worksheet&&before!=null||action.result?.data!==undefined||assignment&&action.explanation;
  return <section className="assistant-action-card" data-wide={worksheet?true:undefined} aria-label={`Предложение: ${title}`}>
    <header className="assistant-action-header">
      <div className="assistant-action-heading"><span className="assistant-action-icon"><Icon name={isAssignment?'workforce':'tasks'} size={19}/></span><h3>{title}</h3></div>
      <span role="status" className="assistant-action-status" data-tone={tone}>{stateLabel}</span>
    </header>
    <div className="assistant-action-body">
    {verification&&<p className="text-sm whitespace-pre-wrap">{verification.summary}</p>}
    {assignment?<div className="assistant-action-task">
      <span className="assistant-action-caption">Наряд</span>
      <p className="assistant-action-title">{assignment.taskTitle}</p>
      {assignment.taskCode&&<span className="assistant-action-code">{assignment.taskCode}</span>}
    </div>:reportPhotos&&action.status==='succeeded'?
      <details className="text-sm"><summary className="cursor-pointer text-muted">Привязка снимков</summary><p className="mt-2 whitespace-pre-wrap">{action.explanation}</p></details>:
      action.explanation&&<p className="whitespace-pre-wrap text-sm text-ink-soft">{action.explanation}</p>}
    {isAssignment&&<div className="assistant-action-facts">
      {assignment&&<div className="assistant-action-fact">
        <span className="assistant-action-caption"><Icon name="user" size={16}/>Исполнители</span>
        {assignment.crewName&&<span className="text-sm text-muted">{assignment.crewName}</span>}
        <ul aria-label="Исполнители" role="list">{assignment.workers.map((name,index)=><li key={index}>{name}</li>)}</ul>
      </div>}
      <div className="assistant-action-fact">
        <span className="assistant-action-caption"><Icon name="clock" size={16}/>{assignmentTime?'Время объекта':'Время из предложения'}</span>
        <p>{assignmentTime??[assignmentBody?.start_at,assignmentBody?.end_at].filter(time=>typeof time==='string').join(' — ')}</p>
      </div>
    </div>}
    {assignmentReason&&<p className="text-sm whitespace-pre-wrap text-ink-soft"><strong className="text-ink">Основание:</strong> {assignmentReason}</p>}
    {previewPhotos.length>0&&<div className="assistant-chat-resources" aria-label="Снимки в этом предложении">
      {previewPhotos.map(({id,title})=><ChatPhoto key={id} url={attachmentUrl(id)} title={title}/>)}
    </div>}
    {worksheet&&<OrderTablePreview items={worksheet.items}/>}
    {fields.length>0&&<dl className="assistant-action-fields">{fields.map(([key,v])=><div key={key}><dt>{labels[key]??key}</dt><dd>{attachments.find(a=>a.attachment_id===v)?.original_name??value(v)}</dd></div>)}</dl>}
    {(typeof target==='string'||taskTarget)&&<div className="assistant-action-links">
      {typeof target==='string'&&<Link to={`/equipment/${encodeURIComponent(target)}`}>Открыть оборудование</Link>}
      {taskTarget&&<Link to={`${executorActions.has(action.tool_name)?'/executor':''}/tasks/${encodeURIComponent(taskTarget)}`}>Открыть задание</Link>}
    </div>}
    {action.status==='uncertain'&&<Callout tone="warning">Ответ после выполнения потерян. Проверьте состояние в системе перед новой командой. Повторное подтверждение не запустит действие ещё раз.</Callout>}
    {action.result?.message&&<p className="text-sm whitespace-pre-wrap">{action.result.message}</p>}
    {resource&&<a className="assistant-resource" href={resource.url} target="_blank" rel="noopener noreferrer">{resource.title}<span className="block text-xs text-muted">Защищённый просмотр · доступ проверяется при открытии</span></a>}
    {summaryRows.length>0&&<dl className="space-y-2 rounded-xl border border-line/70 bg-surface-elevated/40 p-3 text-sm">{summaryRows.map(([k,v])=><div key={k} className="grid min-w-0 gap-1 sm:grid-cols-[160px_minmax(0,1fr)]"><dt className="text-muted">{k}</dt><dd className="min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{v}</dd></div>)}</dl>}
    {detailsPresent&&<details className="assistant-action-details">
      <summary>Технические детали</summary>
      <div>
        {Object.keys(action.arguments).length>0&&<><h4>Все параметры команды</h4><pre>{JSON.stringify(action.arguments,null,2)}</pre></>}
        {!worksheet&&before!=null&&<><h4>Данные до изменения</h4><pre>{JSON.stringify(before,null,2)}</pre></>}
        {assignment&&action.explanation&&<><h4>Текст предложения</h4><p className="whitespace-pre-wrap">{action.explanation}</p></>}
        {action.result?.data!==undefined&&<><h4>Результат действия</h4><pre>{JSON.stringify(action.result.data,null,2)}</pre></>}
      </div>
    </details>}
    </div>
    {(action.status==='proposed'||error)&&<div className="assistant-action-footer">
      {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}
      {action.status==='proposed'&&(expired?<Callout>Предложение истекло. Попросите подготовить новое.</Callout>:<fieldset disabled={busy}>
        {action.secret_fields?.map(field=><label key={field} className="block text-sm">{field==='current_password'?'Текущий пароль':field==='api_key'?'Ключ провайдера':field}<input type="password" autoComplete={field==='current_password'?'current-password':'off'} className="mt-2 block w-full rounded-lg border border-line bg-transparent p-2" value={secrets[field]??''} onChange={e=>setSecrets(v=>({...v,[field]:e.target.value}))}/><span className="mt-1 block text-xs text-muted">Ввод передаётся только при подтверждении, без записи в историю и передачи ИИ.</span></label>)}
        {!reportPhotos&&<label className="assistant-action-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>{move?'Подтверждаю перенос прежней бригады в указанный интервал':'Я проверил параметры и подтверждаю это изменение'}</label>}
        <p className="text-xs text-muted">На подтверждение этой карточки — 15 минут с момента создания.</p>
        <div className="assistant-action-buttons"><Button disabled={(!reportPhotos&&!consent)||action.secret_fields?.some(field=>!secrets[field])} onClick={()=>void run(true)}>{busy?'Выполнение…':move?'Подтвердить перенос':reportPhotos?'Подтвердить прикрепление и сдачу':'Подтвердить и выполнить'}</Button><Button variant="ghost" onClick={()=>void run(false)}>Отклонить</Button></div>
      </fieldset>)}
    </div>}
  </section>;
});
