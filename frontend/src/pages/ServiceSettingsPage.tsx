import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { managementApi } from "@/shared/api/management";
import { maintenanceApi } from "@/shared/api/maintenance";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { todayAt } from "@/shared/lib/format";
import { canOpenSection } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { patternDefaults } from "@/shared/types/management";
import type { EquipmentInput, EquipmentRecord, ManagementCatalog, ServiceConfiguration,ChecklistSetting } from "@/shared/types/management";
import { CalendarPatternEditor } from "@/features/settings/CalendarPatternEditor";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Input, Select } from "@/shared/ui/Form";
import { Card, CardHeader } from "@/shared/ui/Card";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Callout } from "@/shared/ui/Callout";
import { LoadingState, ErrorState } from "@/shared/ui/States";

export function ServiceSettingsPage() {
  const {profile}=useSession();
  const [params,setParams]=useSearchParams();
  const selected=params.get("equipment")??"";
  const [refresh,setRefresh]=useState(0);
  const [notice,setNotice]=useState("");
  const query=useApiQuery(()=>Promise.all([managementApi.catalog(),maintenanceApi.listEquipment()]),[refresh]);
  const mayEdit=profile?.role==="admin"||profile?.role==="dispatcher";
  const today=todayAt(profile?.timezone??"Asia/Yekaterinburg");
  if(DEMO_MODE) return <Callout title="Настройки требуют подключения к серверу">Откройте приложение с рабочим API.</Callout>;
  if(query.status==="loading") return <LoadingState label="Загрузка настроек обслуживания"/>;
  if(query.status==="error") return <ErrorState description={query.error}/>;
  const [catalog,equipment]=query.data;
  return <div className="space-y-6">
    <PageHeader title="Настройка обслуживания" eyebrow="Оборудование и периодичность" description="Календарь строится из этих правил. Создание заданий и назначение работников требуют отдельных действий." actions={canOpenSection(profile?.role,"calendar")&&<Link to="/calendar" className={buttonClassName("secondary")}>Открыть календарь</Link>}/>
    {notice&&<Callout tone="success">{notice}</Callout>}
    <Card className="space-y-3 p-5"><label className="block space-y-1 text-sm">Оборудование для настройки
      <Select aria-label="Оборудование для настройки" value={selected} onChange={event=>{setNotice("");setParams(event.target.value ? {equipment:event.target.value} : {});}}>
        <option value="">{mayEdit ? "Новое оборудование" : "Выберите оборудование"}</option>
        {equipment.map(item=><option key={item.id} value={item.id}>{item.inventoryCode} · {item.name}</option>)}
      </Select>
    </label><p className="text-xs text-muted">Время объекта: {profile?.timezone}. Нормативная дата относится к целым местным суткам.</p></Card>
    {mayEdit&&<ReferenceForms catalog={catalog} mayCreateTypes={profile?.role==="admin"} onSaved={()=>setRefresh(value=>value+1)}/>}
    {(selected||mayEdit)&&<EquipmentSettings key={selected} equipmentId={selected} catalog={catalog} mayEdit={mayEdit}
      onSaved={key=>{setNotice("Оборудование сохранено");setParams({equipment:key});setRefresh(value=>value+1);}}/>}
    {selected&&<ServiceList key={`${selected}:${refresh}`} equipmentId={selected} catalog={catalog} today={today} mayEdit={mayEdit}/>}
  </div>;
}

