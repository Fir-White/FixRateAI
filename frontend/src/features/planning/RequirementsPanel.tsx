import { useDeferredValue,useEffect,useState } from 'react';
import { Link } from 'react-router-dom';
import { requirementsApi,type RequirementsRequest,type Requirement,type RequirementState } from '@/shared/api/requirements';
import { catalogImportsApi } from '@/shared/api/catalogImports';
import { draftPlansApi,type DraftPolicy } from '@/shared/api/draftPlans';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { todayAt,formatDate,formatDateTime } from '@/shared/lib/format';
import { Button,buttonClassName } from '@/shared/ui/Button';
import { FieldCaption,Input,Select } from '@/shared/ui/Form';
import { Callout } from '@/shared/ui/Callout';
import { LoadingState,ErrorState } from '@/shared/ui/States';
import { PlanningPages } from './PlanningChoices';
import { newPolicy,clock } from './PolicyFields';

const states:Record<RequirementState,string>={new:'Нужно запланировать',existing:'Задание уже создано',fulfilled:'Выполнено и принято',review:'Нужна проверка'};
const flags:Record<string,string>={ROLLING_NEXT_OCCURRENCE_ONLY:'Только следующее ТО от принятого выполнения',SYNTHETIC_DATA:'Тестовые данные',OVERDUE_REQUIRES_REVIEW:'Срок уже прошёл: требуется решение инженера',EXISTING_OCCURRENCE_REVIEW:'Существующее вхождение требует сверки',COMPLETION_NOT_ACCEPTED:'Выполнение ещё не принято',PARTIAL_ALREADY_PUBLISHED:'Часть этого объёма уже выдана',SOURCE_EQUIVALENCE_REQUIRED:'Нужно сопоставить одинаковые работы из разных источников',NORM_UNIT_UNCONFIRMED:'Не подтверждена единица нормы',NORM_VALUE_MISSING:'Не указана трудоёмкость',DURATION_UNCONFIRMED:'Не подтверждена длительность',EQUIPMENT_OUT_OF_SERVICE:'Оборудование в ремонте',HISTORY_AFTER_CUTOFF_IGNORED:'Будущие факты не учтены'};

