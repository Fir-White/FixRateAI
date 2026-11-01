import { useState } from "react";
import { managementApi } from "@/shared/api/management";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate,todayAt } from "@/shared/lib/format";
import { ROLE_LABELS } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import type { Role } from "@/shared/types/domain";
import type { CrewRecord,ShiftRule,StaffMember,Workforce } from "@/shared/types/management";
import { patternDefaults } from "@/shared/types/management";
import { CalendarPatternEditor } from "@/features/settings/CalendarPatternEditor";
import { Button } from "@/shared/ui/Button";
import { Input,Select } from "@/shared/ui/Form";
import { Card,CardHeader } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";
import { PageHeader } from "@/shared/ui/PageHeader";
import { LoadingState,ErrorState } from "@/shared/ui/States";

type Run = (action:()=>Promise<unknown>,message:string)=>Promise<boolean>;

export function WorkforceSettingsPage() {
  const {profile}=useSession();const [refresh,setRefresh]=useState(0);const [selected,setSelected]=useState("");
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const query=useApiQuery(()=>managementApi.workforce(),[refresh]);
  const admin=profile?.role==="admin";const mayEdit=admin||profile?.role==="dispatcher";
  const today=todayAt(profile?.timezone??"Asia/Yekaterinburg");
  const run:Run=async(action,message)=>{if(busy)return false;setBusy(true);setError("");setNotice("");try{await action();setNotice(message);setRefresh(n=>n+1);return true;}catch(failure){setError(failure instanceof Error?failure.message:"Не удалось сохранить");return false;}finally{setBusy(false);}};
  if(DEMO_MODE)return <Callout title="Нужно подключение к серверу">Управление сотрудниками работает через API.</Callout>;
  if(query.status==="loading")return <LoadingState label="Загрузка сотрудников и смен"/>;
  if(query.status==="error")return <ErrorState description={query.error}/>;
  const data=query.data;
  const member=data.staff.find(m=>m.user_id===selected);
  return <div className="space-y-6"><PageHeader title="Сотрудники и смены" eyebrow="Команда" description="Роль определяет доступ. Бригада определяет состав. Смены и исключения определяют, когда человек может работать."/>
    {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}{notice&&<Callout tone="success">{notice}</Callout>}
    {admin&&<Enrollment data={data} today={today} busy={busy} run={run}/>}
    <Card className="space-y-2 p-5"><label className="block space-y-1 text-sm">Сотрудник<Select aria-label="Сотрудник" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Выберите сотрудника</option>{data.staff.map(person=><option key={person.user_id} value={person.user_id}>{person.full_name} · {ROLE_LABELS[person.role]}{person.is_active ? "" : " · доступ отключён"}</option>)}</Select></label><p className="text-xs text-muted">Часовой пояс объекта: {data.timezone}. Работа без постоянной бригады поддерживается.</p></Card>
    {member&&<Employee key={`${member.user_id}:${refresh}`} person={member} data={data} admin={admin} mayEdit={mayEdit} today={today} busy={busy} run={run}/>}
    <CrewSettings key={`crews:${refresh}`} data={data} today={today} mayEdit={mayEdit} busy={busy} run={run}/>
    {mayEdit&&<SkillCreate busy={busy} run={run}/>}
  </div>;
}

