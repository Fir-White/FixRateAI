import { lazy,Suspense,useDeferredValue,useRef,useState } from 'react';
import { draftPlansApi as api,type DraftRecord,type GenerationInput,type GenerationPreview,type PlanValidation,type WorkOccurrence,type WorkSegment } from '@/shared/api/draftPlans';
import { catalogImportsApi } from '@/shared/api/catalogImports';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { todayAt,formatDate,formatDateTime } from '@/shared/lib/format';
import { dateTimeFormatter } from '@/shared/lib/dateTimeFormatter';
import { Button } from '@/shared/ui/Button';
import { FieldCaption,Input,Select,Textarea } from '@/shared/ui/Form';
import { LoadingState,ErrorState } from '@/shared/ui/States';
import { Callout } from '@/shared/ui/Callout';
import { Drawer } from '@/shared/ui/Drawer';
import { PlanningChoices,PlanningPages } from './PlanningChoices';
import { splitPersonHours } from './segmentHours';
import './draft-plans.css';
import { JourneySteps } from '@/shared/ui/JourneySteps';
import type { CatalogWorkspace } from '@/features/equipment/CatalogImports';
import { PolicyFields,newPolicy } from './PolicyFields';
import PlanPolicyPanel from './PlanPolicyPanel';
const OptimizationPanel=lazy(()=>import('./OptimizationPanel'));
const PublicationPanel=lazy(()=>import('./PublicationPanel'));
const UndoPlanPanel=lazy(()=>import('./UndoPlanPanel'));
const PlanLoadPanel=lazy(()=>import('./PlanLoadPanel'));

const failure=(error:unknown)=>error instanceof Error?error.message:'Не удалось выполнить действие';
const titleForStatus={valid:'Проверенные ограничения соблюдены',incomplete:'Нужны данные или размещение',invalid:'Обнаружены нарушения'};

export function CatalogPlans({id,mayEdit,mayApprove=false,timezone,workspace}:{id:string;mayEdit:boolean;mayApprove?:boolean;timezone:string;workspace?:CatalogWorkspace}) {
  const [create,setCreate]=useState(false),[refresh,setRefresh]=useState(0),[offset,setOffset]=useState(0),[selected,setSelected]=useState<DraftRecord|null>(null),[head,setHead]=useState(0);
  const query=useApiQuery(()=>api.list(id,offset),[id,offset,refresh],undefined,`draft-plans:${id}:${offset}`);
  const pick=(record:DraftRecord)=>{setSelected(record);setHead(record.revision);workspace?.selectDraft(record);};
  if(workspace?.draftId)return <section aria-label="Версии плана каталога" className="space-y-4"><Button variant="ghost" onClick={()=>workspace.selectDraft(null)}>← Все планы этого файла</Button><LinkedPlan id={id} workspace={workspace} timezone={timezone} mayEdit={mayEdit} mayApprove={mayApprove}/></section>;
  return <section className="draft-plans space-y-4 border-t border-line pt-4" aria-label="Версии плана каталога">
    <h3 className="text-lg font-semibold">Черновики планов</h3>
    <Callout>Год и месяц показывают одну версию работ. Изменения сохраняются новой версией. Публикация и резервирование людей выполняются отдельным действием после утверждения.</Callout>
    {mayEdit&&<Button variant="secondary" aria-expanded={create} onClick={()=>setCreate(v=>!v)}>Подготовить новый черновик</Button>}
    {create&&<CreateDraft id={id} timezone={timezone} onSaved={record=>{setCreate(false);setOffset(0);setRefresh(n=>n+1);pick(record);}}/>}
    {query.status==='loading'&&<LoadingState/>}{query.status==='error'&&<ErrorState description={query.error}/>}
    {query.status==='success'&&<><ul className="space-y-2">{query.data.items.map(record=><li key={record.draft_id}><Button variant={selected?.draft_id===record.draft_id?'primary':'secondary'} onClick={()=>pick(record)}>{record.title} · версия {record.revision} · {record.total_person_hours} чел.-ч</Button></li>)}</ul>{!query.data.total&&<p>Сохранённых вариантов пока нет.</p>}<PlanningPages offset={offset} total={query.data.total} onPage={setOffset}/></>}
    {selected&&!workspace&&<SavedPlan key={`${selected.draft_id}:${selected.revision}`} record={selected} timezone={timezone} mayApprove={mayApprove} mayEdit={mayEdit&&selected.revision===head} onPickVersion={setSelected} onSaved={record=>{setRefresh(n=>n+1);pick(record);}}/>}
  </section>;
}

