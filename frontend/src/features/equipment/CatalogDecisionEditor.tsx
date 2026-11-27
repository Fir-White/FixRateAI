import { lazy,Suspense,useDeferredValue, useState, type ReactNode } from 'react';
import { catalogImportsApi as api, type CatalogDecision, type CatalogDecisionRecord, type CatalogBinding } from '@/shared/api/catalogImports';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { FieldCaption, Input, Select, Textarea } from '@/shared/ui/Form';
import { Callout } from '@/shared/ui/Callout';
import { LoadingState, ErrorState } from '@/shared/ui/States';
import { patternDefaults,type CalendarPattern } from '@/shared/types/management';
import { PlanningChoices,PlanningPages } from '@/features/planning/PlanningChoices';

import { JourneySteps } from '@/shared/ui/JourneySteps';

const PatternEditor=lazy(()=>import('@/features/settings/CalendarPatternEditor').then(m=>({default:m.CalendarPatternEditor})));

export const decisionBlockers:Record<string,string>={NEEDS_SEMANTICS:'Подтвердите смысл отметок, год января и пояснение',NEEDS_FREQUENCY:'Уточните периодичность',NEEDS_ASSET_BINDING:'Выберите действующее оборудование',NEEDS_DURATION:'Укажите норму, единицу, базу расчёта, состав бригады и источник',NEEDS_POLICY:'Уточните разделение работы и правила планирования',NEEDS_PARENT:'Выберите подтверждённую самостоятельную родительскую работу',PARENT_BINDING_MISMATCH:'Оборудование должно совпадать с родительской работой',STALE_PARENT:'Родительская работа изменена — требуется повторное подтверждение',STALE_ASSET_BINDING:'Оборудование изменено — проверьте привязку повторно',SEGMENT_EXCEEDS_DURATION:'Минимальный сегмент превышает длительность работы'};
const modes:Record<CatalogDecision['interpretation'],string>={UNKNOWN:'Не определено',FIXED_EXECUTION:'Отметки — отдельные выполнения',ALLOWED_WINDOW:'Отметки — допустимое окно одной работы',CONTINUOUS_WORK:'Отметки — продолжение одной работы',EQUIPMENT_BATCH:'Отметки — обслуживание группы оборудования'};
decisionBlockers.PARENT_CALENDAR_MISMATCH='Год и события должны совпадать с родительской работой';
decisionBlockers.PARENT_POLICY_MISMATCH='Правила разделения должны совпадать с родительской работой';
const frequencies:Record<CatalogDecision['frequency_kind'],string>={unconfirmed:'Не подтверждена',day:'Раз в N дней',week:'Раз в N недель',month:'Раз в N месяцев',quarter:'Раз в N кварталов',year:'Раз в N лет',yearly_count:'N раз в год',dates:'Подтверждённые даты',daily_events:'N событий в сутки',event:'По необходимости',included_in:'В составе другой работы'};
const errorText=(error:unknown)=>Object.entries(decisionBlockers).reduce((text,[code,label])=>text.replaceAll(code,label),error instanceof Error?error.message:'Не удалось сохранить решение');

export function CatalogDecisionEditor({id,row,mayEdit,mayConfirm,onSaved,guided=false}:{id:string;row:number;mayEdit:boolean;mayConfirm:boolean;onSaved:()=>void;guided?:boolean}) {
  const [refresh,setRefresh]=useState(0);
  // The editing base is read fresh on open/reload. Background focus refetches
  // must not unmount a form with unsaved input on a temporary network error.
  const query=useApiQuery(()=>api.decision(id,row),[id,row,refresh]);
  if(query.status==='loading')return <LoadingState/>;
  if(query.status==='error')return <ErrorState description={query.error}/>;
  return <DecisionForm guided={guided} key={refresh} id={id} row={row} record={query.data} mayEdit={mayEdit} mayConfirm={mayConfirm} onSaved={onSaved} reload={()=>setRefresh(n=>n+1)}/>;
}

