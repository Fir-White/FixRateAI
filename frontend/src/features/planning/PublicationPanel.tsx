import { useRef,useState } from 'react';
import { publicationApi as api,type ExecutionProfile,type PublicationProposal,type PublicationChange } from '@/shared/api/publication';
import type { DraftRecord } from '@/shared/api/draftPlans';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { formatDateTime } from '@/shared/lib/format';
import { Button } from '@/shared/ui/Button';
import { FieldCaption,Input,Select,Textarea } from '@/shared/ui/Form';
import { ErrorState,LoadingState } from '@/shared/ui/States';
import { Callout } from '@/shared/ui/Callout';
import { PlanningPages } from './PlanningChoices';

const states={prepared:'Ожидает утверждения',approved:'Утверждено',rejected:'Отклонено',published:'Опубликовано'};
const empty=(row_number:number):ExecutionProfile=>({row_number,instructions:'',safety_notes:'',methodology_ref:'',engineer_note:'',checklist:[]});
const failure=(e:unknown)=>e instanceof Error?e.message:'Не удалось выполнить действие';

export default function PublicationPanel({record,mayEdit,mayApprove,timezone}:{record:DraftRecord;mayEdit:boolean;mayApprove:boolean;timezone:string}) {
  const [editing,setEditing]=useState(false),[profiles,setProfiles]=useState<Record<number,ExecutionProfile>>({}),[reason,setReason]=useState(''),[scope,setScope]=useState('');
  const [proposal,setProposal]=useState<PublicationProposal|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[refresh,setRefresh]=useState(0),[offset,setOffset]=useState(0);
  const retry=useRef<{body:string;key:string}|null>(null);
  const history=useApiQuery(()=>api.list(record.draft_id,offset),[record.draft_id,offset,refresh]);
  const run=async(fn:()=>Promise<PublicationProposal>)=>{if(busy)return;setBusy(true);setError('');try{setProposal(await fn());setRefresh(n=>n+1);}catch(e){setError(failure(e));}finally{setBusy(false);}};
  return <section className="min-w-0 space-y-4 rounded-xl border border-line p-4" aria-label="Утверждение и публикация плана">
    <h4 className="font-semibold">Утверждение и публикация</h4>
    <p className="text-sm">Подготовьте инструкции и чек-листы. Главный инженер проверит состав, часы, даты, бригады и утвердит предложение. Публикация создаст задания и уведомит исполнителей.</p>
    <Callout>Утверждается выбранный состав и горизонт. Остальные строки каталога не считаются готовыми. Действующие задания сохраняются; повторная выдача уже опубликованных обязательств блокируется.</Callout>
    {mayEdit&&<Button variant="secondary" aria-expanded={editing} onClick={()=>setEditing(v=>!v)}>Подготовить предложение к публикации</Button>}
    {editing&&mayEdit&&<fieldset disabled={busy} className="min-w-0 space-y-4"><legend className="sr-only">Подготовка инструкций и состава</legend>
      <Profiles id={record.draft_id} revision={record.revision} values={profiles} onChange={profile=>setProfiles(p=>({...p,[profile.row_number]:profile}))}/>
      <label className="block"><FieldCaption>Состав и границы публикации</FieldCaption><Textarea aria-label="Состав и границы публикации" value={scope} maxLength={2000} onChange={e=>setScope(e.target.value)}/></label>
      <label className="block"><FieldCaption>Основание предложения</FieldCaption><Textarea aria-label="Основание предложения" value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label>
      <Button disabled={!scope.trim()||!reason.trim()} onClick={()=>void run(()=>{
        const selected=Object.values(profiles).map(p=>({...p,checklist:p.checklist.filter(c=>c.text.trim())})).sort((a,b)=>a.row_number-b.row_number),body=JSON.stringify({profiles:selected,reason,scope});
        if(retry.current?.body!==body)retry.current={body,key:crypto.randomUUID()};
        return api.prepare(record.draft_id,{expected_revision:record.revision,idempotency_key:retry.current!.key,reason,scope_note:scope,profiles:selected}).then(p=>{retry.current=null;setEditing(false);return p;});
      })}>Сохранить предложение на утверждение</Button>
    </fieldset>}
    {error&&<p role="alert">{error} Введённые данные сохранены в форме.</p>}
    {history.status==='loading'&&<LoadingState/>}{history.status==='error'&&<ErrorState description={history.error}/>}
    {history.status==='success'&&<><ul className="space-y-2" aria-label="История предложений">{history.data.items.map(item=><li key={item.proposal_id}><Button variant="ghost" disabled={busy} onClick={()=>void run(()=>api.get(item.proposal_id))}>{formatDateTime(item.created_at,timezone)} · версия {item.base_revision} · {states[item.state]}</Button></li>)}</ul><PlanningPages offset={offset} total={history.data.total} onPage={setOffset}/></>}
    {proposal&&<Proposal key={proposal.proposal_id} value={proposal} mayApprove={mayApprove} timezone={timezone} busy={busy} run={run}/>}
  </section>;
}