function LinkedPlan({id,workspace,timezone,mayEdit,mayApprove}:{id:string;workspace:CatalogWorkspace;timezone:string;mayEdit:boolean;mayApprove:boolean}) {
  const query=useApiQuery(async()=>{
    const versions=await api.versions(workspace.draftId,0),head=versions.items[0];
    if(!head||head.import_id!==id)throw new Error('План не найден в выбранном файле. Вернитесь к списку планов.');
    const record=workspace.draftRevision&&workspace.draftRevision!==head.revision?(await api.overview(workspace.draftId,workspace.draftRevision)).record:head;
    if(record.import_id!==id)throw new Error('План относится к другому файлу.');
    return {record,head:head.revision};
  },[id,workspace.draftId,workspace.draftRevision],undefined,`linked-plan:${id}:${workspace.draftId}:${workspace.draftRevision}`);
  if(query.status==='loading')return <LoadingState label="Открытие сохранённого плана"/>;
  if(query.status==='error')return <ErrorState description={query.error}/>;
  return <SavedPlan key={`${query.data.record.draft_id}:${query.data.record.revision}`} record={query.data.record} timezone={timezone} mayApprove={mayApprove} mayEdit={mayEdit&&query.data.record.revision===query.data.head} onPickVersion={workspace.selectDraft} onSaved={workspace.selectDraft} workspace={workspace}/>;
}

