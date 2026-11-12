import { readQueries } from "@/shared/api/readQueries";
import { Disclosure } from "@/shared/ui/Disclosure";
import { ServiceEvidenceSettings } from "@/features/analyst/AnalystPanels";
import { ConnectionRequired } from "@/shared/ui/ConnectionRequired";
import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { managementApi } from "@/shared/api/management";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate, todayAt } from "@/shared/lib/format";
import { unitLabel } from "@/shared/lib/presentation";
import { FormErrors, RuleSection, revealField, sectionErrors, type FieldError } from "@/features/settings/SectionForm";
import { canOpenSection } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { patternDefaults } from "@/shared/types/management";
import type { EquipmentInput, EquipmentRecord, ManagementCatalog, ServiceConfiguration,ChecklistSetting } from "@/shared/types/management";
import { CalendarPatternEditor } from "@/features/settings/CalendarPatternEditor";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { FieldCaption, Input, Select  } from "@/shared/ui/Form";
import { Card, CardHeader } from "@/shared/ui/Card";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Callout } from "@/shared/ui/Callout";
import { LoadingState, ErrorState } from "@/shared/ui/States";

export function ServiceSettingsPage() {
  return DEMO_MODE ? <ConnectionRequired title="Настройка обслуживания" description="Оборудование, регламенты и правила календаря." capabilities={["Создание оборудования и привязка операций", "Периодичность, нормативы и чек-листы", "Проверка исходных данных перед планированием"]}/> : <LiveServiceSettingsPage/>;
}
function LiveServiceSettingsPage() {
  const {profile}=useSession();
  const [params,setParams]=useSearchParams();
  const selected=params.get("equipment")??"";
  const [refresh,setRefresh]=useState(0);
  const [notice,setNotice]=useState("");
  const query=useApiQuery(readQueries.serviceIndex.load,[refresh],undefined,readQueries.serviceIndex.key);
  const mayEdit=profile?.role==="admin"||profile?.role==="chief_engineer";
  const today=todayAt(profile?.timezone??"Asia/Yekaterinburg");

  if(query.status==="loading") return <LoadingState label="Загрузка настроек обслуживания"/>;
  if(query.status==="error") return <ErrorState description={query.error}/>;
  const [catalog,equipment]=query.data;
  return <div className="space-y-6">
    <PageHeader title="Настройка обслуживания" description="Календарь строится из этих правил. Создание заданий и назначение работников требуют отдельных действий." actions={canOpenSection(profile?.role,"calendar")&&<Link to="/calendar" className={buttonClassName("secondary")}>Открыть календарь</Link>}/>
    {notice&&<Callout tone="success">{notice}</Callout>}
    <Card className="space-y-3 p-5"><label className="block space-y-1 text-sm"><FieldCaption>Оборудование для настройки
      </FieldCaption><Select aria-label="Оборудование для настройки" value={selected} onChange={event=>{setNotice("");setParams(event.target.value ? {equipment:event.target.value} : {});}}>
        <option value="">{mayEdit ? "Новое оборудование" : "Выберите оборудование"}</option>
        {equipment.map(item=><option key={item.id} value={item.id}>{item.inventoryCode} · {item.name}</option>)}
      </Select>
    </label><p className="text-xs text-muted">Время объекта: {profile?.timezone}. Нормативная дата относится к целым местным суткам.</p></Card>
    {mayEdit&&<ReferenceForms catalog={catalog} mayCreateTypes={profile?.role==="admin"} onSaved={()=>setRefresh(value=>value+1)}/>}
    {(selected||mayEdit)&&<details className="fr-rule-section" open={!selected}><summary><span>{selected ? "Паспорт оборудования" : "Новое оборудование"}</span><small>Отдельное сохранение свойств оборудования</small></summary><EquipmentSettings key={selected} equipmentId={selected} catalog={catalog} mayEdit={mayEdit}
      onSaved={key=>{setNotice("Оборудование сохранено");setParams({equipment:key});setRefresh(value=>value+1);}}/></details>}
    {selected&&<ServiceList key={`${selected}:${refresh}`} equipmentId={selected} catalog={catalog} today={today} mayEdit={mayEdit}/>}
  </div>;
}

