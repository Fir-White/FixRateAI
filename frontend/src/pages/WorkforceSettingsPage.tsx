import { dateTimeFormatter } from "@/shared/lib/dateTimeFormatter";
import { readQueries } from "@/shared/api/readQueries";
import { Disclosure } from "@/shared/ui/Disclosure";
import { ConnectionRequired } from "@/shared/ui/ConnectionRequired";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EmployeeCalendar } from "@/features/workforce/EmployeeCalendar";
import { managementApi } from "@/shared/api/management";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate,todayAt } from "@/shared/lib/format";
import { canManageSiteAccess, ROLE_LABELS } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import type { Role } from "@/shared/types/domain";
import type { CrewRecord,ShiftRule,StaffMember,Workforce } from "@/shared/types/management";
import { patternDefaults } from "@/shared/types/management";
import { readCalendarPattern } from "@/shared/lib/calendarPattern";
import { FormErrors, RuleSection, revealField, sectionErrors, type FieldError } from "@/features/settings/SectionForm";
import { CalendarPatternEditor } from "@/features/settings/CalendarPatternEditor";
import { Button } from "@/shared/ui/Button";
import { FieldCaption, Input,Select  } from "@/shared/ui/Form";
import { Card,CardHeader } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";
import { PageHeader } from "@/shared/ui/PageHeader";
import { LoadingState,ErrorState } from "@/shared/ui/States";
import { Icon } from "@/shared/ui/Icon";
import { Modal } from "@/shared/ui/Modal";
import "./workforce-e3.css";

type Run = (action:()=>Promise<unknown>,message:string)=>Promise<boolean>;

export function WorkforceSettingsPage() {
  return DEMO_MODE ? <ConnectionRequired title="Команда и смены" description="Роли, состав бригад, квалификации и рабочие интервалы." capabilities={["Роли и периоды работы сотрудников", "Бригады, квалификации и правила смен", "Исключения и календарь доступности"]}/> : <LiveWorkforceSettingsPage/>;
}
function LiveWorkforceSettingsPage() {
  const {profile}=useSession();const [refresh,setRefresh]=useState(0);
  const [params,setParams]=useSearchParams();
  const [search,setSearch]=useState("");
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const query=useApiQuery(readQueries.workforce.load,[refresh],undefined,readQueries.workforce.key);
  const managesAccess=canManageSiteAccess(profile?.role);
  const sections: [string,string][] = [["staff","Сотрудники"],["crews","Бригады"],["skills","Виды допусков"]];
  if (managesAccess) sections.push(["access","Регистрация и доступ"]);
  const area = sections.find(([key])=>key===params.get("view"))?.[0]??"staff";
  const selected = params.get("staff")??"";
  function navigateSection(view: string, staff?: string) {
    setParams(old => {
      const next = new URLSearchParams(old);
      if (view === "staff") next.delete("view"); else next.set("view",view);
      if (staff) next.set("staff",staff); else next.delete("staff");
      return next;
    });
  }
  const mayEdit=managesAccess||profile?.role==="engineer"||profile?.role==="dispatcher";
  const today=todayAt(profile?.timezone??"Asia/Yekaterinburg");
  const run:Run=async(action,message)=>{if(busy)return false;setBusy(true);setError("");setNotice("");try{await action();setNotice(message);setRefresh(n=>n+1);return true;}catch(failure){setError(failure instanceof Error?failure.message:"Не удалось сохранить");return false;}finally{setBusy(false);}};

  if(query.status==="loading")return <LoadingState label="Загрузка сотрудников и смен"/>;
  if(query.status==="error")return <ErrorState description={query.error}/>;
  const data=query.data;
  const member=data.staff.find(m=>m.user_id===selected);
  return <div className="space-y-6"><PageHeader title="Команда и смены" description="Сотрудники, доступы, смены и составы бригад."/>
    {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}{notice&&<Callout tone="success">{notice}</Callout>}
    <div className="fr-workspace-sections" aria-label="Раздел команды">{sections.map(([key,title])=><Button key={key} type="button" variant="secondary" aria-pressed={area===key} disabled={busy} onClick={()=>navigateSection(key,selected)}>{title}</Button>)}</div>
    <div hidden={area!=="staff"} className="space-y-5">
    {member ? <>
      <Button type="button" variant="ghost" onClick={()=>navigateSection("staff")}><Icon name="back" size={15}/>Все сотрудники</Button>
      <Employee key={`${member.user_id}:${refresh}`} person={member} data={data} managesAccess={managesAccess} mayEdit={mayEdit} today={today} busy={busy} run={run}/>
    </> : <StaffDirectory staff={data.staff} search={search} onSearch={setSearch} onSelect={id=>navigateSection("staff",id)}/>}
    </div><div hidden={area!=="crews"}><CrewSettings key={`crews:${refresh}`} data={data} today={today} mayEdit={mayEdit} busy={busy} run={run}/></div>
    <div hidden={area!=="skills"} className="space-y-4"><Card className="p-5"><h2>Виды допусков</h2>{data.skills.length ? <ul>{data.skills.map(skill=><li key={skill.id} className="border-b border-line py-3">{skill.name} · {skill.validity_required ? "Требуется срок действия" : "Без обязательного срока действия"}</li>)}</ul> : <p>Виды допусков ещё не заданы.</p>}</Card>{mayEdit&&<SkillCreate busy={busy} run={run}/>}</div>
    {area==="access"&&<Enrollment data={data} today={today} busy={busy} run={run}/>}
  </div>;
}