function CreateDraft({id,timezone,onSaved}:{id:string;timezone:string;onSaved:(r:DraftRecord)=>void}) {
  const year=todayAt(timezone).slice(0,4);
  const [input,setInput]=useState<GenerationInput>({import_id:id,starts_on:`${year}-01-01`,ends_on:`${year}-12-31`,row_numbers:[],expansion:'source_january',policy:newPolicy()});
  const [labels,setLabels]=useState<Record<number,string>>({}),[selectedOffset,setSelectedOffset]=useState(0),[search,setSearch]=useState(''),[offset,setOffset]=useState(0);
  const [preview,setPreview]=useState<GenerationPreview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[title,setTitle]=useState('План СВиК'),[reason,setReason]=useState('');
  const key=useRef(crypto.randomUUID());const needle=useDeferredValue(search);
  const choices=useApiQuery(()=>api.sources(id,needle,offset),[id,needle,offset],undefined,`draft-source-choices:${JSON.stringify([id,needle,offset])}`);
  const change=(next:GenerationInput)=>{setInput(next);setPreview(null);setError('');key.current=crypto.randomUUID();};
  const setPolicy=(part:Partial<GenerationInput['policy']>)=>change({...input,policy:{...input.policy,...part}});
  return <section className="space-y-4 rounded-xl border border-line p-4" aria-label="Подготовка черновика плана">
    <fieldset disabled={busy} className="min-w-0 space-y-4"><legend className="mb-3 font-semibold">Исходные данные и горизонт</legend>
      <div className="grid gap-3 sm:grid-cols-2"><label><FieldCaption>Начало горизонта</FieldCaption><Input aria-label="Начало горизонта" type="date" value={input.starts_on} onChange={e=>change({...input,starts_on:e.target.value})}/></label><label><FieldCaption>Конец горизонта</FieldCaption><Input aria-label="Конец горизонта" type="date" value={input.ends_on} onChange={e=>change({...input,ends_on:e.target.value})}/></label></div>
      <label className="block"><FieldCaption>Основание дат</FieldCaption><Select aria-label="Основание дат" value={input.expansion} onChange={e=>change({...input,expansion:e.target.value as GenerationInput['expansion']})}><option value="source_january">Подтверждённые отметки исходного января</option><option value="confirmed_rule">Подтверждённые календарные правила с опорной датой</option></Select></label>
      <p className="text-sm text-muted">Выбираются только подготовленные строки. Для включённой операции выберите также родительскую работу. Полнота оценивается в пределах выбранных строк.</p>
      <Button variant="secondary" onClick={async()=>{setBusy(true);setError('');try{const progress=await catalogImportsApi.preparation(id);change({...input,row_numbers:progress.items.filter(r=>r.prepared).map(r=>r.row_number)});}catch(e){setError(failure(e));}finally{setBusy(false);}}}>Выбрать все подготовленные строки</Button>
      <label className="block"><FieldCaption>Поиск подготовленных операций</FieldCaption><Input aria-label="Поиск подготовленных операций" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/></label>
      {choices.status==='loading'&&<LoadingState/>}{choices.status==='error'&&<ErrorState description={choices.error}/>}
      {choices.status==='success'&&<><ul className="space-y-2">{choices.data.items.map(item=><li key={item.row_number}><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={input.row_numbers.includes(item.row_number)} onChange={e=>{setLabels(m=>({...m,[item.row_number]:`${item.code} · ${item.title}`}));change({...input,row_numbers:e.target.checked?[...input.row_numbers,item.row_number]:input.row_numbers.filter(n=>n!==item.row_number)});}}/><span>{item.code} · {item.title} · строка {item.row_number}</span></label></li>)}</ul>{!choices.data.total&&<p>Подготовленных строк нет. Сначала подтвердите смысл, оборудование и норму в редакторе операции.</p>}<PlanningPages offset={offset} total={choices.data.total} onPage={setOffset}/></>}
      <p className="font-semibold">Выбрано строк: {input.row_numbers.length}</p>
      <ul className="space-y-1 text-sm">{input.row_numbers.slice(selectedOffset,selectedOffset+25).map(n=><li key={n}>{labels[n]??`Строка Excel ${n}`} <Button variant="ghost" onClick={()=>change({...input,row_numbers:input.row_numbers.filter(i=>i!==n)})}>Убрать строку {n}</Button></li>)}</ul><PlanningPages offset={selectedOffset} total={input.row_numbers.length} onPage={setSelectedOffset}/>
      <PolicyFields value={input.policy} onChange={policy=>change({...input,policy})} timezone={timezone}/>
      <details><summary>Границы событий день / ночь</summary><p className="my-2 text-sm text-muted">Нужны для подтверждённых двух событий в сутки. Ночной слот заканчивается в начале дневного следующей даты. Они не определяют численность или длину смен сотрудников.</p><div className="grid gap-3 sm:grid-cols-2">{(['day_start_minute','night_start_minute'] as const).map((field,index)=><label key={field}><FieldCaption>{index?'Ночное событие начинается':'Дневное событие начинается'}</FieldCaption><Input aria-label={index?'Ночное событие начинается':'Дневное событие начинается'} type="time" value={input.policy[field]===null?'':`${String(Math.floor(input.policy[field]!/60)).padStart(2,'0')}:${String(input.policy[field]!%60).padStart(2,'0')}`} onChange={e=>{const [h,m]=e.target.value.split(':').map(Number);setPolicy({[field]:e.target.value?h*60+m:null});}}/></label>)}</div></details>
      <Button disabled={!input.row_numbers.length||!input.starts_on||!input.ends_on} variant="secondary" onClick={async()=>{setBusy(true);setError('');setPreview(null);try{setPreview(await api.preview(input));key.current=crypto.randomUUID();}catch(e){setError(failure(e));}finally{setBusy(false);}}}>{busy?'Расчёт…':'Предпросмотр работ'}</Button>
      {preview&&<div className="space-y-3" aria-label="Предпросмотр работ"><p>{preview.total_occurrences} корневых работ · {preview.total_segments} сегментов · {preview.total_person_hours} чел.-ч</p><p className="text-sm text-muted">За пределами выбранного состава осталось строк: {preview.unselected_rows}. Весь каталог этим расчётом не объявляется покрытым.</p><ul className="space-y-2 text-sm">{preview.issues.map((issue,index)=><li key={index}>{issue.row_number&&`Строка ${issue.row_number}: `}{issue.message}</li>)}</ul>{preview.total_issues>preview.issues.length&&<p>Показаны первые {preview.issues.length} из {preview.total_issues} замечаний.</p>}
        <label className="block"><FieldCaption>Название черновика</FieldCaption><Input aria-label="Название черновика" maxLength={256} value={title} onChange={e=>{setTitle(e.target.value);key.current=crypto.randomUUID();}}/></label>
        <label className="block"><FieldCaption>Основание создания</FieldCaption><Textarea aria-label="Основание создания" maxLength={2000} value={reason} onChange={e=>{setReason(e.target.value);key.current=crypto.randomUUID();}}/></label>
        <Button disabled={!preview.can_save||!title.trim()||!reason.trim()} onClick={async()=>{setBusy(true);setError('');try{onSaved(await api.create(input,preview.input_sha256,key.current,title,reason));}catch(e){setError(failure(e));}finally{setBusy(false);}}}>Сохранить новую версию плана</Button>
      </div>}
    </fieldset>{error&&<p role="alert"><Callout tone="danger">{error}</Callout></p>}
  </section>;
}