function DecisionForm({id,row,record,mayEdit,mayConfirm,onSaved,reload,guided}:{id:string;row:number;record:CatalogDecisionRecord;mayEdit:boolean;mayConfirm:boolean;onSaved:()=>void;reload:()=>void;guided:boolean}) {
  const [saved,setSaved]=useState(record),[draft,setDraft]=useState(record.decision),[reason,setReason]=useState('');
  const [equipment,setEquipment]=useState(record.equipment),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[dirty,setDirty]=useState(false),[history,setHistory]=useState(false);
  const [qualificationLabels,setQualificationLabels]=useState<Record<string,string>>(record.qualification_labels??{}),[qualificationOffset,setQualificationOffset]=useState(0);
  const field=<K extends keyof CatalogDecision>(name:K,value:CatalogDecision[K])=>{setDraft(d=>({...d,[name]:value}));setDirty(true);setNotice('');};
  const save=async(confirm:boolean)=>{
    if(busy)return;setBusy(true);setError('');setNotice('');
    try{const result=await api.saveDecision(id,row,{expected_revision:saved.revision,confirm,reason,decision:draft});setSaved(result);setDraft(result.decision);setEquipment(result.equipment);setReason('');setDirty(false);setNotice(confirm?'Решение подтверждено для подготовки планирования.':'Новая версия черновика сохранена.');onSaved();}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  };
  const included=draft.frequency_kind==='included_in';
  const [step,setStep]=useState('dates');

  const datesFields=<>
      <h4 className="mb-3 font-semibold">Календарные отметки и частота</h4>
      <label className="block"><FieldCaption>Смысл отметок</FieldCaption><Select aria-label="Смысл отметок" value={draft.interpretation} onChange={e=>field('interpretation',e.target.value as CatalogDecision['interpretation'])}>{Object.entries(modes).map(([value,label])=><option key={value} value={value}>{label}</option>)}</Select></label>
      <label className="block"><FieldCaption>Год исходного января</FieldCaption><Input aria-label="Год исходного января" type="number" min={2000} max={2200} value={draft.calendar_year??''} onChange={e=>field('calendar_year',e.target.value===''?null:Number(e.target.value))}/></label>
      <label className="block"><FieldCaption>События внутри отметки</FieldCaption><Select aria-label="События внутри отметки" value={draft.mark_slots} onChange={e=>field('mark_slots',e.target.value as CatalogDecision['mark_slots'])}><option value="unconfirmed">Не подтверждены</option><option value="one_per_mark">Одна отметка — одно событие</option><option value="day_night">День и ночь — отдельные события</option></Select></label>
      <label className="block"><FieldCaption>Пояснение смысла отметок</FieldCaption><Textarea aria-label="Пояснение смысла отметок" maxLength={2000} value={draft.semantics_note} onChange={e=>field('semantics_note',e.target.value)}/></label>
      <label className="block"><FieldCaption>Подтверждённая периодичность</FieldCaption><Select aria-label="Подтверждённая периодичность" value={draft.frequency_kind} onChange={e=>{const kind=e.target.value as CatalogDecision['frequency_kind'];setDraft(d=>({...d,frequency_kind:kind,frequency_interval:null,included_in_row:null,calendar_pattern:null,allowed_lead_days:0,...(kind==='included_in'?{norm_value:null,norm_unit:'unconfirmed' as const,norm_scope:'unconfirmed' as const}: {})}));setDirty(true);}}>{Object.entries(frequencies).map(([value,label])=><option key={value} value={value}>{label}</option>)}</Select></label>
      {!['unconfirmed','event','included_in','dates'].includes(draft.frequency_kind)&&<label className="block"><FieldCaption>Значение N</FieldCaption><Input aria-label="Значение N" type="number" min={1} max={100} value={draft.frequency_interval??''} onChange={e=>field('frequency_interval',e.target.value===''?null:Number(e.target.value))}/></label>}
      {included&&<label className="block"><FieldCaption>Номер строки родительской работы в Excel</FieldCaption><Input aria-label="Номер строки родительской работы в Excel" type="number" min={1} max={1048576} value={draft.included_in_row??''} onChange={e=>field('included_in_row',e.target.value===''?null:Number(e.target.value))}/><small>Выберите подтверждённую самостоятельную работу этого каталога с тем же оборудованием. Собственная норма не добавляется.</small></label>}
      {!included&&draft.frequency_kind!=='event'&&<div className="space-y-3"><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={!!draft.calendar_pattern} onChange={e=>{
        const frequency=(draft.frequency_kind==='daily_events'?'day':['day','week','month','quarter','year','yearly_count','dates'].includes(draft.frequency_kind)?draft.frequency_kind:'month') as CalendarPattern['frequency'];
        const pattern=patternDefaults(`${draft.calendar_year??2027}-01-01`,frequency);if(frequency==='yearly_count')pattern.count_per_year=draft.frequency_interval??1;else pattern.interval=['daily_events','dates'].includes(draft.frequency_kind)?1:draft.frequency_interval??1;
        field('calendar_pattern',e.target.checked?pattern:null);
      }}/><span>Задать календарное правило для других месяцев</span></label><p className="text-sm text-muted">Для годового расчёта подтвердите опорную дату и правило. Январские отметки сами по себе на другие месяцы не переносятся.</p>
        {draft.calendar_pattern&&<Suspense fallback={<LoadingState/>}><PatternEditor allowedFrequencies={draft.frequency_kind==='unconfirmed'?undefined:[(draft.frequency_kind==='daily_events'?'day':draft.frequency_kind) as CalendarPattern['frequency']]} value={draft.calendar_pattern} onChange={value=>field('calendar_pattern',value)}/></Suspense>}
        {draft.calendar_pattern&&<><p className="text-sm text-muted">Правило задаёт обязательные сроки; допуск заранее определяет начало окна до каждого срока. Полоса января на другие месяцы не копируется.</p><label className="block"><FieldCaption>Допуск выполнения заранее, дней</FieldCaption><Input aria-label="Допуск выполнения заранее, дней" type="number" min={0} max={366} disabled={['day','daily_events'].includes(draft.frequency_kind)} value={draft.allowed_lead_days??0} onChange={e=>field('allowed_lead_days',Number(e.target.value))}/></label></>}
      </div>}
  </>;
  const assetFields=<>
      <h4 className="font-semibold">Оборудование текущего здания</h4>
      <ul className="space-y-2">{draft.equipment_ids.map(identity=>{const item=equipment.find(e=>e.equipment_id===identity);return <li key={identity} className="break-words text-sm">{item?`${item.asset_code} · ${item.name}`:identity} <Button variant="ghost" onClick={()=>field('equipment_ids',draft.equipment_ids.filter(i=>i!==identity))} aria-label={`Убрать ${item?.asset_code??identity}`}>Убрать</Button></li>;})}</ul>
      <p className="text-sm text-muted">Выбрано единиц: {draft.equipment_ids.length}. Количество определяется реальным реестром.</p>
      {mayEdit&&<BindingPicker id={id} selected={draft.equipment_ids} onAdd={item=>{setEquipment(items=>[...items.filter(e=>e.equipment_id!==item.equipment_id),item]);field('equipment_ids',[...draft.equipment_ids,item.equipment_id]);}}/>}
      {!included&&<><h4 className="font-semibold">Норматив одного выполнения</h4>
        <label className="block"><FieldCaption>Норма времени</FieldCaption><Input aria-label="Норма времени" type="number" min="0.001" max="999999999.999" step="0.001" value={draft.norm_value??''} onChange={e=>field('norm_value',e.target.value||null)}/></label>
        <label className="block"><FieldCaption>Единица нормы</FieldCaption><Select aria-label="Единица нормы" value={draft.norm_unit} onChange={e=>field('norm_unit',e.target.value as CatalogDecision['norm_unit'])}><option value="unconfirmed">Не подтверждена</option><option value="person_hour">Человеко-часы</option><option value="elapsed_hour">Часы длительности бригады</option></Select></label>
        <label className="block"><FieldCaption>База нормы</FieldCaption><Select aria-label="База нормы" value={draft.norm_scope} onChange={e=>field('norm_scope',e.target.value as CatalogDecision['norm_scope'])}><option value="unconfirmed">Не подтверждена</option><option value="per_asset">На одну единицу оборудования</option><option value="whole_binding">На весь выбранный комплекс</option></Select></label>
        <label className="block"><FieldCaption>Человек в бригаде</FieldCaption><Input aria-label="Человек в бригаде" type="number" min={1} max={100} value={draft.crew_size??''} onChange={e=>field('crew_size',e.target.value===''?null:Number(e.target.value))}/></label>
        <label className="block"><FieldCaption>Источник и методика нормы</FieldCaption><Textarea aria-label="Источник и методика нормы" maxLength={2000} value={draft.norm_ref} onChange={e=>field('norm_ref',e.target.value)}/></label></>}
  </>;
  const ruleFields=<>
      <h4 className="font-semibold">Правила выполнения</h4>
      <label className="block"><FieldCaption>Можно разделять работу на сегменты</FieldCaption><Select aria-label="Можно разделять работу на сегменты" value={draft.splittable===null?'unknown':String(draft.splittable)} onChange={e=>{const value=e.target.value;field('splittable',value==='unknown'?null:value==='true');if(value!=='true')field('min_segment_minutes',null);}}><option value="unknown">Не подтверждено</option><option value="false">Нет, выполнять целиком</option><option value="true">Да, с сохранением общего объёма часов</option></Select></label>
      {draft.splittable&&<label className="block"><FieldCaption>Минимальный сегмент, минут</FieldCaption><Input aria-label="Минимальный сегмент, минут" type="number" min={1} max={46080} value={draft.min_segment_minutes??''} onChange={e=>field('min_segment_minutes',e.target.value===''?null:Number(e.target.value))}/></label>}
      <label className="block"><FieldCaption>Правила и ограничения выполнения</FieldCaption><Textarea aria-label="Правила и ограничения выполнения" maxLength={2000} value={draft.policy_note} onChange={e=>field('policy_note',e.target.value)}/></label>
      <h4 className="font-semibold">Требования к допускам для планирования</h4>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={draft.qualifications_confirmed??false} onChange={e=>field('qualifications_confirmed',e.target.checked)}/><span>Требования к допускам проверены инженером</span></label>
      <p className="text-sm text-muted">Выберите обязательные допуски. Пустой список можно подтвердить с обоснованием отсутствия специальных требований.</p>
      <ul className="space-y-2">{(draft.qualification_ids??[]).slice(qualificationOffset,qualificationOffset+25).map(identity=><li key={identity}>{qualificationLabels[identity]??`Допуск ${identity}`} <Button variant="ghost" onClick={()=>field('qualification_ids',(draft.qualification_ids??[]).filter(i=>i!==identity))}>Убрать допуск</Button></li>)}</ul>
      <PlanningPages offset={qualificationOffset} total={draft.qualification_ids?.length??0} onPage={setQualificationOffset}/>
      {mayEdit&&<PlanningChoices kind="skills" selected={draft.qualification_ids??[]} onAdd={item=>{setQualificationLabels(labels=>({...labels,[item.id]:item.label}));field('qualification_ids',[...(draft.qualification_ids??[]),item.id]);}}/>}
      <label className="block"><FieldCaption>Основание требований к допускам</FieldCaption><Textarea aria-label="Основание требований к допускам" maxLength={2000} value={draft.qualification_note??''} onChange={e=>field('qualification_note',e.target.value)}/></label>
  </>;
  const confirmationFields=<>
      <label className="block"><FieldCaption>Причина новой версии</FieldCaption><Textarea aria-label="Причина новой версии" maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)}/></label>
      {mayEdit&&<div className="flex flex-wrap gap-3"><Button variant="secondary" disabled={!reason.trim()} onClick={()=>void save(false)}>Сохранить решение-черновик</Button>{mayConfirm&&<Button disabled={!reason.trim()} onClick={()=>void save(true)}>Подтвердить решение строки</Button>}</div>}
  </>;
  const controls=(children:ReactNode)=><fieldset disabled={!mayEdit||busy} className="min-w-0 space-y-4">{children}</fieldset>;
  return <section className="catalog-decision-editor min-w-0 space-y-4" aria-label="Решение инженера по строке">
    <h3 className="font-semibold">Решение инженера · версия {saved.revision}</h3>
    <p className="text-sm">{saved.prepared?'Подготовлено для планировщика':saved.confirmed?'Подтверждение требует проверки':'Черновик решения'}. Исходные ячейки сохранены отдельно.</p>
    {saved.created_by&&<p className="break-words text-xs text-muted">Автор: {saved.author_name??saved.created_by} · {saved.created_at}</p>}
    <Callout>Подтверждение строки не публикует план. Часы относятся к одному выполнению выбранной работы. Проверка смен, сроков и нагрузки будет выполняться в планировщике.</Callout>
    {saved.blockers.length>0&&<ul className="space-y-1 text-sm" aria-label="Что нужно уточнить">{saved.blockers.map(b=><li key={b}>{decisionBlockers[b]??b}</li>)}</ul>}
    {dirty&&<p role="status" className="text-sm">Есть несохранённые изменения. Статус и часы выше относятся к сохранённой версии.</p>}
    {!dirty&&saved.total_person_hours!==null&&<p aria-label="Расчёт трудозатрат">{saved.total_person_hours} чел.-ч · {saved.elapsed_hours} ч длительности{included?' · учтено у родителя':''}</p>}
    {guided?<JourneySteps label="Подготовка операции" value={step} onChange={setStep} steps={[
      {id:'dates',title:'Даты и периодичность',content:()=> <>{controls(datesFields)}<div className="journey-footer"><Button variant="secondary" onClick={()=>setStep('assets')}> Далее: оборудование и часы →</Button></div></>},
      {id:'assets',title:'Оборудование и часы',content:()=> <>{controls(assetFields)}<div className="journey-footer"><Button variant="secondary" onClick={()=>setStep('rules')}> Далее: условия выполнения →</Button></div></>},
      {id:'rules',title:'Условия и допуски',content:()=> <>{controls(ruleFields)}<div className="journey-footer"><Button variant="secondary" onClick={()=>setStep('confirm')}> Далее: проверить и подтвердить →</Button></div></>},
      {id:'confirm',title:'Подтверждение',content:()=> <>{controls(confirmationFields)}</>},
    ]}/>:<fieldset disabled={!mayEdit||busy} className="min-w-0 space-y-4">{datesFields}{assetFields}{ruleFields}{confirmationFields}</fieldset>}
    {mayEdit&&!mayConfirm&&<p className="text-sm text-muted">Подтверждение требует отдельного полномочия.</p>}
    {error&&<div role="alert"><Callout tone="danger">{error}</Callout><p className="text-sm">Введённые значения остаются в форме. Загрузка актуальной версии заменит их серверными данными.</p><Button variant="secondary" onClick={reload}>Загрузить актуальную версию</Button></div>}
    {notice&&<p role="status">{notice}</p>}
    <Button variant="ghost" aria-expanded={history} onClick={()=>setHistory(value=>!value)}>История решений строки</Button>
    {history&&<DecisionHistory key={saved.revision} id={id} row={row}/>}
  </section>;
}