function Profiles({id,revision,values,onChange}:{id:string;revision:number;values:Record<number,ExecutionProfile>;onChange:(profile:ExecutionProfile)=>void}) {
  const [offset,setOffset]=useState(0),[selected,setSelected]=useState<number|null>(null);
  const query=useApiQuery(()=>api.profiles(id,revision,offset),[id,revision,offset]);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  const value=selected!==null?(values[selected]??empty(selected)):null;
  return <div className="min-w-0 space-y-3"><p className="text-sm">Корневых строк: {query.data.total}. Для каждой нужны инструкция, безопасность, методика и хотя бы один пункт чек-листа. Содержимое задаёт инженер.</p>
    <ul className="space-y-2">{query.data.items.map(row=><li key={row.row_number}><Button variant={selected===row.row_number?'primary':'secondary'} onClick={()=>setSelected(row.row_number)}>{row.code} · {row.title}</Button>{row.included_rows.length>0&&<p className="text-xs text-muted">В составе: строки {row.included_rows.join(', ')}. Учтите их в инструкции и чек-листе.</p>}</li>)}</ul><PlanningPages offset={offset} total={query.data.total} onPage={n=>{setOffset(n);setSelected(null);}}/>
    {value&&<section className="min-w-0 space-y-3 border-t border-line pt-3" aria-label="Инструкция для публикации"><h5 className="font-semibold">Строка {value.row_number}</h5>
      {([['instructions','Инструкция выполнения'],['safety_notes','Меры безопасности'],['methodology_ref','Основание инструкции'],['engineer_note','Примечание инженера']] as const).map(([key,label])=><label className="block" key={key}><FieldCaption>{label}</FieldCaption><Textarea aria-label={label} maxLength={key==='instructions'?10000:key==='safety_notes'?5000:2000} value={value[key]} onChange={e=>onChange({...value,[key]:e.target.value})}/></label>)}
      <label className="block"><FieldCaption>Чек-лист: один пункт на строку</FieldCaption><Textarea aria-label="Чек-лист: один пункт на строку" maxLength={50000} value={value.checklist.map(c=>c.text).join('\n')} onChange={e=>onChange({...value,checklist:e.target.value.split('\n').map((text,index)=>({...value.checklist[index]??{answer_kind:'boolean' as const,required:true,visual_verifiability:'not_verifiable' as const,photo_required:false},text}))})}/></label>
      <Checklist key={selected} value={value} onChange={onChange}/>
    </section>}
  </div>;
}