export function SavedPlan({record,timezone,mayEdit,mayApprove,onPickVersion,onSaved,workspace}:{record:DraftRecord;timezone:string;mayEdit:boolean;mayApprove:boolean;onPickVersion:(r:DraftRecord)=>void;onSaved:(r:DraftRecord)=>void;workspace?:CatalogWorkspace}) {
  const [undoOpen,setUndoOpen]=useState(false),[undoVisited,setUndoVisited]=useState(false),[loadVisited,setLoadVisited]=useState(false);
  const [period,setPeriod]=useState(''),[search,setSearch]=useState(''),[offset,setOffset]=useState(0),[root,setRoot]=useState<string|null>(null),[history,setHistory]=useState(false);
  const [validation,setValidation]=useState<PlanValidation|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const needle=useDeferredValue(search);
  const overview=useApiQuery(()=>api.overview(record.draft_id,record.revision),[record.draft_id,record.revision],undefined,`draft-overview:${record.draft_id}:${record.revision}`);
  const rows=useApiQuery(()=>api.occurrences(record.draft_id,record.revision,offset,needle,period),[record.draft_id,record.revision,offset,needle,period],undefined,`draft-occurrences:${JSON.stringify([record.draft_id,record.revision,offset,needle,period])}`);
  const work=<>
    <PlanPolicyPanel record={record} mayEdit={mayEdit} timezone={timezone} onSaved={onSaved}/>
    {overview.status==='loading'&&<LoadingState/>}{overview.status==='error'&&<ErrorState description={overview.error}/>}
    {overview.status==='success'&&<><div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-4" aria-label="Месяцы одной версии"><Button variant={!period?'primary':'secondary'} onClick={()=>{setPeriod('');setOffset(0);}}>Весь горизонт · {record.total_person_hours} чел.-ч</Button>{overview.data.months.map(month=><Button key={month.month} variant={period===month.month?'primary':'secondary'} onClick={()=>{setPeriod(month.month);setOffset(0);}}>{month.month} · обязательства {month.due_person_hours} · размещено {month.planned_person_hours} чел.-ч</Button>)}</div>
      <ValidationReport key={validation?.input_sha256??'stored'} value={validation??overview.data.validation}/>
    </>}
    <Button variant="secondary" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{setValidation(await api.validate(record.draft_id,record.revision));}catch(e){setError(failure(e));}finally{setBusy(false);}}}>{busy?'Проверка…':'Проверить по текущим данным'}</Button>{error&&<p role="alert">{error}</p>}
    <label className="block"><FieldCaption>Поиск работ версии</FieldCaption><Input aria-label="Поиск работ версии" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/></label>
    {rows.status==='loading'&&<LoadingState/>}{rows.status==='error'&&<ErrorState description={rows.error}/>}
    {rows.status==='success'&&<><ul className="space-y-3" aria-label="Работы версии плана">{rows.data.items.map(item=><li className="rounded-xl border border-line p-4" key={item.occurrence_id}><Button variant="ghost" onClick={()=>setRoot(item.occurrence_id)}>{item.operation_code} · {item.title}</Button><p className="mt-2 text-sm">{item.maintenance_type} · {formatDate(item.earliest_date)} — {formatDate(item.latest_date)} · {item.total_person_hours} чел.-ч · бригада {item.crew_size}</p><p className="text-xs text-muted">{item.source_kind==='regulation'?'Действующий регламент':`Строка ${item.source_row}, решение v${item.decision_revision}`} · {item.source_slot==='day'?'Дневное событие':item.source_slot==='night'?'Ночное событие':'В пределах допустимых дат'}</p></li>)}</ul>{!rows.data.total&&<p>В этом представлении работ нет.</p>}<PlanningPages offset={offset} total={rows.data.total} onPage={setOffset}/></>}
    {workspace&&<div className="journey-footer"><span className="text-sm text-muted">Проверьте состав и перейдите к распределению дат и бригад.</span><Button onClick={()=>workspace.selectPlanView('schedule')}>Распределить работы →</Button></div>}
  </>;
  const optimization=<Suspense fallback={<LoadingState/>}><OptimizationPanel simple={!!workspace} record={record} timezone={timezone} mayEdit={mayEdit} onSaved={onSaved}/>{workspace&&<div className="journey-footer"><Button variant="ghost" onClick={()=>workspace.selectPlanView('work')}>← Состав работ</Button><Button onClick={()=>workspace.selectPlanView('load')}>Проверить нагрузку →</Button></div>}</Suspense>;
  const publication=<Suspense fallback={<LoadingState/>}><PublicationPanel record={record} timezone={timezone} mayEdit={mayEdit} mayApprove={mayApprove}/></Suspense>;
  const load=<Suspense fallback={<LoadingState/>}><PlanLoadPanel record={record} timezone={timezone} month={workspace?.loadMonth} onMonth={workspace?.selectLoadMonth}/>{workspace&&<div className="journey-footer"><Button variant="ghost" onClick={()=>workspace.selectPlanView('schedule')}>← Даты и бригады</Button><Button onClick={()=>workspace.selectPlanView('publish')}>К утверждению и выпуску →</Button></div>}</Suspense>;
  return <section className="space-y-5" aria-label="Сохранённая версия плана"><header className="journey-panel-heading"><h3 className="font-semibold">{record.title} · версия {record.revision}</h3><p className="text-sm">{formatDate(record.starts_on)} — {formatDate(record.ends_on)} · {record.author_name} · {record.occurrence_count} работ · {record.total_person_hours} чел.-ч</p></header>
    {!mayEdit&&<p className="text-sm text-muted">Открыта версия для просмотра. Изменять можно последнюю версию при наличии прав.</p>}
    {workspace?<JourneySteps label="Этапы работы с планом" value={workspace.planView} onChange={workspace.selectPlanView} steps={[
      {id:'work',title:'Состав работ',content:()=>work},
      {id:'schedule',title:'Даты и бригады',description:'Рассчитайте варианты, проверьте назначения и примените выбранный вариант в новую версию.',content:()=>optimization},
      {id:'load',title:'Нагрузка',content:()=>load},
      {id:'publish',title:'Утверждение и выпуск',content:()=>publication},
    ]}/>:<>{work}{optimization}<details onToggle={e=>{if(e.currentTarget.open)setLoadVisited(true);}}><summary>Нагрузка выбранной версии</summary>{loadVisited&&load}</details>{publication}</>}
    {record.change_kind==='undo'&&<div role="status"><Callout>Изменение версии {record.undone_revision} отменено. Восстановлено содержимое версии {record.restored_revision}; история сохранена.</Callout></div>}
    {mayEdit&&record.revision>1&&record.change_kind!=='undo'&&<><Button variant="ghost" aria-expanded={undoOpen} onClick={()=>{setUndoOpen(v=>!v);setUndoVisited(true);}}>Отменить последнее своё изменение</Button>{undoVisited&&<div hidden={!undoOpen} inert={!undoOpen}><Suspense fallback={<LoadingState/>}><UndoPlanPanel record={record} onSaved={onSaved}/></Suspense></div>}</>}
    <Button variant="ghost" aria-expanded={history} onClick={()=>setHistory(v=>!v)}>История версий плана</Button>{history&&<PlanVersions id={record.draft_id} onPick={onPickVersion}/>}
    <Drawer open={root!==null} onClose={()=>setRoot(null)} title="Работа и сегменты плана">{root&&<RootSegments id={record.draft_id} revision={record.revision} rootId={root} timezone={timezone} mayEdit={mayEdit} onSaved={onSaved}/>}</Drawer>
  </section>;
}