export default function RequirementsPanel({timezone,catalogId,initialStart,initialEnd,mayConfigure,mayViewTasks=false,onCatalog,onCalculate,onPrepare}:{timezone:string;catalogId:string;initialStart?:string;initialEnd?:string;mayConfigure:boolean;mayViewTasks?:boolean;onCatalog:(id:string)=>void;onCalculate:(start:string,end:string)=>void;onPrepare:()=>void}) {
  const year=todayAt(timezone).slice(0,4);
  const [start,setStart]=useState(initialStart||`${year}-01-01`),[end,setEnd]=useState(initialEnd||`${year}-12-31`),[regulations,setRegulations]=useState(true),[withCatalog,setWithCatalog]=useState(!!catalogId);
  const [rows,setRows]=useState<number[]>([]),[expansion,setExpansion]=useState<'source_january'|'confirmed_rule'>('confirmed_rule'),[policy,setPolicy]=useState<DraftPolicy>(newPolicy);
  const [submitted,setSubmitted]=useState<{body:RequirementsRequest;generation:number}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const body:RequirementsRequest={starts_on:start,ends_on:end,include_regulations:regulations,catalog:withCatalog&&catalogId?{import_id:catalogId,starts_on:start,ends_on:end,row_numbers:rows,expansion,policy}:null};
  const stale=submitted&&JSON.stringify(body)!==JSON.stringify(submitted.body);
  return <section className="space-y-5" aria-label="Обязательные работы из регламентов и Excel">
    <div><h2 className="text-xl font-semibold">Что нужно обслужить в выбранном периоде</h2><p className="mt-2 text-sm text-muted">Общий состав по действующим регламентам и выбранным строкам Excel. Существующие задания учитываются отдельно.</p></div>
    <fieldset disabled={busy} className="min-w-0 space-y-4 rounded-xl border border-line p-4"><legend className="px-2 font-semibold">Период и источники</legend>
      <div className="grid gap-3 sm:grid-cols-2"><label><FieldCaption>Начало периода обязательств</FieldCaption><Input type="date" aria-label="Начало периода обязательств" value={start} onChange={e=>setStart(e.target.value)}/></label><label><FieldCaption>Конец периода обязательств</FieldCaption><Input type="date" aria-label="Конец периода обязательств" value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={regulations} onChange={e=>setRegulations(e.target.checked)}/>Действующие регламенты объекта</label>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={withCatalog} onChange={e=>setWithCatalog(e.target.checked)}/>Добавить подготовленные строки Excel</label>
      {withCatalog&&<div className="space-y-3 border-t border-line pt-4"><CatalogPicker selected={catalogId} onSelect={id=>{setRows([]);onCatalog(id);}}/>
        {catalogId&&<><label className="block"><FieldCaption>Даты из Excel</FieldCaption><Select aria-label="Даты из Excel" value={expansion} onChange={e=>setExpansion(e.target.value as typeof expansion)}><option value="confirmed_rule">Подтверждённое правило на выбранный период</option><option value="source_january">Только подтверждённые отметки исходного января</option></Select></label>
          <SourceRows id={catalogId} selected={rows} onChange={setRows}/>
          <Button variant="secondary" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const data=await catalogImportsApi.preparation(catalogId);setRows(data.items.filter(x=>x.prepared).map(x=>x.row_number));}catch(e){setError(e instanceof Error?e.message:'Не удалось получить подготовленные строки');}finally{setBusy(false);}}}>Выбрать все подготовленные строки Excel</Button>
          <p className="text-sm">Выбрано строк: {rows.length}. <Button variant="ghost" onClick={onPrepare}>Подготовить или проверить строки →</Button></p>
          <details><summary>Для двух событий в сутки: границы день / ночь</summary><div className="mt-3 grid gap-3 sm:grid-cols-2">{(['day_start_minute','night_start_minute'] as const).map((key,i)=><label key={key}><FieldCaption>{i?'Начало ночного события':'Начало дневного события'}</FieldCaption><Input type="time" aria-label={i?'Начало ночного события':'Начало дневного события'} value={policy[key]===null?'':clock(policy[key]!)} onChange={e=>{const [h,m]=e.target.value.split(':').map(Number);setPolicy(p=>({...p,[key]:e.target.value?h*60+m:null}));}}/></label>)}</div></details>
        </>}
      </div>}
      <Button disabled={!start||!end||(!regulations&&!withCatalog)||(withCatalog&&(!catalogId||!rows.length))} onClick={()=>{setError('');setSubmitted(previous=>({body,generation:(previous?.generation??0)+1}));onCalculate(start,end);}}>Рассчитать состав обязательств</Button>
      {error&&<p role="alert">{error}</p>}
    </fieldset>
    {stale&&<Callout>Параметры изменены. Ниже показан предыдущий расчёт; нажмите «Рассчитать состав обязательств», чтобы обновить его.</Callout>}
    {submitted?<Results key={submitted.generation} input={submitted.body} timezone={timezone} mayConfigure={mayConfigure} mayViewTasks={mayViewTasks} onPrepare={onPrepare}/>:<Callout>Выберите период и источники, затем запустите расчёт. Неизвестные нормы и неподтверждённые правила будут показаны явно.</Callout>}
  </section>;
}

function CatalogPicker({selected,onSelect}:{selected:string;onSelect:(id:string)=>void}) {
  const [offset,setOffset]=useState(0);const query=useApiQuery(()=>catalogImportsApi.list(offset),[offset],undefined,`catalog-list:${offset}`);
  return <div className="space-y-2" aria-label="Выбор Excel для общего состава"><p className="font-semibold text-sm">Сохранённый Excel</p>{query.status==='loading'&&<LoadingState/>}{query.status==='error'&&<ErrorState description={query.error}/>}{query.status==='success'&&<><ul className="space-y-2">{query.data.items.map(x=><li key={x.import_id}><Button variant={x.import_id===selected?'primary':'secondary'} aria-pressed={x.import_id===selected} className="max-w-full whitespace-normal break-words text-left" onClick={()=>onSelect(x.import_id)}>{x.filename}</Button></li>)}</ul>{!query.data.total&&<p className="text-sm">Сохранённых файлов нет. Загрузите файл во вкладке «Планы из Excel».</p>}<PlanningPages offset={offset} total={query.data.total} onPage={setOffset}/></>}</div>;
}