function Proposal({value:p,mayApprove,timezone,busy,run}:{value:PublicationProposal;mayApprove:boolean;timezone:string;busy:boolean;run:(fn:()=>Promise<PublicationProposal>)=>Promise<void>}) {
  const [reason,setReason]=useState(''),[consent,setConsent]=useState(false),[publishConsent,setPublishConsent]=useState(false);
  const publishKey=useRef(crypto.randomUUID());
  return <section className="min-w-0 space-y-4 border-t border-line pt-4" aria-label="Предложение публикации">
    <p role="status" aria-label="Состояние предложения">{states[p.state]} · версия {p.base_revision}</p>
    <p className="text-sm">Добавить заданий: {p.summary.added_tasks}; изменить: {p.summary.changed_tasks}; отменить: {p.summary.cancelled_tasks}. Всего {p.summary.total_person_hours} чел.-ч, {p.summary.occurrences} работ, {p.summary.segments} сегментов.</p>
    <p className="text-sm">Строк выбрано: {p.summary.selected_rows}; вне состава: {p.summary.unselected_rows}. Месяцы: {p.summary.months.join(', ')||'нет размещения'}.</p>
    <p className="whitespace-pre-wrap text-sm">{p.scope_note}</p><p className="text-xs text-muted">Предложение действительно до {formatDateTime(p.expires_at,timezone)}. При изменении исходных данных потребуется новое предложение.</p>
    <ul className="space-y-2 text-sm">{p.blockers.map((item,i)=><li key={i}>{item.message}</li>)}</ul>{p.blocker_count>p.blockers.length&&<p>Всего замечаний: {p.blocker_count}. Показаны первые {p.blockers.length}.</p>}
    <Changes proposal={p.proposal_id} timezone={timezone}/>
    {p.decision_reason&&<p className="whitespace-pre-wrap text-sm">Решение главного инженера: {p.decision_reason}</p>}
    {mayApprove&&['prepared','approved'].includes(p.state)&&<fieldset disabled={busy} className="min-w-0 space-y-3"><legend className="sr-only">Решение главного инженера</legend>
      <label className="block"><FieldCaption>Основание решения главного инженера</FieldCaption><Textarea aria-label="Основание решения главного инженера" value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label>
      {p.state==='prepared'&&<><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>Проверены выбранный состав, ограничения, инструкции, чек-листы и назначения</span></label><Button disabled={!p.can_approve||!consent||!reason.trim()} onClick={()=>void run(()=>api.approve(p.proposal_id,p.proposal_digest,reason))}>Утвердить предложение</Button></>}
      <Button variant="secondary" disabled={!reason.trim()} onClick={()=>void run(()=>api.reject(p.proposal_id,p.proposal_digest,reason))}>Отклонить предложение</Button>
      {p.state==='approved'&&p.approval_token&&<><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={publishConsent} onChange={e=>setPublishConsent(e.target.checked)}/><span>Создать утверждённые задания и назначения в рабочем календаре и уведомить исполнителей</span></label><Button disabled={!publishConsent} onClick={()=>void run(()=>api.publish(p.proposal_id,p.proposal_digest,p.approval_token!,publishKey.current))}>Опубликовать утверждённый план</Button></>}
    </fieldset>}
    {!mayApprove&&p.state!=='published'&&<p className="text-sm">Решение и публикация доступны главному инженеру.</p>}
    {p.state==='published'&&<Callout>Задания опубликованы. Они доступны в календаре ТО и списке заданий; исполнители получили уведомления.</Callout>}
  </section>;
}