function ValidationReport({value}:{value:PlanValidation}) {
  const [days,setDays]=useState(false),[offset,setOffset]=useState(0);
  return <section className="space-y-3 rounded-xl border border-line p-4" aria-label="Результат проверки плана"><h4 className="font-semibold">{titleForStatus[value.status]}</h4><p>Размещено {value.placed_person_hours} из {value.total_person_hours} чел.-ч. Неразмещённых сегментов: {value.unplaced_segments}.</p><p className="text-xs text-muted">Снимок проверки: {value.checked_at}. Публикация не выполнялась.</p><ul className="space-y-2 text-sm">{value.issues.map((issue,index)=><li key={index}>{issue.row_number&&`Строка ${issue.row_number}: `}{issue.message}</li>)}</ul>{value.total_issues>value.issues.length&&<p className="text-sm">Показаны первые {value.issues.length} из {value.total_issues} замечаний. После исправлений повторите проверку.</p>}
    <Button variant="ghost" aria-expanded={days} onClick={()=>setDays(v=>!v)}>Подневная нагрузка</Button>{days&&<><ul className="space-y-2 text-sm">{value.days.slice(offset,offset+25).map(day=><li key={day.date}>{formatDate(day.date)}: размещено {day.planned_person_hours} чел.-ч · зарезервировано в черновике {day.reserved_person_hours} ч присутствия · свободная полезная ёмкость {day.available_person_hours??'неизвестна'}{day.deficit_person_hours!==null&&` · дефицит ${day.deficit_person_hours}`}</li>)}</ul><PlanningPages offset={offset} total={value.days.length} onPage={setOffset}/></>}
  </section>;
}