function EquipmentSettings({equipmentId,catalog,mayEdit,onSaved}: {equipmentId:string;catalog:ManagementCatalog;mayEdit:boolean;onSaved:(key:string)=>void}) {
  const query=useApiQuery(()=>equipmentId ? managementApi.getEquipment(equipmentId) : Promise.resolve(null),[equipmentId]);
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
    <label className="space-y-1 text-sm">Инвентарный номер<Input aria-label="Инвентарный номер" required value={value.asset_code} onChange={e=>set({asset_code:e.target.value})}/></label>
    <label className="space-y-1 text-sm">Название оборудования<Input aria-label="Название оборудования" required value={value.name} onChange={e=>set({name:e.target.value})}/></label>
    <label className="space-y-1 text-sm">Инженерная система<Select aria-label="Инженерная система" required value={value.system_id} onChange={e=>set({system_id:e.target.value})}>{catalog.systems.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>
    <label className="space-y-1 text-sm">Тип оборудования<Select aria-label="Тип оборудования" value={value.equipment_type_id??''} onChange={e=>set({equipment_type_id:e.target.value||null})}><option value="">Не указан</option>{catalog.equipment_types.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>
    <label className="space-y-1 text-sm">Дата ввода, если известна<Input aria-label="Дата ввода" type="date" value={value.commissioned_on??''} onChange={e=>set({commissioned_on:e.target.value||null})}/></label>
    <label className="space-y-1 text-sm">Расположение<Input aria-label="Расположение" value={value.location??""} onChange={e=>set({location:e.target.value||null})}/></label>
    <label className="space-y-1 text-sm">Серийный номер<Input aria-label="Серийный номер" value={value.serial_number??""} onChange={e=>set({serial_number:e.target.value||null})}/></label>
    <label className="space-y-1 text-sm">Состояние оборудования<Select aria-label="Состояние оборудования" value={value.status} onChange={e=>set({status:e.target.value as EquipmentInput["status"]})}><option value="active">В эксплуатации</option><option value="under_repair">В ремонте</option><option value="retired">Списано</option></Select></label>
    <label className="space-y-1 text-sm">Происхождение данных<Select aria-label="Происхождение данных" value={value.data_origin} onChange={e=>set({data_origin:e.target.value as EquipmentInput["data_origin"]})}><option value="customer">Рабочие данные</option><option value="synthetic_demo">Демонстрационные данные</option></Select></label>
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
    {services.map(item=><Card key={item.binding_id} className="space-y-2 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">{item.code} · {item.title}</h3>{mayEdit&&<Button variant="ghost" onClick={()=>{setEditing(item);setNotice("");}}>Настроить</Button>}</div><p className="text-sm text-muted">Версия {item.rule_version} · {item.enabled ? "Действует" : "Отключено"} · {item.crew_size} чел. · {item.duration_minutes??"не задано"} мин.</p><p className="text-sm">{item.source_text}</p></Card>)}
    {editing!==undefined&&<ServiceEditor key={editing?.binding_id??"new"} initial={editing} today={today} catalog={catalog} systemId={equipment.system_id} onClose={()=>setEditing(undefined)} onSave={async body=>{
      await managementApi.saveService(equipmentId,body,editing?.binding_id);setEditing(undefined);setNotice("Правило сохранено. Пересчитайте календарь, чтобы увидеть даты.");setRefresh(n=>n+1);
    }}/>}
  </section>;
}

function ServiceEditor({initial,today,catalog,systemId,onClose,onSave}: {initial:ServiceConfiguration|null;today:string;catalog:ManagementCatalog;systemId:string;onClose:()=>void;onSave:(value:ServiceConfiguration)=>Promise<void>}) {
  const [value,setValue]=useState<ServiceConfiguration>(initial ? {...initial,pattern:initial.pattern??patternDefaults(today),expected_revision:initial.revision} : {
    code:"",title:"",instructions:"",maintenance_type:"ТО2",pattern:patternDefaults(today),valid_from:today,valid_until:null,crew_size:1,norm_value:"1.000",norm_unit:"person_hour",duration_minutes:60,qualification_ids:[],checklist:[newCheck()],allowed_lead_days:0,enabled:true,
  });
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const set=(part:Partial<ServiceConfiguration>)=>setValue({...value,...part});
  return <Card><CardHeader title={initial ? "Изменить обслуживание" : "Новое обслуживание"}/><form className="space-y-4 p-5" onSubmit={async event=>{
    event.preventDefault();if(busy)return;
    if(value.pattern?.frequency==="dates"&&!value.pattern.dates.length){setError("Добавьте даты обслуживания.");return;}
    setBusy(true);setError("");try{await onSave(value);}catch(failure){setError(failure instanceof Error?failure.message:"Ошибка сохранения");}finally{setBusy(false);}
  }}><fieldset disabled={busy} className="space-y-4">
    {initial&&<Callout>Изменение создаёт новую версию с выбранной даты. Сохранённые задания и история сохраняются; конфликтующие будущие задания нужно сначала отменить.</Callout>}
    {!initial&&<label className="block space-y-1 text-sm">Использовать существующую операцию<Select aria-label="Использовать существующую операцию" value={value.operation_id??''} onChange={e=>{
      const op=catalog.operations.find(row=>row.id===e.target.value);
      set(op ? {operation_id:op.id,code:op.code,title:op.title,instructions:op.instructions,maintenance_type:op.maintenance_type} : {operation_id:undefined,code:'',title:'',instructions:''});
    }}><option value="">Новая операция</option>{catalog.operations.filter(op=>op.system_id===systemId).map(op=><option key={op.id} value={op.id}>{op.code} · {op.title}</option>)}</Select><p className="text-xs text-muted">Периодичность, норма, длительность и чек-лист этой единицы оборудования задаются ниже.</p></label>}
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="space-y-1 text-sm">Код операции<Input aria-label="Код операции" required readOnly={!!initial||!!value.operation_id} value={value.code} onChange={e=>set({code:e.target.value})}/></label>
      <label className="space-y-1 text-sm">Название обслуживания<Input aria-label="Название обслуживания" required value={value.title} onChange={e=>set({title:e.target.value})}/></label>
      <label className="space-y-1 text-sm">Вид ТО<Select aria-label="Вид ТО" value={value.maintenance_type} onChange={e=>set({maintenance_type:e.target.value as "ТО1"|"ТО2"})}><option>ТО1</option><option>ТО2</option></Select></label>
      <label className="space-y-1 text-sm">Сотрудников одновременно<Input aria-label="Сотрудников одновременно" type="number" required min={1} max={100} value={value.crew_size} onChange={e=>set({crew_size:Number(e.target.value)})}/></label>
      <label className="space-y-1 text-sm">Действует с<Input aria-label="Действует с" type="date" required value={value.valid_from} onChange={e=>set({valid_from:e.target.value})}/></label>
      <label className="space-y-1 text-sm">Действует по<Input aria-label="Действует по" type="date" value={value.valid_until??""} onChange={e=>set({valid_until:e.target.value||null})}/></label>
      <label className="space-y-1 text-sm">Исходная норма труда<Input aria-label="Исходная норма труда" type="number" min={0} step="0.001" required value={value.norm_value??""} onChange={e=>set({norm_value:e.target.value})}/></label>
      <label className="space-y-1 text-sm">Единица нормы<Select aria-label="Единица нормы" required value={value.norm_unit==="unconfirmed"?"":value.norm_unit} onChange={e=>set({norm_unit:e.target.value as "person_hour"|"elapsed_hour"})}><option value="">Выберите единицу</option><option value="person_hour">Человеко-часы, всего на работу</option><option value="elapsed_hour">Часы работы всего состава</option></Select></label>
      <label className="space-y-1 text-sm">Длительность работы, минут<Input aria-label="Длительность работы, минут" type="number" min={1} max={46080} required value={value.duration_minutes??""} onChange={e=>set({duration_minutes:Number(e.target.value)})}/></label>
      <label className="space-y-1 text-sm">Разрешено раньше срока, дней<Input aria-label="Разрешено раньше срока, дней" type="number" min={0} max={366} required value={value.allowed_lead_days} onChange={e=>set({allowed_lead_days:Number(e.target.value)})}/></label>
    </div><p className="text-xs text-muted">Норма труда и длительность задаются отдельно. Значение нормы не превращается автоматически в минуты.</p>
    <label className="block space-y-1 text-sm">Инструкция<textarea aria-label="Инструкция" required className="w-full rounded-lg border border-line bg-canvas p-3" value={value.instructions} onChange={e=>set({instructions:e.target.value})}/></label>
    <label className="block space-y-1 text-sm">Отсчёт обслуживания<Select aria-label="Отсчёт обслуживания" value={value.basis??"fixed_calendar"} onChange={e=>set({basis:e.target.value as "fixed_calendar"|"after_accepted_completion",pattern:patternDefaults(value.pattern!.anchor_date,e.target.value==="after_accepted_completion" ? "month" : "week")})}><option value="fixed_calendar">Фиксированный календарь</option><option value="after_accepted_completion">От последнего принятого выполнения</option></Select></label>
    {value.basis==="after_accepted_completion"&&<p className="text-xs text-muted">Без истории опорная дата — первый срок. После приёмки следующий срок считается от даты выполнения. Будущие выполнения не предполагаются.</p>}
    <CalendarPatternEditor value={value.pattern!} rolling={value.basis==="after_accepted_completion"} onChange={pattern=>set({pattern})}/>
    <ChecklistEditor value={value.checklist} onChange={checklist=>set({checklist})}/>
    <fieldset className="space-y-2"><legend className="text-sm">Обязательные допуски каждого работника</legend>{catalog.skills.map(skill=><label key={skill.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.qualification_ids.includes(skill.id)} onChange={e=>set({qualification_ids:e.target.checked?[...value.qualification_ids,skill.id]:value.qualification_ids.filter(id=>id!==skill.id)})}/>{skill.name}</label>)}</fieldset>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.enabled} onChange={e=>set({enabled:e.target.checked})}/>Обслуживание включено</label>
    {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}
    <div className="flex gap-3"><Button type="submit" disabled={busy}>{busy?"Сохранение…":"Сохранить обслуживание"}</Button><Button variant="ghost" type="button" disabled={busy} onClick={onClose}>Закрыть редактор</Button></div>
  </fieldset></form></Card>;
}

function newCheck():ChecklistSetting {
  return {text:'Проверить оборудование',answer_kind:'boolean',unit:null,required:true,visual_verifiability:'not_verifiable',photo_required:false};
}

function ChecklistEditor({value,onChange}:{value:ChecklistSetting[];onChange:(value:ChecklistSetting[])=>void}) {
  const edit=(index:number,part:Partial<ChecklistSetting>)=>onChange(value.map((row,i)=>i===index?{...row,...part}:row));
  return <fieldset className="space-y-3 rounded-xl border border-line p-4"><legend className="px-2 font-semibold">Чек-лист исполнения</legend>{value.map((row,index)=><div key={index} className="space-y-3 rounded-lg border border-line p-3">
    <label className="block text-sm">Пункт {index+1}<Input aria-label={`Пункт ${index+1}`} required maxLength={2000} value={row.text} onChange={e=>edit(index,{text:e.target.value})}/></label>
    <div className="grid gap-3 sm:grid-cols-3"><label className="text-sm">Вид ответа<Select aria-label={`Вид ответа ${index+1}`} value={row.answer_kind} onChange={e=>edit(index,{answer_kind:e.target.value as ChecklistSetting['answer_kind']})}><option value="boolean">Отметка выполнения</option><option value="number">Числовое показание</option><option value="text">Текст</option></Select></label>
    <label className="text-sm">Единица показания<Input aria-label={`Единица показания ${index+1}`} value={row.unit??''} onChange={e=>edit(index,{unit:e.target.value||null})}/></label>
    <label className="text-sm">Проверяемость по фото<Select aria-label={`Проверяемость по фото ${index+1}`} value={row.visual_verifiability} onChange={e=>edit(index,{visual_verifiability:e.target.value as ChecklistSetting['visual_verifiability']})}><option value="not_verifiable">По фото не подтверждается</option><option value="partial">Частично видна</option><option value="visible">Результат виден</option></Select></label></div>
    <div className="flex flex-wrap items-center gap-4 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={row.required} onChange={e=>edit(index,{required:e.target.checked})}/>Обязательный пункт</label><label className="flex items-center gap-2"><input type="checkbox" checked={row.photo_required} onChange={e=>edit(index,{photo_required:e.target.checked})}/>Требуются фото до и после</label><Button type="button" variant="ghost" disabled={value.length===1} onClick={()=>onChange(value.filter((_,i)=>i!==index))}>Убрать пункт</Button></div>
  </div>)}<Button type="button" variant="secondary" disabled={value.length>=100} onClick={()=>onChange([...value,newCheck()])}>Добавить пункт чек-листа</Button></fieldset>;
}

function ReferenceForms({catalog,mayCreateTypes,onSaved}: {catalog:ManagementCatalog;mayCreateTypes:boolean;onSaved:()=>void}) {
  const [kind,setKind]=useState<"systems"|"equipment-types">("systems");const [code,setCode]=useState("");const [name,setName]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  return <details className="rounded-xl border border-line p-4"><summary className="cursor-pointer font-semibold">Добавить систему или тип оборудования</summary><form className="mt-4 space-y-3" onSubmit={async event=>{event.preventDefault();if(busy)return;setBusy(true);setError("");try{await managementApi.createReference(kind,{code,name});onSaved();}catch(failure){setError(failure instanceof Error?failure.message:"Ошибка справочника");}finally{setBusy(false);}}}>
    <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3"><label className="text-sm">Справочник<Select aria-label="Справочник" value={kind} onChange={e=>setKind(e.target.value as "systems"|"equipment-types")}><option value="systems">Инженерная система</option>{mayCreateTypes&&<option value="equipment-types">Тип оборудования</option>}</Select></label><label className="text-sm">Код справочника<Input aria-label="Код справочника" required value={code} onChange={e=>setCode(e.target.value)}/></label><label className="text-sm">Название справочника<Input aria-label="Название справочника" required value={name} onChange={e=>setName(e.target.value)}/></label></fieldset>
    {!catalog.systems.length&&<p className="text-sm text-amber-200">Сначала добавьте инженерную систему.</p>}{error&&<div role="alert">{error}</div>}<Button type="submit" variant="secondary" disabled={busy}>Добавить в справочник</Button>
  </form></details>;
}
