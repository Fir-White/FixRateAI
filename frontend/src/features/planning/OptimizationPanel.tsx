import { useEffect,useRef,useState } from 'react';
import { optimizationApi as api,type OptimizationOptions,type OptimizationRun,type OptimizationVariant } from '@/shared/api/optimization';
import type { DraftRecord } from '@/shared/api/draftPlans';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { formatDateTime } from '@/shared/lib/format';
import { Button } from '@/shared/ui/Button';
import { FieldCaption,Input,Select,Textarea } from '@/shared/ui/Form';
import { LoadingState,ErrorState } from '@/shared/ui/States';
import { Callout } from '@/shared/ui/Callout';
import { PlanningPages } from './PlanningChoices';

const active=(run:OptimizationRun)=>['queued','running','cancel_requested'].includes(run.state);
const failure=(e:unknown)=>e instanceof Error?e.message:'Не удалось выполнить действие';
const states={queued:'В очереди',running:'Выполняется',cancel_requested:'Отмена запрошена',cancelled:'Отменён',succeeded:'Завершён',failed:'Ошибка расчёта'};
const solverStates:Record<string,string>={HEURISTIC:'Базовое размещение',OPTIMAL:'Найден лучший вариант модели',FEASIBLE:'Найден допустимый вариант',INFEASIBLE:'Ограничения несовместимы',UNKNOWN:'Результат пока неизвестен',MODEL_INVALID:'Ошибка модели',UNAVAILABLE:'Решатель недоступен'};
const reasons:Record<string,string>={finished:'Расчёт завершён',time_limit:'Достигнут лимит времени',model_limit:'Рассмотрена часть вариантов: достигнут лимит модели',needs_input:'Нужно уточнить исходные данные',solver_unavailable:'Решатель недоступен; доступен базовый режим'};
const defaults:OptimizationOptions={grid_minutes:60,time_limit_seconds:10,replan_existing:false,start_buffer_minutes:5,random_seed:1,weights:{daily_peak:10,worker_spread:3,changes:10,earliness:0}};