function PlanVersions({id,onPick}:{id:string;onPick:(r:DraftRecord)=>void}) {
  const [offset,setOffset]=useState(0);
  const query=useApiQuery(()=>api.versions(id,offset),[id,offset],undefined,`draft-versions:${id}:${offset}`);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  return <><ul className="space-y-2">{query.data.items.map(item=><li key={item.revision}><Button variant="secondary" onClick={()=>onPick(item)}>Версия {item.revision} · {item.author_name} · {item.reason}</Button></li>)}</ul><PlanningPages offset={offset} total={query.data.total} onPage={setOffset}/></>;
}

function RootSegments({id,revision,rootId,timezone,mayEdit,onSaved}:{id:string;revision:number;rootId:string;timezone:string;mayEdit:boolean;onSaved:(r:DraftRecord)=>void}) {
  const [offset,setOffset]=useState(0),[selected,setSelected]=useState<WorkSegment|null>(null);
  const query=useApiQuery(()=>api.segments(id,revision,rootId,offset),[id,revision,rootId,offset]);
  return <div className="draft-plan-editor min-w-0 space-y-4">
    {query.status==='loading'&&<LoadingState/>}{query.status==='error'&&<ErrorState description={query.error}/>}
    {query.status==='success'&&<><h3 className="font-semibold">{query.data.occurrence.operation_code} · {query.data.occurrence.title}</h3><p>{query.data.occurrence.total_person_hours} чел.-ч · одновременно {query.data.occurrence.crew_size} чел. · {query.data.occurrence.splittable?'Делимость подтверждена':'Неделимая работа'}</p>
      {query.data.occurrence.import_id?<><a className="text-accent underline" href={catalogImportsApi.source(query.data.occurrence.import_id)}>Скачать исходный Excel</a><p className="break-words text-xs">Лист1: {query.data.occurrence.source_cells.join(', ')} · решение v{query.data.occurrence.decision_revision}</p></>:<div className="space-y-1 break-words text-xs"><p>Действующий регламент · правило {query.data.occurrence.rule_id}</p><p>Редакция {query.data.occurrence.regulation_id} · привязка {query.data.occurrence.binding_id}</p><p>Подтверждённая длительность: {query.data.occurrence.minimum_duration_minutes} мин.</p></div>}
      <p className="text-sm">Основание дат: {query.data.occurrence.date_basis==='accepted_history'?'принятое выполнение':query.data.occurrence.date_basis==='regulation_rule'?'действующий регламент':query.data.occurrence.date_basis==='confirmed_rule'?'подтверждённое календарное правило':'отметки исходного января'}.</p>
      <p className="text-sm">Норма: {query.data.occurrence.norm_ref}</p><p className="text-sm">Ограничения: {query.data.occurrence.policy_note}</p>
      {query.data.occurrence.included_rows.length>0&&<p className="text-sm">В составе работы: строки {query.data.occurrence.included_rows.join(', ')}. Их часы учтены у родителя.</p>}
      <ul className="space-y-3">{query.data.items.map((segment,index)=><li key={segment.segment_id}><Button variant="secondary" onClick={()=>setSelected(segment)}>Сегмент {offset+index+1} · {segment.person_hours} чел.-ч · {segment.locked?'Закреплён':segment.start_at?'Размещён':'Без размещения'}</Button><p className="mt-1 text-sm">{segment.start_at?`${formatDateTime(segment.start_at,timezone)} — ${formatDateTime(segment.end_at,timezone)}`:'Дата и бригада не назначены'}</p>{segment.worker_ids.length>0&&<p className="text-sm">{segment.worker_ids.map(i=>query.data.worker_labels[i]??'Сотрудник недоступен').join(', ')}</p>}</li>)}</ul>
      <PlanningPages offset={offset} total={query.data.total} onPage={setOffset}/>
      {selected&&<SegmentEditor key={selected.segment_id} id={id} revision={revision} root={query.data.occurrence} segment={selected} timezone={timezone} mayEdit={mayEdit} labels={query.data.worker_labels} onSaved={onSaved}/>}
    </>}
  </div>;
}