function SourceRows({id,selected,onChange}:{id:string;selected:number[];onChange:(rows:number[])=>void}) {
  const [q,setQ]=useState(''),[offset,setOffset]=useState(0),needle=useDeferredValue(q);
  const query=useApiQuery(()=>draftPlansApi.sources(id,needle,offset),[id,needle,offset],undefined,`requirements-rows:${JSON.stringify([id,needle,offset])}`);
  return <div className="space-y-2"><label className="block"><FieldCaption>Поиск подготовленных строк для состава</FieldCaption><Input aria-label="Поиск подготовленных строк для состава" value={q} onChange={e=>{setQ(e.target.value);setOffset(0);}}/></label>{query.status==='loading'&&<LoadingState/>}{query.status==='error'&&<ErrorState description={query.error}/>}{query.status==='success'&&<><ul className="space-y-2">{query.data.items.map(x=><li key={x.row_number}><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={selected.includes(x.row_number)} onChange={e=>onChange(e.target.checked?[...selected,x.row_number]:selected.filter(n=>n!==x.row_number))}/>{x.code} · {x.title} · строка {x.row_number}</label></li>)}</ul>{!query.data.total&&<p className="text-sm text-muted">Подготовленных строк не найдено. Уточните оборудование, смысл отметок и норму в файле.</p>}<PlanningPages offset={offset} total={query.data.total} onPage={setOffset}/></>}</div>;
}