function EquipmentSettings({equipmentId,catalog,mayEdit,onSaved}: {equipmentId:string;catalog:ManagementCatalog;mayEdit:boolean;onSaved:(key:string)=>void}) {
  const query=useApiQuery(()=>equipmentId ? managementApi.getEquipment(equipmentId) : Promise.resolve(null),[equipmentId],undefined,equipmentId?undefined:"new-equipment-form");
  if(query.status==="loading") return <LoadingState label="Загрузка оборудования"/>;
  if(query.status==="error") return <ErrorState description={query.error}/>;
  return <EquipmentEditor key={query.data?.revision??"new"} initial={query.data} catalog={catalog} mayEdit={mayEdit} onSaved={onSaved}/>;
}

function EquipmentEditor({initial,catalog,mayEdit,onSaved}: {initial:EquipmentRecord|null;catalog:ManagementCatalog;mayEdit:boolean;onSaved:(key:string)=>void}) {
  const [value,setValue]=useState<EquipmentInput>(initial ? {
    system_id:initial.system_id,equipment_type_id:initial.equipment_type_id??"",asset_code:initial.asset_code,name:initial.name,
    parent_equipment_id:initial.parent_equipment_id,serial_number:initial.serial_number,commissioned_on:initial.commissioned_on,
    location:initial.location,status:initial.status,data_origin:initial.properties.data_origin==="synthetic_demo" ? "synthetic_demo" : "customer",expected_revision:initial.revision,
  } : {system_id:catalog.systems[0]?.id??"",equipment_type_id:catalog.equipment_types[0]?.id??"",asset_code:"",name:"",parent_equipment_id:null,serial_number:null,commissioned_on:null,location:null,status:"active",data_origin:"customer"});
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const set=(part:Partial<EquipmentInput>)=>setValue({...value,...part});
  return <Card><CardHeader title={initial ? "Параметры оборудования" : "Добавить оборудование"}/><form className="space-y-4 p-5" onSubmit={async event=>{
    event.preventDefault();if(busy) return;setBusy(true);setError("");
    try {const saved=await managementApi.saveEquipment(value,initial?.equipment_id);onSaved(saved.equipment_id);}
    catch(failure){setError(failure instanceof Error?failure.message:"Не удалось сохранить");}finally{setBusy(false);}
  }}><fieldset disabled={busy||!mayEdit} className="grid gap-4 sm:grid-cols-2">
    <label className="space-y-1 text-sm"><FieldCaption>Инвентарный номер</FieldCaption><Input aria-label="Инвентарный номер" required value={value.asset_code} onChange={e=>set({asset_code:e.target.value})}/></label>
    <label className="space-y-1 text-sm"><FieldCaption>Название оборудования</FieldCaption><Input aria-label="Название оборудования" required value={value.name} onChange={e=>set({name:e.target.value})}/></label>
    <label className="space-y-1 text-sm"><FieldCaption>Инженерная система</FieldCaption><Select aria-label="Инженерная система" required value={value.system_id} onChange={e=>set({system_id:e.target.value})}>{catalog.systems.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>
    <label className="space-y-1 text-sm"><FieldCaption>Тип оборудования</FieldCaption><Select aria-label="Тип оборудования" value={value.equipment_type_id??''} onChange={e=>set({equipment_type_id:e.target.value||null})}><option value="">Не указан</option>{catalog.equipment_types.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>
    <label className="space-y-1 text-sm"><FieldCaption>Дата ввода, если известна</FieldCaption><Input aria-label="Дата ввода" type="date" value={value.commissioned_on??''} onChange={e=>set({commissioned_on:e.target.value||null})}/></label>
    <label className="space-y-1 text-sm"><FieldCaption>Расположение</FieldCaption><Input aria-label="Расположение" value={value.location??""} onChange={e=>set({location:e.target.value||null})}/></label>
    <label className="space-y-1 text-sm"><FieldCaption>Серийный номер</FieldCaption><Input aria-label="Серийный номер" value={value.serial_number??""} onChange={e=>set({serial_number:e.target.value||null})}/></label>
    <label className="space-y-1 text-sm"><FieldCaption>Состояние оборудования</FieldCaption><Select aria-label="Состояние оборудования" value={value.status} onChange={e=>set({status:e.target.value as EquipmentInput["status"]})}><option value="active">В эксплуатации</option><option value="under_repair">В ремонте</option><option value="retired">Списано</option></Select></label>
  </fieldset>{error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}
    {mayEdit&&<Button type="submit" disabled={busy}>{busy ? "Сохранение…" : "Сохранить оборудование"}</Button>}
  </form></Card>;
}

function ServiceList({equipmentId,catalog,today,mayEdit}: {equipmentId:string;catalog:ManagementCatalog;today:string;mayEdit:boolean}) {
  const [refresh,setRefresh]=useState(0);const [editing,setEditing]=useState<ServiceConfiguration|null|undefined>();
  const [notice,setNotice]=useState("");
  const query=useApiQuery(()=>Promise.all([managementApi.services(equipmentId),managementApi.getEquipment(equipmentId)]),[equipmentId,refresh]);
  if(query.status==="loading") return <LoadingState label="Загрузка правил обслуживания"/>;
  if(query.status==="error") return <ErrorState description={query.error}/>;
  const [services,equipment]=query.data;
  return <section aria-label="Правила обслуживания" className="space-y-4"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Правила обслуживания</h2>{mayEdit&&<Button variant="secondary" onClick={()=>{setEditing(null);setNotice("");}}>Добавить обслуживание</Button>}</div>
    {notice&&<Callout tone="success">{notice}</Callout>}
    {!services.length&&<Callout>Для оборудования ещё не задано обслуживание. Добавьте операцию, длительность и периодичность.</Callout>}
    <details className="fr-rule-section" open={editing===undefined||undefined}><summary><span>Регламенты оборудования · {services.length}</span><small>{editing===undefined ? "Выберите обслуживание для настройки" : "Другие правила доступны без закрытия редактора"}</small></summary><div className="space-y-3 pb-4">{services.map(item=><Card key={item.binding_id} className="space-y-2 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">{item.code} · {item.title}</h3>{mayEdit&&<Button variant="ghost" onClick={()=>{setEditing(item);setNotice("");}}>Настроить</Button>}</div><p className="text-sm text-muted">Версия {item.rule_version} · {item.enabled ? "Действует" : "Отключено"} · {item.crew_size} чел. · {item.duration_minutes??"не задано"} мин.</p><p className="text-sm">{item.source_text}</p></Card>)}</div></details>
    {editing!==undefined&&<ServiceEditor key={editing?.binding_id??"new"} initial={editing} today={today} catalog={catalog} systemId={equipment.system_id} onClose={()=>setEditing(undefined)} onSave={async body=>{
      await managementApi.saveService(equipmentId,body,editing?.binding_id);setEditing(undefined);setNotice("Правило сохранено. Пересчитайте календарь, чтобы увидеть даты.");setRefresh(n=>n+1);
    }}/>}
  </section>;
}

function ServiceEditor({initial,today,catalog,systemId,onClose,onSave}: {initial:ServiceConfiguration|null;today:string;catalog:ManagementCatalog;systemId:string;onClose:()=>void;onSave:(value:ServiceConfiguration)=>Promise<void>}) {
  const [value,setValue]=useState<ServiceConfiguration>(initial ? {...initial,pattern:initial.pattern??patternDefaults(today),expected_revision:initial.revision} : {
    code:"",title:"",instructions:"",maintenance_type:"ТО2",pattern:{...patternDefaults(today),quarter_policy:"rolling_months",annual_policy:"from_anchor",weekend_policy:"next_workday"},valid_from:today,valid_until:null,crew_size:1,norm_value:null,norm_unit:"unconfirmed",duration_minutes:null,qualification_ids:[],checklist:[newCheck()],allowed_lead_days:0,enabled:false,methodology_ref:"",measurement_requirements:[],required_acts:[],
  });
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [errors,setErrors]=useState<FieldError[]>([]);const [dirty,setDirty]=useState(false);
  const formRef=useRef<HTMLFormElement>(null);
  const set=(part:Partial<ServiceConfiguration>)=>{setDirty(true);setValue({...value,...part});};
  const periodSummary = `${value.basis==="after_accepted_completion" ? "От фактического выполнения принятой работы" : "Фиксированный календарь"} · ${value.pattern ? frequencyLabel[value.pattern.frequency] : "Правило не задано"} · с ${formatDate(value.pattern?.anchor_date??null)}`;
  return <section className="fr-settings-workspace" aria-label="Редактор обслуживания"><h3 className="text-xl font-semibold">{initial ? "Изменить обслуживание" : "Новое обслуживание"}</h3><p className="mt-2 text-sm text-muted">{value.code} · {value.title}</p><form ref={formRef} noValidate className="mt-4" onSubmit={async event=>{
    event.preventDefault();if(busy)return;
    const invalid=sectionErrors(event.currentTarget);setErrors(invalid);
    if(invalid.length){revealField(invalid[0].field);return;}
    if(value.pattern?.frequency==="dates"&&!value.pattern.dates.length){setError("Добавьте даты обслуживания.");const input=event.currentTarget.querySelector<HTMLElement>('[aria-label="Даты обслуживания: новая дата"]');if(input)revealField(input);return;}
    setBusy(true);setError("");try{await onSave(value);}catch(failure){setError(failure instanceof Error?failure.message:"Ошибка сохранения");}finally{setBusy(false);}
  }}><FormErrors errors={errors}/><fieldset disabled={busy} className="fr-settings-grid"><div className="fr-settings-main">
    {initial&&<Callout>Изменение создаёт новую версию с выбранной даты. Сохранённые задания и история сохраняются; конфликтующие будущие задания нужно сначала отменить.</Callout>}
    <RuleSection title="Основное" summary={value.title||"Операция, название и период действия"} open errors={errors}>
    {!initial&&<label className="block space-y-1 text-sm"><FieldCaption>Использовать существующую операцию</FieldCaption><Select aria-label="Использовать существующую операцию" value={value.operation_id??''} onChange={e=>{
      const op=catalog.operations.find(row=>row.id===e.target.value);
      set(op ? {operation_id:op.id,code:op.code,title:op.title,instructions:op.instructions,maintenance_type:op.maintenance_type} : {operation_id:undefined,code:'',title:'',instructions:''});
    }}><option value="">Новая операция</option>{catalog.operations.filter(op=>op.system_id===systemId).map(op=><option key={op.id} value={op.id}>{op.code} · {op.title}</option>)}</Select><p className="text-xs text-muted"><FieldCaption>Периодичность, норма, длительность и чек-лист этой единицы оборудования задаются ниже.</FieldCaption></p></label>}
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="space-y-1 text-sm"><FieldCaption>Код операции</FieldCaption><Input aria-label="Код операции" required readOnly={!!initial||!!value.operation_id} value={value.code} onChange={e=>set({code:e.target.value})}/></label>
      <label className="space-y-1 text-sm"><FieldCaption>Название обслуживания</FieldCaption><Input aria-label="Название обслуживания" required value={value.title} onChange={e=>set({title:e.target.value})}/></label>
      <label className="space-y-1 text-sm"><FieldCaption>Вид ТО</FieldCaption><Select aria-label="Вид ТО" value={value.maintenance_type} onChange={e=>set({maintenance_type:e.target.value as "ТО1"|"ТО2"|"ТО3"})}><option>ТО1</option><option>ТО2</option><option>ТО3</option></Select></label>
      <label className="space-y-1 text-sm"><FieldCaption>Действует с</FieldCaption><Input aria-label="Действует с" type="date" required value={value.valid_from} onChange={e=>set({valid_from:e.target.value})}/></label>
      <label className="space-y-1 text-sm"><FieldCaption>Действует по</FieldCaption><Input aria-label="Действует по" type="date" value={value.valid_until??""} onChange={e=>set({valid_until:e.target.value||null})}/></label>
    </div></RuleSection>
    <RuleSection title="Трудоёмкость и состав" summary={`${value.norm_value??"Норма не задана"} ${unitLabel(value.norm_unit)} · ${value.duration_minutes??"—"} мин. · ${value.crew_size} чел.`} errors={errors}><div className="grid gap-4 sm:grid-cols-2">
      <label className="space-y-1 text-sm"><FieldCaption>Сотрудников одновременно</FieldCaption><Input aria-label="Сотрудников одновременно" type="number" required min={1} max={100} value={value.crew_size} onChange={e=>set({crew_size:Number(e.target.value)})}/></label>
      <label className="space-y-1 text-sm"><FieldCaption>Исходная норма труда</FieldCaption><Input aria-label="Исходная норма труда" type="number" min={0} step="0.001" required={value.enabled} value={value.norm_value??""} onChange={e=>set({norm_value:e.target.value||null})}/></label>
      <label className="space-y-1 text-sm"><FieldCaption>Единица нормы</FieldCaption><Select aria-label="Единица нормы" required={value.enabled} value={value.norm_unit==="unconfirmed"?"":value.norm_unit} onChange={e=>set({norm_unit:(e.target.value||"unconfirmed") as "person_hour"|"elapsed_hour"|"unconfirmed"})}><option value="">Выберите единицу</option><option value="person_hour">Человеко-часы, всего на работу</option><option value="elapsed_hour">Часы работы всего состава</option></Select></label>
      <label className="space-y-1 text-sm"><FieldCaption>Длительность работы, минут</FieldCaption><Input aria-label="Длительность работы, минут" type="number" min={1} max={46080} required={value.enabled} value={value.duration_minutes??""} onChange={e=>set({duration_minutes:e.target.value?Number(e.target.value):null})}/></label>
      <label className="space-y-1 text-sm"><FieldCaption>Разрешено раньше срока, дней</FieldCaption><Input aria-label="Разрешено раньше срока, дней" type="number" min={0} max={366} required value={value.allowed_lead_days} onChange={e=>set({allowed_lead_days:Number(e.target.value)})}/></label>
    </div><p className="text-xs text-muted">Норма труда и длительность задаются отдельно. Значение нормы не превращается автоматически в минуты.</p>
    </RuleSection>
    <RuleSection title="Периодичность" summary={periodSummary} open errors={errors}>
    <label className="block space-y-1 text-sm"><FieldCaption>Отсчёт обслуживания</FieldCaption><Select aria-label="Отсчёт обслуживания" value={value.basis??"fixed_calendar"} onChange={e=>set({basis:e.target.value as "fixed_calendar"|"after_accepted_completion",pattern:{...patternDefaults(value.pattern!.anchor_date,e.target.value==="after_accepted_completion" ? "month" : "week"),quarter_policy:"rolling_months",annual_policy:"from_anchor",weekend_policy:"next_workday"}})}><option value="fixed_calendar">Фиксированный календарь</option><option value="after_accepted_completion">От последнего принятого выполнения</option></Select></label>
    {value.basis==="after_accepted_completion"&&<p className="text-xs text-muted">Без истории опорная дата — первый срок. После приёмки следующий срок считается от даты выполнения. Будущие выполнения не предполагаются.</p>}
    <CalendarPatternEditor value={value.pattern!} rolling={value.basis==="after_accepted_completion"} onChange={pattern=>set({pattern})}/>
    </RuleSection>
    <RuleSection title="Методика и доказательства" summary={`${value.measurement_requirements?.length??0} требований к показаниям · ${value.required_acts?.length??0} документов`} errors={errors}>
    <label className="block space-y-1 text-sm"><FieldCaption>Инструкция</FieldCaption><textarea aria-label="Инструкция" required className="w-full rounded-lg border border-line bg-canvas p-3" value={value.instructions} onChange={e=>set({instructions:e.target.value})}/></label>
    <ServiceEvidenceSettings value={value} onChange={set}/>
    </RuleSection>
    <RuleSection title="Чек-лист исполнения" summary={`${value.checklist.length} пунктов · обязательных: ${value.checklist.filter(item=>item.required).length}`} errors={errors}>
    <ChecklistEditor value={value.checklist} onChange={checklist=>set({checklist})}/>
    </RuleSection>
    <RuleSection title="Допуски работников" summary={`Выбрано: ${value.qualification_ids.length}`} errors={errors}>
    <fieldset className="space-y-2"><legend className="text-sm">Обязательные допуски каждого работника</legend>{catalog.skills.map(skill=><label key={skill.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.qualification_ids.includes(skill.id)} onChange={e=>set({qualification_ids:e.target.checked?[...value.qualification_ids,skill.id]:value.qualification_ids.filter(id=>id!==skill.id)})}/>{skill.name}</label>)}</fieldset>
    </RuleSection></div><aside className="fr-settings-rail" aria-label="Резюме правила"><h4 className="text-lg font-semibold">Резюме правила</h4><p>{periodSummary}</p><dl><div><dt>Норма труда</dt><dd>{value.norm_value??"Не задана"} {unitLabel(value.norm_unit)}</dd></div><div><dt>Длительность и состав</dt><dd>{value.duration_minutes??"Не задана"} мин. · {value.crew_size} чел.</dd></div><div><dt>Требования</dt><dd>{value.checklist.length} пунктов · {value.qualification_ids.length} допусков</dd></div></dl><p className="text-sm text-muted">{dirty ? "Изменения не сохранены" : initial ? "Сохранённая версия регламента" : "Новое правило ещё не сохранено"}</p>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.enabled} onChange={e=>set({enabled:e.target.checked})}/>Утвердить и опубликовать (главный инженер)</label>
    {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}
    <div className="fr-settings-actions"><Button type="submit" disabled={busy}>{busy?"Сохранение…":"Сохранить обслуживание"}</Button><Button variant="ghost" type="button" disabled={busy} onClick={onClose}>Закрыть редактор</Button></div>
  </aside></fieldset></form></section>;
}

const frequencyLabel = { day: "Дни", week: "Недели", month: "Месяцы", quarter: "Кварталы", year: "Годы", yearly_count: "Число повторений в годовом цикле", dates: "Конкретные даты" };

function newCheck():ChecklistSetting {
  return {text:'Проверить оборудование',answer_kind:'boolean',unit:null,required:true,visual_verifiability:'not_verifiable',photo_required:false};
}

function ChecklistEditor({value,onChange}:{value:ChecklistSetting[];onChange:(value:ChecklistSetting[])=>void}) {
  const edit=(index:number,part:Partial<ChecklistSetting>)=>onChange(value.map((row,i)=>i===index?{...row,...part}:row));
  return <fieldset className="fr-checklist"><legend className="sr-only">Пункты чек-листа</legend>{value.map((row,index)=><details key={index} className="fr-checklist-row" open={index===0||undefined}><summary>{index+1}. {row.text||"Новый пункт"}<small>{row.answer_kind==="number" ? "Числовое показание" : row.answer_kind==="boolean" ? "Отметка выполнения" : "Текст"} · {row.required ? "Обязательный" : "Необязательный"}{row.photo_required ? " · Фото до и после" : ""}</small></summary><div className="fr-checklist-fields">
    <label className="block text-sm"><FieldCaption>Пункт {index+1}</FieldCaption><Input aria-label={`Пункт ${index+1}`} required maxLength={2000} value={row.text} onChange={e=>edit(index,{text:e.target.value})}/></label>
    <div className="grid gap-3 sm:grid-cols-3"><label className="text-sm"><FieldCaption>Вид ответа</FieldCaption><Select aria-label={`Вид ответа ${index+1}`} value={row.answer_kind} onChange={e=>edit(index,{answer_kind:e.target.value as ChecklistSetting['answer_kind']})}><option value="boolean">Отметка выполнения</option><option value="number">Числовое показание</option><option value="text">Текст</option></Select></label>
    <label className="text-sm"><FieldCaption>Единица показания</FieldCaption><Input aria-label={`Единица показания ${index+1}`} value={row.unit??''} onChange={e=>edit(index,{unit:e.target.value||null})}/></label>
    <label className="text-sm"><FieldCaption>Проверяемость по фото</FieldCaption><Select aria-label={`Проверяемость по фото ${index+1}`} value={row.visual_verifiability} onChange={e=>edit(index,{visual_verifiability:e.target.value as ChecklistSetting['visual_verifiability']})}><option value="not_verifiable">По фото не подтверждается</option><option value="partial">Частично видна</option><option value="visible">Результат виден</option></Select></label></div>
    <div className="flex flex-wrap items-center gap-4 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={row.required} onChange={e=>edit(index,{required:e.target.checked})}/>Обязательный пункт</label><label className="flex items-center gap-2"><input type="checkbox" checked={row.photo_required} onChange={e=>edit(index,{photo_required:e.target.checked})}/>Требуются фото до и после</label><Button type="button" variant="ghost" disabled={value.length===1} onClick={()=>onChange(value.filter((_,i)=>i!==index))}>Убрать пункт</Button></div>
  </div></details>)}<Button type="button" variant="secondary" disabled={value.length>=100} onClick={()=>onChange([...value,newCheck()])}>Добавить пункт чек-листа</Button></fieldset>;
}

function ReferenceForms({catalog,mayCreateTypes,onSaved}: {catalog:ManagementCatalog;mayCreateTypes:boolean;onSaved:()=>void}) {
  const [kind,setKind]=useState<"systems"|"equipment-types">("systems");const [code,setCode]=useState("");const [name,setName]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  return <Disclosure title="Добавить систему или тип оборудования"><form className="mt-4 space-y-3" onSubmit={async event=>{event.preventDefault();if(busy)return;setBusy(true);setError("");try{await managementApi.createReference(kind,{code,name});onSaved();}catch(failure){setError(failure instanceof Error?failure.message:"Ошибка справочника");}finally{setBusy(false);}}}>
    <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3"><label className="text-sm"><FieldCaption>Справочник</FieldCaption><Select aria-label="Справочник" value={kind} onChange={e=>setKind(e.target.value as "systems"|"equipment-types")}><option value="systems">Инженерная система</option>{mayCreateTypes&&<option value="equipment-types">Тип оборудования</option>}</Select></label><label className="text-sm"><FieldCaption>Код справочника</FieldCaption><Input aria-label="Код справочника" required value={code} onChange={e=>setCode(e.target.value)}/></label><label className="text-sm"><FieldCaption>Название справочника</FieldCaption><Input aria-label="Название справочника" required value={name} onChange={e=>setName(e.target.value)}/></label></fieldset>
    {!catalog.systems.length&&<p className="text-sm text-amber-200">Сначала добавьте инженерную систему.</p>}{error&&<div role="alert">{error}</div>}<Button type="submit" variant="secondary" disabled={busy}>Добавить в справочник</Button>
  </form></Disclosure>;
}