function localMinute(iso:string,timezone:string) {
  const parts=dateTimeFormatter('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(iso));
  const get=(key:string)=>parts.find(p=>p.type===key)!.value;return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}
function SegmentEditor({id,revision,root,segment,timezone,mayEdit,labels,onSaved}:{id:string;revision:number;root:WorkOccurrence;segment:WorkSegment;timezone:string;mayEdit:boolean;labels:Record<string,string>;onSaved:(r:DraftRecord)=>void}) {
  const [start,setStart]=useState(segment.start_at?localMinute(segment.start_at,timezone):''),[end,setEnd]=useState(segment.end_at?localMinute(segment.end_at,timezone):'');
  const [workers,setWorkers]=useState(segment.worker_ids),[names,setNames]=useState(labels),[locked,setLocked]=useState(segment.locked),[unlock,setUnlock]=useState(false),[reason,setReason]=useState(''),[count,setCount]=useState(2);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const run=async(action:()=>Promise<DraftRecord>)=>{if(busy)return;setBusy(true);setError('');try{onSaved(await action());}catch(e){setError(failure(e));}finally{setBusy(false);}};
  return <section className="space-y-4 border-t border-line pt-4" aria-label="Редактор сегмента"><h4 className="font-semibold">Сегмент · {segment.person_hours} чел.-ч</h4><p className="text-sm">Часы объекта: {timezone}. Для работы одновременно нужны {root.crew_size} сотрудников. Проверка учитывает действующие назначения и отсутствие.</p>
    <fieldset disabled={!mayEdit||busy} className="min-w-0 space-y-4"><legend className="sr-only">Изменение сегмента в новой версии</legend>
      <label className="block"><FieldCaption>Начало сегмента по времени объекта</FieldCaption><Input aria-label="Начало сегмента по времени объекта" type="datetime-local" value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label className="block"><FieldCaption>Конец сегмента по времени объекта</FieldCaption><Input aria-label="Конец сегмента по времени объекта" type="datetime-local" value={end} onChange={e=>setEnd(e.target.value)}/></label>
      <ul className="space-y-2 text-sm">{workers.map(identity=><li key={identity}>{names[identity]??'Выбранный сотрудник'} <Button variant="ghost" onClick={()=>setWorkers(ids=>ids.filter(i=>i!==identity))}>Убрать исполнителя</Button></li>)}</ul>
      {mayEdit&&<PlanningChoices kind="workers" selected={workers} onAdd={item=>{setWorkers(ids=>[...ids,item.id]);setNames(m=>({...m,[item.id]:item.label}));}}/>}
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={locked} onChange={e=>setLocked(e.target.checked)}/><span>Закрепить размещение и состав бригады</span></label>
      {segment.locked&&<label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={unlock} onChange={e=>setUnlock(e.target.checked)}/><span>Явно разрешаю изменить закреплённый сегмент с указанной причиной</span></label>}
      <label className="block"><FieldCaption>Причина изменения плана</FieldCaption><Textarea aria-label="Причина изменения плана" maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)}/></label>
      {mayEdit&&<><Button disabled={!reason.trim()||!start||!end||workers.length!==root.crew_size} onClick={()=>void run(()=>api.place(id,{expected_revision:revision,segment_id:segment.segment_id,start_local:start,end_local:end,worker_ids:workers,locked,unlock,reason}))}>Сохранить размещение в новой версии</Button>
        {segment.start_at&&<Button variant="secondary" disabled={!reason.trim()} onClick={()=>void run(()=>api.place(id,{expected_revision:revision,segment_id:segment.segment_id,start_local:null,end_local:null,worker_ids:[],locked:false,unlock,reason}))}>Снять размещение в новой версии</Button>}
        <div className="space-y-3"><label className="block"><FieldCaption>Число частей сегмента</FieldCaption><Input aria-label="Число частей сегмента" type="number" min={2} max={25} value={count} onChange={e=>setCount(Number(e.target.value))}/></label><Button variant="secondary" disabled={!root.splittable||!reason.trim()} onClick={()=>void run(async()=>{
          const hours=splitPersonHours(segment.person_hours,count),ids=hours.map((_,i)=>i===hours.length-1?segment.segment_id:crypto.randomUUID());
          const pieces=hours.map((person_hours,i):WorkSegment=>({...segment,segment_id:ids[i],person_hours,start_at:null,end_at:null,worker_ids:[],locked:false,depends_on_segment_ids:i?[ids[i-1]]:segment.depends_on_segment_ids}));
          return api.edit(id,{expected_revision:revision,occurrence_id:root.occurrence_id,replace_segment_ids:[segment.segment_id],segments:pieces,unlock,reason});
        })}>Разделить с сохранением общего объёма</Button><p className="text-sm text-muted">Часы сохраняются точно; остаток входит в последнюю часть. Сегменты размещаются отдельно в порядке зависимостей. Неделимая работа не разделяется.</p></div>
      </>}
    </fieldset>{error&&<p role="alert"><Callout tone="danger">{error}</Callout><span className="text-sm">Введённые значения сохранены в форме.</span></p>}
  </section>;
}