export default function OptimizationPanel({record,mayEdit,timezone,onSaved}:{record:DraftRecord;mayEdit:boolean;timezone:string;onSaved:(record:DraftRecord)=>void}) {
  const [options,setOptions]=useState(defaults),[run,setRun]=useState<OptimizationRun|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[offset,setOffset]=useState(0);
  const attempt=useRef<{signature:string;key:string}|null>(null),mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const history=useApiQuery(()=>api.list(record.draft_id,offset),[record.draft_id,offset,refresh]);
  // Poll only the chosen run, with one request in flight and no polling in a hidden tab.
  useEffect(()=>{
    if(!run||!active(run))return;
    let disposed=false,inFlight=false,timer:ReturnType<typeof setTimeout>|undefined;
    const poll=async()=>{
      if(disposed||document.hidden||inFlight)return;
      inFlight=true;
      try{const next=await api.get(run.run_id);if(!disposed){setRun(next);setError('');if(!active(next))setRefresh(n=>n+1);}}
      catch(e){if(!disposed)setError(failure(e));}
      finally{inFlight=false;if(!disposed&&!document.hidden)timer=setTimeout(()=>void poll(),1500);}
    };
    const visibility=()=>{if(timer)clearTimeout(timer);if(!document.hidden)void poll();};
    timer=setTimeout(()=>void poll(),750);document.addEventListener('visibilitychange',visibility);
    return()=>{disposed=true;if(timer)clearTimeout(timer);document.removeEventListener('visibilitychange',visibility);};
  },[run?.run_id,run?.state]);
  const action=async(fn:()=>Promise<OptimizationRun>)=>{
    if(busy)return;setBusy(true);setError('');
    try{const next=await fn();if(mounted.current){setRun(next);setRefresh(n=>n+1);}}
    catch(e){if(mounted.current)setError(failure(e));}finally{if(mounted.current)setBusy(false);}
  };
  return <section className="space-y-4 rounded-xl border border-line p-4" aria-label="Автоматическое размещение работ">
    <h4 className="font-semibold">Автоматическое размещение и сравнение</h4>
    <p className="text-sm">Сравните размещение по ближайшему сроку и вариант с балансировкой нагрузки. Расчёт использует сохранённые сегменты, подтверждённые нормы, доступность и допуски сотрудников. Для делимой работы сначала задайте нужные части в редакторе.</p>
    {mayEdit&&<fieldset disabled={busy||Boolean(run&&active(run))} className="grid min-w-0 gap-3 sm:grid-cols-2">
      <legend className="sr-only">Параметры расчёта</legend>
      <label><FieldCaption>Шаг начала работ</FieldCaption><Select aria-label="Шаг начала работ" value={options.grid_minutes} onChange={e=>{const grid_minutes=Number(e.target.value) as 15|30|60;setOptions(o=>({...o,grid_minutes}));}}><option value={60}>60 минут</option><option value={30}>30 минут</option><option value={15}>15 минут</option></Select></label>
      <label><FieldCaption>Лимит расчёта, секунд</FieldCaption><Input aria-label="Лимит расчёта, секунд" type="number" min={1} max={30} value={options.time_limit_seconds} onChange={e=>setOptions(o=>({...o,time_limit_seconds:Number(e.target.value)}))}/></label>
      <label className="flex items-start gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={options.replan_existing} onChange={e=>setOptions(o=>({...o,replan_existing:e.target.checked}))}/><span>Разрешить перенос незакреплённых размещений. Закреплённые дата и бригада сохраняются.</span></label>
      <details className="sm:col-span-2"><summary className="cursor-pointer text-sm">Приоритеты балансировки</summary><div className="mt-3 grid gap-3 sm:grid-cols-2">{([['daily_peak','Снижение пиков по дням'],['worker_spread','Равномерность загрузки людей'],['changes','Сохранение прежних назначений'],['earliness','Более раннее выполнение']] as const).map(([key,label])=><label key={key}><FieldCaption>{label}</FieldCaption><Input aria-label={label} type="number" min={0} max={100} value={options.weights[key]} onChange={e=>setOptions(o=>({...o,weights:{...o.weights,[key]:Number(e.target.value)}}))}/></label>)}</div><p className="mt-2 text-xs text-muted">Сначала обеспечивается покрытие работ, затем число размещённых сегментов; веса применяются после этих приоритетов.</p></details>
      <Button onClick={()=>void action(()=>{
        const signature=JSON.stringify(options);if(attempt.current?.signature!==signature)attempt.current={signature,key:crypto.randomUUID()};
        return api.start(record.draft_id,record.revision,attempt.current!.key,options).then(next=>{attempt.current=null;return next;});
      })}>Рассчитать два варианта</Button>
    </fieldset>}
    {error&&<p role="alert">{error}</p>}
    {history.status==='loading'&&<LoadingState/>}{history.status==='error'&&<ErrorState description={history.error}/>}
    {history.status==='success'&&<><ul className="space-y-2" aria-label="История расчётов">{history.data.items.map(item=><li key={item.run_id}><Button variant="ghost" disabled={busy} onClick={()=>void action(()=>api.get(item.run_id))}>{formatDateTime(item.created_at,timezone)} · версия {item.base_revision} · {states[item.state]}</Button></li>)}</ul><PlanningPages offset={offset} total={history.data.total} onPage={setOffset}/></>}
    {run&&<section className="space-y-4" aria-label="Результат автоматического расчёта"><p role="status">{states[run.state]} · исходная версия {run.base_revision}</p>
      {mayEdit&&active(run)&&<Button variant="secondary" disabled={busy||run.state==='cancel_requested'} onClick={()=>void action(()=>api.cancel(run.run_id))}>Отменить расчёт</Button>}
      {run.error_code&&<Callout tone="danger">Расчёт не завершился: {run.error_code}. Можно повторить его; черновик сохранён.</Callout>}
      {run.result&&<><p>{reasons[run.result.completion_reason]??run.result.completion_reason}. Кандидатов: {run.result.candidate_count}.</p><Callout>Доказательство оптимальности относится только к выбранной сетке и рассмотренным кандидатам. Неполный поиск и истечение времени не доказывают невозможность составить график. Применение создаёт новую версию черновика.</Callout>
        <ul className="space-y-2 text-sm">{run.result.diagnostics.map((item,index)=><li key={index}>{item.row_number&&`Строка ${item.row_number}: `}{item.message}</li>)}</ul>
        {Object.values(run.result.diagnostic_counts).reduce((a,b)=>a+b,0)>run.result.diagnostics.length&&<p className="text-xs text-muted">Показаны первые {run.result.diagnostics.length} замечаний.</p>}
        <div className="grid min-w-0 gap-4 lg:grid-cols-2">{([run.result.baseline,run.result.optimized]).filter((v):v is OptimizationVariant=>v!==null).map(variant=><Variant key={run.run_id+variant.kind} variant={variant} run={run} record={record} timezone={timezone} mayEdit={mayEdit&&!run.applied_revision&&record.revision===run.base_revision} onSaved={onSaved}/>)}</div>
      </>}{run.applied_revision&&<p>Применён вариант «{run.applied_kind==='optimized'?'С балансировкой':'Базовый'}» в версии {run.applied_revision}.</p>}
    </section>}
  </section>;
}