function Enrollment({data,today,busy,run}: {data:Workforce;today:string;busy:boolean;run:Run}) {
  const query=useApiQuery(()=>managementApi.enrollment(),[]);
  const [role,setRole]=useState<Role>("executor");
  return <Card className="space-y-4 p-5"><h2 className="text-lg font-semibold">Регистрация и выдача роли</h2>
    <p className="text-sm text-muted">Сотрудник регистрируется по коду компании на странице входа. До выдачи роли у него нет доступа к объекту.</p>
    {query.status==="success"&&query.data.code&&<p className="break-all rounded-lg border border-line p-3 text-sm">Код компании: <code>{query.data.code}</code></p>}
    {query.status==="success"&&!query.data.code&&<Button variant="secondary" disabled={busy} onClick={()=>run(()=>managementApi.createEnrollment(),"Код компании создан")}>Создать код регистрации</Button>}
    {query.status==="error"&&<div role="alert">{query.error}</div>}
    <h3 className="font-semibold">Ожидают доступа: {data.applications.length}</h3>
    {!!data.applications.length&&<label className="block space-y-1 text-sm">Роль нового сотрудника<RoleSelect value={role} onChange={setRole}/></label>}
    {data.applications.map(person=><div key={person.application_id} className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"><p>{person.full_name}<span className="block text-xs text-muted">{person.email}</span></p><div className="flex gap-2"><Button disabled={busy} onClick={()=>run(()=>managementApi.decideApplication(person.application_id,person.revision,role,"accepted",today),"Доступ сотруднику выдан")}>Выдать роль</Button><Button variant="ghost" disabled={busy} onClick={()=>run(()=>managementApi.decideApplication(person.application_id,person.revision,role,"rejected",today),"Заявка отклонена")}>Отклонить заявку</Button></div></div>)}
  </Card>;
}

function RoleSelect({value,onChange}: {value:Role;onChange:(role:Role)=>void}) {
  return <Select aria-label="Роль сотрудника" value={value} onChange={e=>onChange(e.target.value as Role)}>{(Object.keys(ROLE_LABELS) as Role[]).map(role=><option key={role} value={role}>{ROLE_LABELS[role]}</option>)}</Select>;
}

function Employee({person,data,admin,mayEdit,today,busy,run}: {person:StaffMember;data:Workforce;admin:boolean;mayEdit:boolean;today:string;busy:boolean;run:Run}) {
  const [role,setRole]=useState(person.role);const [active,setActive]=useState(person.is_active);
  const [from,setFrom]=useState(person.employed_from??"");const [until,setUntil]=useState(person.employed_until??"");
  const [shift,setShift]=useState<ShiftRule|null|undefined>();
  return <section aria-label="Настройки сотрудника" className="space-y-5"><Card><CardHeader title={person.full_name} description={person.email}/>
    <form className="space-y-4 p-5" onSubmit={e=>{e.preventDefault();run(()=>managementApi.saveStaff(person.user_id,{expected_revision:person.revision,role,is_active:active,employed_from:from||null,employed_until:until||null}),"Роль и период работы сохранены");}}><fieldset disabled={busy||!admin} className="grid gap-4 sm:grid-cols-3"><label className="text-sm">Роль<RoleSelect value={role} onChange={setRole}/></label><label className="text-sm">Работает с<Input aria-label="Работает с" type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label className="text-sm">Работает по<Input aria-label="Работает по" type="date" value={until} onChange={e=>setUntil(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Доступ к объекту включён</label></fieldset>{admin&&<Button type="submit" disabled={busy}>Сохранить роль и период работы</Button>}</form>
  </Card>
  {person.role==="executor"&&<>
    <Card className="space-y-3 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Регулярные смены</h3>{mayEdit&&<Button variant="secondary" disabled={busy} onClick={()=>setShift(null)}>Добавить смену</Button>}</div>
      {!person.shifts.length&&<p className="text-sm text-muted">Смен нет. Для назначения нужно задать смену или отдельный рабочий интервал.</p>}
      {person.shifts.map(row=><div key={row.shift_rule_id} className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"><p>{row.label} · {row.starts_local.slice(0,5)}–{row.ends_local.slice(0,5)}<span className="block text-xs text-muted">{row.is_active ? "Действует" : "Отключена"} · с {formatDate(row.valid_from)}{row.valid_until ? ` по ${formatDate(row.valid_until)}` : ""} · {row.status==="available" ? "Рабочее время" : "Не работает"}</span></p>{mayEdit&&<Button variant="ghost" disabled={busy} onClick={()=>setShift(row)}>Изменить смену</Button>}</div>)}
    </Card>
    {shift!==undefined&&<ShiftEditor key={shift?.shift_rule_id??"new"} initial={shift} today={today} busy={busy} onClose={()=>setShift(undefined)} onSave={value=>run(()=>managementApi.saveShift(person.user_id,value),"Смена сохранена")}/>}
    <Qualifications person={person} data={data} today={today} busy={busy} mayEdit={mayEdit} run={run}/>
    <Exceptions person={person} today={today} busy={busy} mayEdit={mayEdit} timezone={data.timezone} run={run}/>
    <EmployeeCalendar person={person} today={today} timezone={data.timezone}/>
  </>}
  </section>;
}

function ShiftEditor({initial,today,busy,onSave,onClose}: {initial:ShiftRule|null;today:string;busy:boolean;onSave:(value:ShiftRule)=>Promise<boolean>;onClose:()=>void}) {
  const [value,setValue]=useState<ShiftRule>(initial ? {...initial,expected_revision:initial.revision} : {label:"Дневная смена",pattern:patternDefaults(today),valid_from:today,valid_until:null,starts_local:"09:00",ends_local:"17:00",status:"available",is_active:true});
  const set=(part:Partial<ShiftRule>)=>setValue({...value,...part});
  return <Card><CardHeader title={initial ? "Изменить смену" : "Новая регулярная смена"}/><form className="space-y-4 p-5" onSubmit={async e=>{e.preventDefault();if(await onSave(value))onClose();}}><fieldset disabled={busy} className="space-y-4"><div className="grid gap-3 sm:grid-cols-2">
    <label className="text-sm">Название смены<Input aria-label="Название смены" required value={value.label} onChange={e=>set({label:e.target.value})}/></label>
    <label className="text-sm">Режим смены<Select aria-label="Режим смены" value={value.status} onChange={e=>set({status:e.target.value as "available"|"unavailable"})}><option value="available">Рабочее время</option><option value="unavailable">Регулярно не работает</option></Select></label>
    <label className="text-sm">Начало смены<Input aria-label="Начало смены" type="time" required value={value.starts_local} onChange={e=>set({starts_local:e.target.value})}/></label>
    <label className="text-sm">Конец смены<Input aria-label="Конец смены" type="time" required value={value.ends_local} onChange={e=>set({ends_local:e.target.value})}/></label>
    <label className="text-sm">Смена действует с<Input aria-label="Смена действует с" type="date" required value={value.valid_from} onChange={e=>set({valid_from:e.target.value})}/></label>
    <label className="text-sm">Смена действует по<Input aria-label="Смена действует по" type="date" value={value.valid_until??""} onChange={e=>set({valid_until:e.target.value||null})}/></label>
  </div><p className="text-xs text-muted">Конец раньше начала означает ночную смену до следующего дня. Смены ограничиваются периодом работы сотрудника.</p>
  <CalendarPatternEditor value={value.pattern} onChange={pattern=>set({pattern})}/>
  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.is_active} onChange={e=>set({is_active:e.target.checked})}/>Смена включена</label>
  <div className="flex gap-3"><Button type="submit" disabled={busy}>Сохранить смену</Button><Button variant="ghost" type="button" disabled={busy} onClick={onClose}>Закрыть смену</Button></div></fieldset></form></Card>;
}

function Qualifications({person,data,today,busy,mayEdit,run}: {person:StaffMember;data:Workforce;today:string;busy:boolean;mayEdit:boolean;run:Run}) {
  const [skill,setSkill]=useState(data.skills[0]?.id??"");const [verified,setVerified]=useState(today);const [until,setUntil]=useState("");
  return <Card className="space-y-3 p-5"><h3 className="font-semibold">Квалификации и допуски</h3>
    {!person.qualifications.length&&<p className="text-sm text-muted">Допуски не заданы.</p>}{person.qualifications.map(fact=><div key={fact.skill_id} className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm">{data.skills.find(s=>s.id===fact.skill_id)?.name??"Допуск"} · {fact.verified_at ? "проверен" : "не проверен"}{fact.valid_until ? ` · действует по ${formatDate(fact.valid_until)}` : ""}</p>{mayEdit&&fact.verified_at&&<Button variant="ghost" disabled={busy} onClick={()=>run(()=>managementApi.revokeQualification(person.user_id,fact.skill_id,fact.revision),"Допуск отозван")}>Отозвать допуск</Button>}</div>)}
    {mayEdit&&<form className="space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.qualification(person.user_id,skill,{verified_local:verified+"T00:00",valid_until:until||null,expected_revision:person.qualifications.find(row=>row.skill_id===skill)?.revision}),"Допуск сохранён");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3"><label className="text-sm">Допуск<Select aria-label="Допуск" required value={skill} onChange={e=>setSkill(e.target.value)}>{data.skills.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</Select></label><label className="text-sm">Дата проверки допуска<Input aria-label="Дата проверки допуска" type="date" required max={today} value={verified} onChange={e=>setVerified(e.target.value)}/></label><label className="text-sm">Допуск действует по<Input aria-label="Допуск действует по" type="date" value={until} required={data.skills.find(s=>s.id===skill)?.validity_required} onChange={e=>setUntil(e.target.value)}/></label></fieldset><Button type="submit" variant="secondary" disabled={busy||!skill}>Сохранить допуск</Button></form>}
  </Card>;
}

function Exceptions({person,today,busy,mayEdit,timezone,run}: {person:StaffMember;today:string;busy:boolean;mayEdit:boolean;timezone:string;run:Run}) {
  const [from,setFrom]=useState(today+"T09:00");const [until,setUntil]=useState(today+"T17:00");const [reason,setReason]=useState("");const [status,setStatus]=useState<"available"|"unavailable">("unavailable");
  const stamp=(value:string)=>new Intl.DateTimeFormat("ru-RU",{timeZone:timezone,dateStyle:"short",timeStyle:"short"}).format(new Date(value));
  return <Card className="space-y-3 p-5"><h3 className="font-semibold">Отсутствия и отдельные рабочие интервалы</h3>
    {person.exceptions.map(row=><div key={row.id} className="flex flex-wrap justify-between gap-3 border-t border-line pt-3"><p className="text-sm">{stamp(row.start_at)} — {stamp(row.end_at)} · {row.status==="unavailable" ? "Не работает" : "Дополнительное рабочее время"}<span className="block text-xs text-muted">{row.reason}</span></p>{mayEdit&&<Button variant="ghost" disabled={busy} onClick={()=>run(()=>managementApi.cancelAvailability(person.user_id,row.id,row.revision),"Исключение отменено")}>Отменить исключение</Button>}</div>)}
    {mayEdit&&<form className="space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.availability(person.user_id,{start_local:from,end_local:until,status,reason}),"Интервал сохранён");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm">С начала<Input aria-label="Исключение: начало" type="datetime-local" required value={from} onChange={e=>setFrom(e.target.value)}/></label><label className="text-sm">До конца<Input aria-label="Исключение: конец" type="datetime-local" required value={until} onChange={e=>setUntil(e.target.value)}/></label><label className="text-sm">Вид исключения<Select aria-label="Вид исключения" value={status} onChange={e=>setStatus(e.target.value as "available"|"unavailable")}><option value="unavailable">Не работает: отпуск, отгул, больничный</option><option value="available">Дополнительное рабочее время</option></Select></label><label className="text-sm">Причина исключения<Input aria-label="Причина исключения" required value={reason} onChange={e=>setReason(e.target.value)}/></label></fieldset><p className="text-xs text-muted">Отсутствия имеют приоритет над рабочими сменами. Подтверждённые назначения не переносятся автоматически.</p><Button type="submit" variant="secondary" disabled={busy}>Сохранить исключение</Button></form>}
  </Card>;
}

export function EmployeeCalendar({person,today,timezone}: {person:Pick<StaffMember,"user_id">;today:string;timezone:string}) {
  const [start,setStart]=useState(today);const [end,setEnd]=useState(today);const [period,setPeriod]=useState({start:today,end:today});
  const query=useApiQuery(()=>managementApi.workerCalendar(person.user_id,period.start,period.end),[person.user_id,period.start,period.end]);
  const stamp=(value:string)=>new Intl.DateTimeFormat("ru-RU",{timeZone:timezone,dateStyle:"short",timeStyle:"short"}).format(new Date(value));
  return <Card className="space-y-3 p-5"><h3 className="font-semibold">Календарь смен и исключений</h3><form className="flex flex-wrap items-end gap-3" onSubmit={e=>{e.preventDefault();setPeriod({start,end});}}><label className="text-sm">Показать с<Input aria-label="Календарь сотрудника: с" type="date" required value={start} onChange={e=>setStart(e.target.value)}/></label><label className="text-sm">Показать по<Input aria-label="Календарь сотрудника: по" type="date" min={start} required value={end} onChange={e=>setEnd(e.target.value)}/></label><Button type="submit" variant="secondary">Показать смены</Button></form>
    {query.status==="loading"&&<LoadingState label="Расчёт смен"/>}{query.status==="error"&&<ErrorState description={query.error}/>}{query.status==="success"&&<><ul className="max-h-80 space-y-2 overflow-auto">{query.data.intervals.map((row,index)=><li key={index} className="text-sm">{stamp(row.start_at)} — {stamp(row.end_at)} · {row.status==="available" ? "Смена / рабочий интервал" : "Не работает"}</li>)}</ul>{!query.data.intervals.length&&<p className="text-sm text-muted">Рабочих интервалов за период нет.</p>}{query.data.diagnostics.map((row,index)=><Callout key={index} tone="warning">{row.date}: {row.explanation}</Callout>)}</>}
  </Card>;
}

function CrewSettings({data,today,mayEdit,busy,run}: {data:Workforce;today:string;mayEdit:boolean;busy:boolean;run:Run}) {
  const [selected,setSelected]=useState("");const [name,setName]=useState("");const [active,setActive]=useState(true);const [members,setMembers]=useState<CrewRecord["members"]>([]);
  const choose=(id:string)=>{setSelected(id);const crew=data.crews.find(c=>c.id===id);setName(crew?.name??"");setActive(crew?.is_active??true);setMembers(crew?.members??[]);};
  return <Card className="space-y-4 p-5"><h2 className="text-lg font-semibold">Бригады</h2><p className="text-sm text-muted">Участие в бригаде не создаёт смену и не резервирует работника. Доступность каждого участника проверяется отдельно.</p>
    <label className="block text-sm">Бригада<Select aria-label="Бригада" value={selected} onChange={e=>choose(e.target.value)}><option value="">Новая бригада</option>{data.crews.map(crew=><option key={crew.id} value={crew.id}>{crew.name}</option>)}</Select></label>
    <form className="space-y-4" onSubmit={e=>{e.preventDefault();run(()=>managementApi.saveCrew({name,is_active:active,members,expected_revision:data.crews.find(c=>c.id===selected)?.revision},selected||undefined),"Бригада сохранена");}}><fieldset disabled={!mayEdit||busy} className="space-y-3"><label className="block text-sm">Название бригады<Input aria-label="Название бригады" required value={name} onChange={e=>setName(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Бригада действует</label>
      {data.staff.filter(person=>person.role==="executor").map(person=>{const member=members.find(m=>m.user_id===person.user_id);return <div key={person.user_id} className="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!member} onChange={e=>setMembers(e.target.checked?[...members,{user_id:person.user_id,valid_from:today,valid_to:null}]:members.filter(m=>m.user_id!==person.user_id))}/>{person.full_name}</label>{member&&<><label className="text-sm">В бригаде с<Input aria-label={`В бригаде с: ${person.full_name}`} type="date" required value={member.valid_from} onChange={e=>setMembers(members.map(m=>m.user_id===person.user_id?{...m,valid_from:e.target.value}:m))}/></label><label className="text-sm">В бригаде по<Input aria-label={`В бригаде по: ${person.full_name}`} type="date" value={member.valid_to??""} onChange={e=>setMembers(members.map(m=>m.user_id===person.user_id?{...m,valid_to:e.target.value||null}:m))}/></label></>}</div>;})}
      {mayEdit&&<Button type="submit" disabled={busy}>Сохранить бригаду</Button>}
    </fieldset></form>
  </Card>;
}

function SkillCreate({busy,run}: {busy:boolean;run:Run}) {
  const [code,setCode]=useState("");const [name,setName]=useState("");const [expiry,setExpiry]=useState(false);
  return <details className="rounded-xl border border-line p-4"><summary className="cursor-pointer font-semibold">Новый вид квалификации / допуска</summary><form className="mt-4 space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.createReference("skills",{code,name,validity_required:expiry}),"Вид допуска добавлен");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm">Код допуска<Input aria-label="Код допуска" required value={code} onChange={e=>setCode(e.target.value)}/></label><label className="text-sm">Название допуска<Input aria-label="Название допуска" required value={name} onChange={e=>setName(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={expiry} onChange={e=>setExpiry(e.target.checked)}/>Обязателен срок действия</label></fieldset><Button type="submit" variant="secondary" disabled={busy}>Создать вид допуска</Button></form></details>;
}