function BindingPicker({id,selected,onAdd}:{id:string;selected:string[];onAdd:(item:CatalogBinding)=>void}) {
  const [search,setSearch]=useState(''),[offset,setOffset]=useState(0),[open,setOpen]=useState(false);
  const needle=useDeferredValue(search);
  return <div className="space-y-3"><Button variant="secondary" aria-expanded={open} disabled={selected.length>=100} onClick={()=>setOpen(value=>!value)}>Выбрать оборудование</Button>{open&&<>
    <label className="block"><FieldCaption>Поиск оборудования для привязки</FieldCaption><Input aria-label="Поиск оборудования для привязки" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/></label>
    <BindingResults id={id} q={needle} offset={offset} selected={selected} onAdd={onAdd} onPage={setOffset}/>
  </>}</div>;
}
function BindingResults({id,q,offset,selected,onAdd,onPage}:{id:string;q:string;offset:number;selected:string[];onAdd:(item:CatalogBinding)=>void;onPage:(offset:number)=>void}) {
  const query=useApiQuery(()=>api.bindingOptions(id,q,offset),[id,q,offset],undefined,`catalog-binding:${JSON.stringify([id,q,offset])}`);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  return <><ul className="space-y-2">{query.data.items.map(item=><li key={item.equipment_id}><Button variant="secondary" disabled={selected.includes(item.equipment_id)||selected.length>=100} onClick={()=>onAdd(item)}>{item.asset_code} · {item.name}</Button></li>)}</ul>{!query.data.total&&<p>Действующее оборудование не найдено.</p>}<Pages offset={offset} total={query.data.total} onPage={onPage}/></>;
}
function Pages({offset,total,onPage}:{offset:number;total:number;onPage:(offset:number)=>void}) {return total>25&&<div className="flex flex-wrap items-center gap-3"><Button variant="secondary" disabled={!offset} onClick={()=>onPage(offset-25)}>Предыдущие</Button><span>{offset+1}–{Math.min(offset+25,total)} из {total}</span><Button variant="secondary" disabled={offset+25>=total} onClick={()=>onPage(offset+25)}>Следующие</Button></div>;}
function DecisionHistory({id,row}:{id:string;row:number}) {
  const [offset,setOffset]=useState(0);
  const query=useApiQuery(()=>api.history(id,row,offset),[id,row,offset],undefined,`catalog-history:${id}:${row}:${offset}`);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  return <div className="space-y-3"><ol className="space-y-2">{query.data.items.map(item=><li className="break-words text-sm" key={item.revision}><details>
    <summary>Версия {item.revision} · {item.confirmed?'Подтверждена':'Черновик'} · {item.reason}</summary>
    <p>{item.created_at} · {item.author_name??item.created_by}</p>
    {item.parent_revision!==null&&<p>Версия родительской работы: {item.parent_revision}</p>}
    <ul>{item.equipment.map(asset=><li key={asset.equipment_id}>{asset.asset_code} · {asset.name} · ревизия {asset.revision}</li>)}</ul>
    <pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(item.decision,null,2)}</pre>
  </details></li>)}</ol>{!query.data.total&&<p>Сохранённых решений пока нет.</p>}<Pages offset={offset} total={query.data.total} onPage={setOffset}/></div>;
}