function Variant({variant:v,run,record,timezone,mayEdit,onSaved}:{variant:OptimizationVariant;run:OptimizationRun;record:DraftRecord;timezone:string;mayEdit:boolean;onSaved:(record:DraftRecord)=>void}) {
  const [show,setShow]=useState(false),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const m=v.metrics,percent=(value:string|null)=>value===null?'неизвестно':`${(Number(value)*100).toFixed(1)}%`;
  return <section className="min-w-0 space-y-3 rounded-xl border border-line p-3" aria-label={v.kind==='baseline'?'Базовый вариант':'Вариант с балансировкой'}>
    <h5 className="font-semibold">{v.kind==='baseline'?'Базовый вариант':'С балансировкой · CP-SAT'}</h5>
    <p className="text-sm">{solverStates[v.solver_status]??v.solver_status} · покрытие {m.covered_occurrences}/{m.total_occurrences} · {v.optimality_proven?'Оптимум в рассмотренной модели доказан':'Оптимальность не доказана'}</p>
    <dl className="space-y-1 text-sm"><div><dt className="inline">Размещено: </dt><dd className="inline">{m.placed_person_hours} из {m.total_person_hours} чел.-ч</dd></div><div><dt className="inline">Пиковая нагрузка дня: </dt><dd className="inline">{m.peak_daily_person_hours} чел.-ч · {percent(m.peak_daily_utilization)} ёмкости</dd></div><div><dt className="inline">Использование людей: </dt><dd className="inline">{percent(m.staff_utilization)}</dd></div><div><dt className="inline">Разброс загрузки людей: </dt><dd className="inline">{percent(m.fairness_spread)}</dd></div><div><dt className="inline">Переназначений: </dt><dd className="inline">{m.changed_assignments} · неразмещённых сегментов {m.unplaced_segments}</dd></div></dl>
    <p className="text-sm">{v.validation.status==='valid'?'Проверенные ограничения соблюдены':v.validation.status==='incomplete'?'Требуются данные или размещение':'Есть нарушения'}</p>
    <ul className="space-y-1 text-xs">{v.validation.issues.map((issue,i)=><li key={i}>{issue.message}</li>)}</ul>
    <Button variant="ghost" aria-expanded={show} onClick={()=>setShow(a=>!a)}>Посмотреть размещения</Button>{show&&<Placements run={run.run_id} kind={v.kind} timezone={timezone}/>}
    {mayEdit&&v.applicable&&<><label className="block"><FieldCaption>Причина применения варианта</FieldCaption><Textarea aria-label="Причина применения варианта" value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label><Button disabled={busy||!reason.trim()} onClick={async()=>{setBusy(true);setError('');try{onSaved(await api.apply(run.run_id,record.revision,v.kind,reason));}catch(e){setError(failure(e));}finally{setBusy(false);}}}>Применить в новую версию</Button></>}
    {error&&<p role="alert">{error} Введённая причина сохранена.</p>}
  </section>;
}

function Placements({run,kind,timezone}:{run:string;kind:'baseline'|'optimized';timezone:string}) {
  const [offset,setOffset]=useState(0);const query=useApiQuery(()=>api.placements(run,kind,offset),[run,kind,offset]);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  return <><ul className="space-y-2 text-sm" aria-label="Размещения варианта">{query.data.items.map((item,index)=><li className="break-words" key={item.segment_id}><p className="font-semibold">{query.data.occurrence_labels[item.occurrence_id]??'Работа черновика'}</p>Сегмент {offset+index+1} · {item.person_hours} чел.-ч · {item.start_at?`${formatDateTime(item.start_at,timezone)} — ${formatDateTime(item.end_at,timezone)}`:'Не размещён'}<p>{item.worker_ids.map(id=>query.data.worker_labels[id]??'Сотрудник недоступен').join(', ')}{item.locked?' · Закреплён':''}</p></li>)}</ul><PlanningPages offset={offset} total={query.data.total} onPage={setOffset}/></>;
}