function StaffDirectory({staff, search, onSearch, onSelect}: {
  staff: StaffMember[]; search: string; onSearch: (search:string)=>void; onSelect: (id:string)=>void;
}) {
  const term = search.trim().toLocaleLowerCase("ru");
  const matches = staff.filter(person=>`${person.full_name} ${person.email} ${ROLE_LABELS[person.role]}`.toLocaleLowerCase("ru").includes(term));
  const [offset,setOffset] = useState(0);
  const pageStart = Math.min(offset, 25*Math.max(0,Math.ceil(matches.length/25)-1));
  return <section className="e3-staff-directory">
    <h2>Сотрудники объекта</h2>
    <label className="block max-w-md space-y-1"><FieldCaption>Поиск сотрудника</FieldCaption>
      <Input leadingIcon={<Icon name="search" size={17}/>} value={search} placeholder="Имя, почта или роль" onChange={event=>{onSearch(event.target.value);setOffset(0);}}/>
    </label>
    {matches.length>0 ? <>
      <div className="e3-staff-row e3-staff-labels" aria-hidden="true"><span>Сотрудник</span><span>Роль</span><span>Смены</span><span>Доступ</span><span/></div>
      <ul>{matches.slice(pageStart,pageStart+25).map(person => <li key={person.user_id}>
        <button type="button" className="e3-staff-row" onClick={()=>onSelect(person.user_id)} aria-label={`Открыть сотрудника: ${person.full_name}`}>
          <strong>{person.full_name}</strong><span>{ROLE_LABELS[person.role]}</span>
          <span>{person.shifts.filter(shift=>shift.is_active).length||"—"}</span>
          <span data-tone={person.is_active?"success":"muted"}>{person.is_active?"Доступ включён":"Доступ отключён"}</span>
          <Icon name="chevron" size={14}/>
        </button>
      </li>)}</ul>
      {matches.length>25&&<nav className="fr-pagination" aria-label="Страницы списка сотрудников">
        <Button variant="secondary" disabled={pageStart===0} onClick={()=>setOffset(pageStart-25)}>Предыдущая</Button>
        <span>{pageStart+1}–{Math.min(pageStart+25,matches.length)} из {matches.length}</span>
        <Button variant="secondary" disabled={pageStart+25>=matches.length} onClick={()=>setOffset(pageStart+25)}>Следующая</Button>
      </nav>}
    </> : <p className="text-muted">{term?"По этому запросу сотрудников нет.":"В объекте пока нет сотрудников."}</p>}
  </section>;
}