function Results({input,timezone,mayConfigure,mayViewTasks,onPrepare}:{input:RequirementsRequest;timezone:string;mayConfigure:boolean;mayViewTasks:boolean;onPrepare:()=>void}) {
  const [offset,setOffset]=useState(0),[issueOffset,setIssueOffset]=useState(0),[q,setQ]=useState(''),[state,setState]=useState<RequirementsRequest['state']>('all'),[retry,setRetry]=useState(0),[needle,setNeedle]=useState('');
  useEffect(()=>{const timer=setTimeout(()=>setNeedle(q),250);return()=>clearTimeout(timer);},[q]);
  const query=useApiQuery(()=>requirementsApi.preview({...input,q:needle,state,offset,issue_offset:issueOffset}),[input,needle,state,offset,issueOffset,retry]);
  const searchField=<label key="search" className="block"><FieldCaption>Поиск обязательных работ</FieldCaption><Input aria-label="Поиск обязательных работ" value={q} onChange={e=>{setQ(e.target.value);setOffset(0);}}/></label>;
  if(query.status==='loading')return <section aria-label="Состав обязательств" className="space-y-4">{searchField}<LoadingState label="Расчёт обязательных работ"/></section>;
  if(query.status==='error')return <section aria-label="Состав обязательств" className="space-y-3">{searchField}<ErrorState description={query.error}/><Button variant="secondary" onClick={()=>setRetry(n=>n+1)}>Повторить расчёт обязательств</Button><p className="text-sm">Исходные параметры сохранены в форме.</p></section>;
  const data=query.data,s=data.summary;
  return <section className="space-y-4" aria-label="Состав обязательств">{searchField}<div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-line p-4"><p className="text-sm text-muted">Обязательных работ</p><strong className="text-2xl">{s.total}</strong></div><div className="rounded-xl border border-line p-4"><p className="text-sm text-muted">Известная трудоёмкость</p><strong className="text-2xl">{s.known_person_hours} чел.-ч</strong>{s.total_person_hours===null&&<p className="text-sm text-muted">Сумма неполная — проверьте замечания</p>}</div><div className="rounded-xl border border-line p-4"><p className="text-sm text-muted">Новый объём для планирования</p><strong className="text-2xl">{s.new_person_hours===null?'Требует уточнения':`${s.new_person_hours} чел.-ч`}</strong></div></div>
    <p className="text-sm text-muted">{formatDate(data.starts_on)} — {formatDate(data.ends_on)} · {formatDateTime(data.calculated_at,timezone)} · {data.timezone}</p>
    <p className="text-sm text-muted">Привязок регламентов: {s.binding_count}. Строк Excel выбрано: {s.selected_catalog_rows}; вне выбранного состава: {s.unselected_catalog_rows}. Полнота расчёта относится только к этому составу.</p>
    <div className="flex flex-wrap gap-2">{Object.entries(states).map(([key,label])=><Button key={key} variant={state===key?'primary':'secondary'} onClick={()=>{setState(key as RequirementState);setOffset(0);}}>{label}: {s.state_counts[key as RequirementState]??0}</Button>)}<Button variant={state==='all'?'primary':'secondary'} onClick={()=>{setState('all');setOffset(0);}}>Все работы</Button></div>
    {data.total_issues>0&&<section className="space-y-3 rounded-xl border border-line p-4" aria-label="Что нужно уточнить для расчёта"><h3 className="font-semibold">Что нужно уточнить: {data.total_issues}</h3><ul className="space-y-2 text-sm">{data.issues.map((x,i)=><li key={i}>{x.source_kind==='catalog'?`Excel${x.source_row?` · строка ${x.source_row}`:''}`:'Регламент'}: {x.source_label&&<strong>{x.source_label}: </strong>}{x.message}</li>)}</ul><PlanningPages offset={issueOffset} total={data.total_issues} onPage={setIssueOffset}/>{mayConfigure&&<Link className={buttonClassName('secondary')} to="/settings/equipment">Проверить регламенты оборудования</Link>}{input.catalog&&<Button variant="secondary" onClick={onPrepare}>Проверить строки Excel</Button>}</section>}
    <details><summary>Часы по месяцам срока</summary><ul className="mt-3 grid gap-2 sm:grid-cols-3">{data.months.map(x=><li key={x.month} className="rounded-lg border border-line p-3 text-sm">{x.month} · {x.requirements} работ · известно {x.known_person_hours} чел.-ч{x.unknown_hours_count>0&&` · без нормы: ${x.unknown_hours_count}`}</li>)}</ul></details>
    <ul className="space-y-3" aria-label="Работы общего состава">{data.items.map(item=><li key={item.requirement_id}><RequirementCard value={item} mayViewTasks={mayViewTasks}/></li>)}</ul>{!data.total&&<p>Работы в этом представлении не найдены. Проверьте источники, период и фильтр.</p>}<PlanningPages offset={offset} total={data.total} onPage={setOffset}/>
    <Callout>Это проверка состава и исходной трудоёмкости. Назначения и действующий график не изменяются. Расчёт и выпуск плана по подготовленным строкам доступны во вкладке «Планы из Excel»; перенос общего состава в единый редактор — следующий этап.</Callout>
  </section>;
}
function RequirementCard({value:x,mayViewTasks}:{value:Requirement;mayViewTasks:boolean}) {
  return <article className="space-y-2 rounded-xl border border-line p-4">{x.source_slot!=='whole_day'&&<p className="text-sm text-muted">{x.source_slot==='day'?'Дневное событие':'Ночное событие'}</p>}<div className="flex flex-wrap items-start justify-between gap-2"><h3 className="font-semibold">{x.operation_code} · {x.title}</h3><span className="text-sm text-accent">{states[x.state]}</span></div><p className="text-sm">{x.equipment_labels.join(', ')} · {x.maintenance_type}</p><p className="text-sm">{x.person_hours===null?'Трудоёмкость не подтверждена':`${x.person_hours} чел.-ч`} · бригада {x.crew_size}</p><p className="text-sm">Допустимые даты: {formatDate(x.earliest_date)} — {formatDate(x.due_date)}</p>{x.synthetic&&<p className="text-xs text-muted">Тестовые данные</p>}
    <details><summary className="text-sm">Источник, сроки и объяснение</summary><div className="mt-3 space-y-2 text-sm"><p>{x.source_kind==='catalog'?`Excel · строка ${x.source_row}`:'Действующий регламент'} · версия {x.source_revision}</p><p>Исходная дата обязательства: {formatDate(x.source_date)}</p><p className="whitespace-pre-wrap break-words">{x.explanation}</p><p className="break-words text-muted">{x.source_ref}</p>{x.qualification_ids.length>0&&<p>Специальных допусков: {x.qualification_ids.length}</p>}<ul>{x.issues.map(flag=><li key={flag}>{flags[flag]??flag}</li>)}</ul>{mayViewTasks&&<div className="flex flex-wrap gap-2">{x.task_ids.slice(0,5).map((id,index)=><Link key={id} className="text-accent underline" to={`/tasks/${id}`}>Открыть задание {index+1}</Link>)}</div>}{x.task_ids.length>0&&<p>Связанных заданий: {x.task_ids.length}. Они учитываются отдельно от нового объёма.</p>}</div></details>
  </article>;
}