function Checklist({value,onChange}:{value:ExecutionProfile;onChange:(profile:ExecutionProfile)=>void}) {
  const [offset,setOffset]=useState(0);
  return <details><summary className="cursor-pointer text-sm">Типы ответов и фотофиксация</summary><ul className="mt-3 space-y-4">{value.checklist.slice(offset,offset+25).map((item,index)=>{
    const position=offset+index,change=(fields:Partial<typeof item>)=>onChange({...value,checklist:value.checklist.map((c,i)=>i===position?{...c,...fields}:c)});
    return <li className="space-y-2 rounded-xl border border-line p-3" key={position}><p className="text-sm">{position+1}. {item.text||'Новый пункт'}</p>
      <label className="block"><FieldCaption>Тип ответа, пункт {position+1}</FieldCaption><Select aria-label={`Тип ответа, пункт ${position+1}`} value={item.answer_kind} onChange={e=>change({answer_kind:e.target.value as typeof item.answer_kind})}><option value="boolean">Отметка выполнения</option><option value="number">Числовое значение</option><option value="text">Текст</option></Select></label>
      {item.answer_kind==='number'&&<label className="block"><FieldCaption>Единица измерения, пункт {position+1}</FieldCaption><Input aria-label={`Единица измерения, пункт ${position+1}`} value={item.unit??''} maxLength={64} onChange={e=>change({unit:e.target.value})}/></label>}
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={item.required} onChange={e=>change({required:e.target.checked})}/><span>Обязательный ответ, пункт {position+1}</span></label>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={item.photo_required} onChange={e=>change({photo_required:e.target.checked})}/><span>Фото до и после, пункт {position+1}</span></label>
      <label className="block"><FieldCaption>Что видно на фото, пункт {position+1}</FieldCaption><Select aria-label={`Что видно на фото, пункт ${position+1}`} value={item.visual_verifiability} onChange={e=>change({visual_verifiability:e.target.value as typeof item.visual_verifiability})}><option value="not_verifiable">Не подтверждается фотографией</option><option value="partial">Подтверждается частично</option><option value="visible">Подтверждается визуально</option></Select></label>
    </li>;
  })}</ul><PlanningPages offset={offset} total={value.checklist.length} onPage={setOffset}/></details>;
}

function Changes({proposal,timezone}:{proposal:string;timezone:string}) {
  const [offset,setOffset]=useState(0),[selected,setSelected]=useState<string|null>(null),[checkOffset,setCheckOffset]=useState(0);
  const query=useApiQuery(()=>api.changes(proposal,offset),[proposal,offset]);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  const item:PublicationChange|undefined=query.data.items.find(i=>i.item_id===selected);
  return <div className="min-w-0 space-y-3"><h5 className="font-semibold">Изменения рабочего графика</h5><ul className="space-y-3" aria-label="Изменения публикации">{query.data.items.map(item=><li className="break-words rounded-xl border border-line p-3" key={item.item_id}><p className="font-semibold">Добавить: {item.operation_code} · {item.title}</p><p className="text-sm">{item.person_hours} чел.-ч · {item.start_at?formatDateTime(item.start_at,timezone):'Не размещено'} — {formatDateTime(item.end_at,timezone)}</p><p className="text-sm">{item.equipment_ids.map(id=>query.data.equipment_labels[id]??'Оборудование').join(', ')}</p><p className="text-sm">{item.worker_ids.map(id=>query.data.worker_labels[id]??'Сотрудник').join(', ')}</p><Button variant="ghost" onClick={()=>{setSelected(item.item_id===selected?null:item.item_id);setCheckOffset(0);}}>Проверить инструкцию и чек-лист</Button></li>)}</ul><PlanningPages offset={offset} total={query.data.total} onPage={n=>{setOffset(n);setSelected(null);}}/>
    {item&&<section className="min-w-0 space-y-2 text-sm" aria-label="Утверждаемая инструкция"><p className="whitespace-pre-wrap">{item.execution.instructions}</p><p className="whitespace-pre-wrap">Безопасность: {item.execution.safety_notes}</p><p className="whitespace-pre-wrap">Методика: {item.execution.methodology_ref}</p><p className="whitespace-pre-wrap">Примечание: {item.execution.engineer_note||'Нет'}</p><ul>{item.execution.checklist.slice(checkOffset,checkOffset+25).map((c,i)=><li key={checkOffset+i}>{checkOffset+i+1}. {c.text}{c.unit&&` (${c.unit})`}{c.photo_required?' · Фото до и после':''}</li>)}</ul><PlanningPages offset={checkOffset} total={item.execution.checklist.length} onPage={setCheckOffset}/></section>}
  </div>;
}