function Enrollment({data,today,busy,run}: {data:Workforce;today:string;busy:boolean;run:Run}) {
  const query=useApiQuery(()=>managementApi.enrollment(),[]);
  const [role,setRole]=useState<Role>("executor");
  const [rejection, setRejection]=useState<Workforce["applications"][number]>();
  return <Card className="space-y-4 p-5"><h2 className="text-lg font-semibold">Регистрация и выдача роли</h2>
    <p className="text-sm text-muted">Сотрудник регистрируется по коду компании на странице входа. До выдачи роли у него нет доступа к объекту.</p>
    {query.status==="success"&&query.data.code&&<p className="break-all rounded-lg border border-line p-3 text-sm">Код компании: <code>{query.data.code}</code></p>}
    {query.status==="success"&&!query.data.code&&<Button variant="secondary" disabled={busy} onClick={()=>run(()=>managementApi.createEnrollment(),"Код компании создан")}>Создать код регистрации</Button>}
    {query.status==="error"&&<div role="alert">{query.error}</div>}
    <h3 className="font-semibold">Ожидают доступа: {data.applications.length}</h3>
    {!!data.applications.length&&<label className="block space-y-1 text-sm"><FieldCaption>Роль нового сотрудника</FieldCaption><RoleSelect value={role} onChange={setRole}/></label>}
    {data.applications.map(person=><div key={person.application_id} className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"><p className="min-w-0 break-words">{person.full_name}<span className="block text-xs text-muted">{person.email}</span></p><div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={()=>run(()=>managementApi.decideApplication(person.application_id,person.revision,role,"accepted",today),"Доступ сотруднику выдан")}>Выдать роль</Button><Button variant="ghost" disabled={busy} onClick={()=>setRejection(person)}>Отклонить заявку</Button></div></div>)}
    <Modal open={!!rejection} title="Отклонить заявку?" onClose={()=>setRejection(undefined)}
      footer={<><Button variant="secondary" onClick={()=>setRejection(undefined)}>Отмена</Button>
        <Button variant="danger" disabled={busy} onClick={async()=>{
          if (rejection&&await run(()=>managementApi.decideApplication(rejection.application_id,rejection.revision,role,"rejected",today),"Заявка отклонена")) setRejection(undefined);
        }}>Отклонить заявку</Button></>}>
      <p className="font-semibold">{rejection?.full_name}</p>
      <p className="mt-2 text-muted">У сотрудника не будет доступа к этому объекту.</p>
    </Modal>
  </Card>;
}

function RoleSelect({value,onChange}: {value:Role;onChange:(role:Role)=>void}) {
  return <Select aria-label="Роль сотрудника" value={value} onChange={e=>onChange(e.target.value as Role)}>{(Object.keys(ROLE_LABELS) as Role[]).map(role=><option key={role} value={role}>{ROLE_LABELS[role]}</option>)}</Select>;
}

function Employee({person,data,managesAccess,mayEdit,today,busy,run}: {person:StaffMember;data:Workforce;managesAccess:boolean;mayEdit:boolean;today:string;busy:boolean;run:Run}) {
  const [role,setRole]=useState(person.role);const [active,setActive]=useState(person.is_active);
  const [from,setFrom]=useState(person.employed_from??"");const [until,setUntil]=useState(person.employed_until??"");
  const [shift,setShift]=useState<ShiftRule|null|undefined>();
  return <section aria-label="Настройки сотрудника" className="space-y-5"><Card><CardHeader title={person.full_name} description={person.email}/>
    <p className="px-5 pb-4 text-sm">{ROLE_LABELS[person.role]} · {person.is_active ? "Доступ включён" : "Доступ отключён"} · {person.employed_from ? `Работает с ${formatDate(person.employed_from)}` : "Начало работы не указано"}{person.employed_until ? ` по ${formatDate(person.employed_until)}` : ""}</p><details className="px-5" open={managesAccess||undefined}><summary className="cursor-pointer py-3">Роль и период работы{!managesAccess&&" · только просмотр"}</summary>
    <form className="space-y-4 p-5" onSubmit={e=>{e.preventDefault();if(managesAccess)run(()=>managementApi.saveStaff(person.user_id,{expected_revision:person.revision,role,is_active:active,employed_from:from||null,employed_until:until||null}),"Роль и период работы сохранены");}}><fieldset disabled={busy||!managesAccess} className="grid gap-4 sm:grid-cols-3"><label className="text-sm"><FieldCaption>Роль</FieldCaption><RoleSelect value={role} onChange={setRole}/></label><label className="text-sm"><FieldCaption>Работает с</FieldCaption><Input aria-label="Работает с" type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label className="text-sm"><FieldCaption>Работает по</FieldCaption><Input aria-label="Работает по" type="date" value={until} onChange={e=>setUntil(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Доступ к объекту включён</label></fieldset>{managesAccess&&<Button type="submit" disabled={busy}>Сохранить роль и период работы</Button>}</form>
  </details></Card>
  {person.role==="executor"&&<>
    <Card className="space-y-3 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Регулярные смены</h3>{mayEdit&&<Button variant="secondary" disabled={busy} onClick={()=>setShift(null)}>Добавить смену</Button>}</div>
      {!person.shifts.length&&<p className="text-sm text-muted">Смен нет. Для назначения нужно задать смену или отдельный рабочий интервал.</p>}
      {person.shifts.map(row=><div key={row.shift_rule_id} className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"><p>{row.label} · {row.starts_local.slice(0,5)}–{row.ends_local.slice(0,5)}<span className="block text-xs text-muted">{row.is_active ? "Действует" : "Отключена"} · с {formatDate(row.valid_from)}{row.valid_until ? ` по ${formatDate(row.valid_until)}` : ""} · {row.status==="available" ? "Рабочее время" : "Не работает"}</span></p>{mayEdit&&<Button variant="ghost" disabled={busy} onClick={()=>setShift(row)}>Изменить смену</Button>}</div>)}
    </Card>
    {shift!==undefined&&<ShiftEditor key={shift?.shift_rule_id??"new"} initial={shift} today={today} busy={busy} onClose={()=>setShift(undefined)} onSave={value=>run(()=>managementApi.saveShift(person.user_id,value),"Смена сохранена")}/>}
    <RuleSection title="Отсутствия и отдельные интервалы" summary={`Записей: ${person.exceptions.length}`}><Exceptions person={person} today={today} busy={busy} mayEdit={mayEdit} timezone={data.timezone} run={run}/></RuleSection>
    <RuleSection title="Квалификации и допуски" summary={`Записей: ${person.qualifications.length}`}><Qualifications person={person} data={data} today={today} busy={busy} mayEdit={mayEdit} run={run}/></RuleSection>
    <EmployeeCalendar person={person} today={today} timezone={data.timezone}/>
  </>}
  </section>;
}

function ShiftEditor({initial,today,busy,onSave,onClose}: {initial:ShiftRule|null;today:string;busy:boolean;onSave:(value:ShiftRule)=>Promise<boolean>;onClose:()=>void}) {
  const [storedPattern] = useState(() => initial ? readCalendarPattern(initial.pattern) : null);
  const [value,setValue]=useState<ShiftRule>(initial ? {...initial,pattern:storedPattern?.ok ? storedPattern.value : initial.pattern,expected_revision:initial.revision} : {label:"Дневная смена",pattern:patternDefaults(today),valid_from:today,valid_until:null,starts_local:"09:00",ends_local:"17:00",status:"available",is_active:true});
  const [errors,setErrors]=useState<FieldError[]>([]);
  const set=(part:Partial<ShiftRule>)=>setValue({...value,...part});
  if (storedPattern && !storedPattern.ok) return <Card className="space-y-4 p-5"><h3 className="font-semibold">{initial?.label}</h3><div role="alert"><Callout tone="danger">{storedPattern.error}</Callout></div><Button type="button" variant="ghost" onClick={onClose}>Закрыть смену</Button></Card>;
  return <Card><CardHeader title={initial ? "Изменить смену" : "Новая регулярная смена"}/><form noValidate className="space-y-4 p-5" onSubmit={async e=>{e.preventDefault();const invalid=sectionErrors(e.currentTarget);setErrors(invalid);if(invalid.length){revealField(invalid[0].field);return;}if(await onSave(value))onClose();}}><FormErrors errors={errors}/><fieldset disabled={busy} className="space-y-4"><div className="grid gap-3 sm:grid-cols-2">
    <label className="text-sm"><FieldCaption>Название смены</FieldCaption><Input aria-label="Название смены" required value={value.label} onChange={e=>set({label:e.target.value})}/></label>
    <label className="text-sm"><FieldCaption>Режим смены</FieldCaption><Select aria-label="Режим смены" value={value.status} onChange={e=>set({status:e.target.value as "available"|"unavailable"})}><option value="available">Рабочее время</option><option value="unavailable">Регулярно не работает</option></Select></label>
    <label className="text-sm"><FieldCaption>Начало смены</FieldCaption><Input aria-label="Начало смены" type="time" required value={value.starts_local} onChange={e=>set({starts_local:e.target.value})}/></label>
    <label className="text-sm"><FieldCaption>Конец смены</FieldCaption><Input aria-label="Конец смены" type="time" required value={value.ends_local} onChange={e=>set({ends_local:e.target.value})}/></label>
    <label className="text-sm"><FieldCaption>Смена действует с</FieldCaption><Input aria-label="Смена действует с" type="date" required value={value.valid_from} onChange={e=>set({valid_from:e.target.value})}/></label>
    <label className="text-sm"><FieldCaption>Смена действует по</FieldCaption><Input aria-label="Смена действует по" type="date" min={value.valid_from} value={value.valid_until??""} onChange={e=>set({valid_until:e.target.value||null})}/></label>
  </div><p className="text-xs text-muted">Конец раньше начала — окончание на следующий день. Одинаковое время начала и конца — суточная смена. Смены ограничиваются периодом работы сотрудника.</p>
  <CalendarPatternEditor value={value.pattern} context="shift" onChange={pattern=>set({pattern})}/>
  <p className="border-t border-line pt-4 text-sm">{value.status==="available" ? "Рабочее время" : "Регулярно не работает"}: {value.starts_local.slice(0,5)}–{value.ends_local.slice(0,5)} · с {formatDate(value.valid_from)}{value.valid_until ? ` по ${formatDate(value.valid_until)}` : ""}. Исключённых дат: {value.pattern.excluded_dates.length}. Это правило смены, а не подтверждённое назначение.</p>
  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.is_active} onChange={e=>set({is_active:e.target.checked})}/>Смена включена</label>
  <div className="flex gap-3"><Button type="submit" disabled={busy}>Сохранить смену</Button><Button variant="ghost" type="button" disabled={busy} onClick={onClose}>Закрыть смену</Button></div></fieldset></form></Card>;
}

function Qualifications({person,data,today,busy,mayEdit,run}: {person:StaffMember;data:Workforce;today:string;busy:boolean;mayEdit:boolean;run:Run}) {
  const [skill,setSkill]=useState(data.skills[0]?.id??"");const [verified,setVerified]=useState(today);const [until,setUntil]=useState("");
  return <Card className="space-y-3 p-5"><h3 className="font-semibold">Квалификации и допуски</h3>
    {!person.qualifications.length&&<p className="text-sm text-muted">Допуски не заданы.</p>}{person.qualifications.map(fact=><div key={fact.skill_id} className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm">{data.skills.find(s=>s.id===fact.skill_id)?.name??"Допуск"} · {fact.verified_at ? "проверен" : "не проверен"}{fact.valid_until ? ` · действует по ${formatDate(fact.valid_until)}` : ""}</p>{mayEdit&&fact.verified_at&&<Button variant="ghost" disabled={busy} onClick={()=>run(()=>managementApi.revokeQualification(person.user_id,fact.skill_id,fact.revision),"Допуск отозван")}>Отозвать допуск</Button>}</div>)}
    {mayEdit&&<form className="space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.qualification(person.user_id,skill,{verified_local:verified+"T00:00",valid_until:until||null,expected_revision:person.qualifications.find(row=>row.skill_id===skill)?.revision}),"Допуск сохранён");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3"><label className="text-sm"><FieldCaption>Допуск</FieldCaption><Select aria-label="Допуск" required value={skill} onChange={e=>setSkill(e.target.value)}>{data.skills.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</Select></label><label className="text-sm"><FieldCaption>Дата проверки допуска</FieldCaption><Input aria-label="Дата проверки допуска" type="date" required max={today} value={verified} onChange={e=>setVerified(e.target.value)}/></label><label className="text-sm"><FieldCaption>Допуск действует по</FieldCaption><Input aria-label="Допуск действует по" type="date" value={until} required={data.skills.find(s=>s.id===skill)?.validity_required} onChange={e=>setUntil(e.target.value)}/></label></fieldset><Button type="submit" variant="secondary" disabled={busy||!skill}>Сохранить допуск</Button></form>}
  </Card>;
}

function Exceptions({person,today,busy,mayEdit,timezone,run}: {person:StaffMember;today:string;busy:boolean;mayEdit:boolean;timezone:string;run:Run}) {
  const [from,setFrom]=useState(today+"T09:00");const [until,setUntil]=useState(today+"T17:00");const [reason,setReason]=useState("");const [status,setStatus]=useState<"available"|"unavailable">("unavailable");
  const stamp=(value:string)=>dateTimeFormatter("ru-RU",{timeZone:timezone,dateStyle:"short",timeStyle:"short"}).format(new Date(value));
  return <Card className="space-y-3 p-5"><h3 className="font-semibold">Отсутствия и отдельные рабочие интервалы</h3>
    {person.exceptions.map(row=><div key={row.id} className="flex flex-wrap justify-between gap-3 border-t border-line pt-3"><p className="text-sm">{stamp(row.start_at)} — {stamp(row.end_at)} · {row.status==="unavailable" ? "Не работает" : "Дополнительное рабочее время"}<span className="block text-xs text-muted">{row.reason}</span></p>{mayEdit&&<Button variant="ghost" disabled={busy} onClick={()=>run(()=>managementApi.cancelAvailability(person.user_id,row.id,row.revision),"Исключение отменено")}>Отменить исключение</Button>}</div>)}
    {mayEdit&&<form className="space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.availability(person.user_id,{start_local:from,end_local:until,status,reason}),"Интервал сохранён");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm"><FieldCaption>С начала</FieldCaption><Input aria-label="Исключение: начало" type="datetime-local" required value={from} onChange={e=>setFrom(e.target.value)}/></label><label className="text-sm"><FieldCaption>До конца</FieldCaption><Input aria-label="Исключение: конец" type="datetime-local" required value={until} onChange={e=>setUntil(e.target.value)}/></label><label className="text-sm"><FieldCaption>Вид исключения</FieldCaption><Select aria-label="Вид исключения" value={status} onChange={e=>setStatus(e.target.value as "available"|"unavailable")}><option value="unavailable">Не работает: отпуск, отгул, больничный</option><option value="available">Дополнительное рабочее время</option></Select></label><label className="text-sm"><FieldCaption>Причина исключения</FieldCaption><Input aria-label="Причина исключения" required value={reason} onChange={e=>setReason(e.target.value)}/></label></fieldset><p className="text-xs text-muted">Отсутствия имеют приоритет над рабочими сменами. Подтверждённые назначения не переносятся автоматически.</p><Button type="submit" variant="secondary" disabled={busy}>Сохранить исключение</Button></form>}
  </Card>;
}

export { EmployeeCalendar } from "@/features/workforce/EmployeeCalendar";

function CrewSettings({data,today,mayEdit,busy,run}: {data:Workforce;today:string;mayEdit:boolean;busy:boolean;run:Run}) {
  const [selected,setSelected]=useState("");const [name,setName]=useState("");const [active,setActive]=useState(true);const [members,setMembers]=useState<CrewRecord["members"]>([]);
  const choose=(id:string)=>{setSelected(id);const crew=data.crews.find(c=>c.id===id);setName(crew?.name??"");setActive(crew?.is_active??true);setMembers(crew?.members??[]);};
  return <Card className="space-y-4 p-5"><h2 className="text-lg font-semibold">Бригады</h2><p className="text-sm text-muted">Участие в бригаде не создаёт смену и не резервирует работника. Доступность каждого участника проверяется отдельно.</p>
    <label className="block text-sm"><FieldCaption>Бригада</FieldCaption><Select aria-label="Бригада" value={selected} onChange={e=>choose(e.target.value)}><option value="">Новая бригада</option>{data.crews.map(crew=><option key={crew.id} value={crew.id}>{crew.name}</option>)}</Select></label>
    <form className="space-y-4" onSubmit={e=>{e.preventDefault();run(()=>managementApi.saveCrew({name,is_active:active,members,expected_revision:data.crews.find(c=>c.id===selected)?.revision},selected||undefined),"Бригада сохранена");}}><fieldset disabled={!mayEdit||busy} className="space-y-3"><label className="block text-sm"><FieldCaption>Название бригады</FieldCaption><Input aria-label="Название бригады" required value={name} onChange={e=>setName(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Бригада действует</label>
      {data.staff.filter(person=>person.role==="executor").map(person=>{const member=members.find(m=>m.user_id===person.user_id);return <div key={person.user_id} className="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!member} onChange={e=>setMembers(e.target.checked?[...members,{user_id:person.user_id,valid_from:today,valid_to:null}]:members.filter(m=>m.user_id!==person.user_id))}/>{person.full_name}</label>{member&&<><label className="text-sm"><FieldCaption>В бригаде с</FieldCaption><Input aria-label={`В бригаде с: ${person.full_name}`} type="date" required value={member.valid_from} onChange={e=>setMembers(members.map(m=>m.user_id===person.user_id?{...m,valid_from:e.target.value}:m))}/></label><label className="text-sm"><FieldCaption>В бригаде по</FieldCaption><Input aria-label={`В бригаде по: ${person.full_name}`} type="date" value={member.valid_to??""} onChange={e=>setMembers(members.map(m=>m.user_id===person.user_id?{...m,valid_to:e.target.value||null}:m))}/></label></>}</div>;})}
      {mayEdit&&<Button type="submit" disabled={busy}>Сохранить бригаду</Button>}
    </fieldset></form>
  </Card>;
}

function SkillCreate({busy,run}: {busy:boolean;run:Run}) {
  const [code,setCode]=useState("");const [name,setName]=useState("");const [expiry,setExpiry]=useState(false);
  return <Disclosure title="Новый вид квалификации / допуска"><form className="mt-4 space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.createReference("skills",{code,name,validity_required:expiry}),"Вид допуска добавлен");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm"><FieldCaption>Код допуска</FieldCaption><Input aria-label="Код допуска" required value={code} onChange={e=>setCode(e.target.value)}/></label><label className="text-sm"><FieldCaption>Название допуска</FieldCaption><Input aria-label="Название допуска" required value={name} onChange={e=>setName(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={expiry} onChange={e=>setExpiry(e.target.checked)}/>Обязателен срок действия</label></fieldset><Button type="submit" variant="secondary" disabled={busy}>Создать вид допуска</Button></form></Disclosure>;
}
