import { ConnectionRequired } from "@/shared/ui/ConnectionRequired";
import { useRef, useState } from "react";
import { useScrollBoundary } from "@/shared/lib/useScrollBoundary";
import { isShortString, useWorkspaceState } from "@/shared/lib/workspaceState";
import { managementApi } from "@/shared/api/management";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate,todayAt } from "@/shared/lib/format";
import { ROLE_LABELS } from "@/shared/lib/roles";
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

type Run = (action:()=>Promise<unknown>,message:string)=>Promise<boolean>;

export function WorkforceSettingsPage() {
  return DEMO_MODE ? <ConnectionRequired title="Сотрудники и смены" description="Роли, состав бригад, квалификации и рабочие интервалы." capabilities={["Роли и периоды работы сотрудников", "Бригады, квалификации и правила смен", "Исключения и календарь доступности"]}/> : <LiveWorkforceSettingsPage/>;
}
function LiveWorkforceSettingsPage() {
  const {profile}=useSession();const [refresh,setRefresh]=useState(0);const [selected,setSelected]=useWorkspaceState("workforce.employee", "", isShortString);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const [area,setArea]=useState<"staff"|"crews"|"skills">("staff");
  const query=useApiQuery(()=>managementApi.workforce(),[refresh]);
  const admin=profile?.role==="admin";const mayEdit=admin||["chief_engineer","engineer","dispatcher"].includes(profile?.role??"");
  const today=todayAt(profile?.timezone??"Asia/Yekaterinburg");
  const run:Run=async(action,message)=>{if(busy)return false;setBusy(true);setError("");setNotice("");try{await action();setNotice(message);setRefresh(n=>n+1);return true;}catch(failure){setError(failure instanceof Error?failure.message:"Не удалось сохранить");return false;}finally{setBusy(false);}};

  if(query.status==="loading")return <LoadingState label="Загрузка сотрудников и смен"/>;
  if(query.status==="error")return <ErrorState description={query.error}/>;
  const data=query.data;
  const member=data.staff.find(m=>m.user_id===selected);
  return <div className="space-y-6"><PageHeader title="Сотрудники и смены" eyebrow="Команда" description="Роль определяет доступ. Бригада определяет состав. Смены и исключения определяют, когда человек может работать."/>
    {error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}{notice&&<Callout tone="success">{notice}</Callout>}
    <div className="fr-workspace-sections" aria-label="Раздел команды">{([["staff","Сотрудники"],["crews","Бригады"],["skills","Виды допусков"]] as const).map(([key,title])=><Button key={key} type="button" variant="secondary" aria-pressed={area===key} disabled={busy} onClick={()=>setArea(key)}>{title}</Button>)}</div>
    <div hidden={area!=="staff"} className="space-y-5">
    {admin&&<Enrollment data={data} today={today} busy={busy} run={run}/>}
    <Card className="space-y-2 p-5"><label className="block space-y-1 text-sm"><FieldCaption>Сотрудник</FieldCaption><Select aria-label="Сотрудник" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Выберите сотрудника</option>{data.staff.map(person=><option key={person.user_id} value={person.user_id}>{person.full_name} · {ROLE_LABELS[person.role]}{person.is_active ? "" : " · доступ отключён"}</option>)}</Select></label><p className="text-xs text-muted">Часовой пояс объекта: {data.timezone}. Работа без постоянной бригады поддерживается.</p></Card>
    {member&&<Employee key={`${member.user_id}:${refresh}`} person={member} data={data} admin={admin} mayEdit={mayEdit} today={today} busy={busy} run={run}/>}
    </div><div hidden={area!=="crews"}><CrewSettings key={`crews:${refresh}`} data={data} today={today} mayEdit={mayEdit} busy={busy} run={run}/></div>
    <div hidden={area!=="skills"} className="space-y-4"><Card className="p-5"><h2>Виды допусков</h2>{data.skills.length ? <ul>{data.skills.map(skill=><li key={skill.id} className="border-b border-line py-3">{skill.name} · {skill.validity_required ? "Требуется срок действия" : "Без обязательного срока действия"}</li>)}</ul> : <p>Виды допусков ещё не заданы.</p>}</Card>{mayEdit&&<SkillCreate busy={busy} run={run}/>}</div>
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
    {!!data.applications.length&&<label className="block space-y-1 text-sm"><FieldCaption>Роль нового сотрудника</FieldCaption><RoleSelect value={role} onChange={setRole}/></label>}
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
    <p className="px-5 pb-4 text-sm">{ROLE_LABELS[person.role]} · {person.is_active ? "Доступ включён" : "Доступ отключён"} · {person.employed_from ? `Работает с ${formatDate(person.employed_from)}` : "Начало работы не указано"}{person.employed_until ? ` по ${formatDate(person.employed_until)}` : ""}</p><details className="px-5" open={admin||undefined}><summary className="cursor-pointer py-3">Роль и период работы{!admin&&" · только просмотр"}</summary>
    <form className="space-y-4 p-5" onSubmit={e=>{e.preventDefault();run(()=>managementApi.saveStaff(person.user_id,{expected_revision:person.revision,role,is_active:active,employed_from:from||null,employed_until:until||null}),"Роль и период работы сохранены");}}><fieldset disabled={busy||!admin} className="grid gap-4 sm:grid-cols-3"><label className="text-sm"><FieldCaption>Роль</FieldCaption><RoleSelect value={role} onChange={setRole}/></label><label className="text-sm"><FieldCaption>Работает с</FieldCaption><Input aria-label="Работает с" type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label className="text-sm"><FieldCaption>Работает по</FieldCaption><Input aria-label="Работает по" type="date" value={until} onChange={e=>setUntil(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Доступ к объекту включён</label></fieldset>{admin&&<Button type="submit" disabled={busy}>Сохранить роль и период работы</Button>}</form>
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
  </div><p className="text-xs text-muted">Конец раньше начала означает ночную смену до следующего дня. Смены ограничиваются периодом работы сотрудника.</p>
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
  const stamp=(value:string)=>new Intl.DateTimeFormat("ru-RU",{timeZone:timezone,dateStyle:"short",timeStyle:"short"}).format(new Date(value));
  return <Card className="space-y-3 p-5"><h3 className="font-semibold">Отсутствия и отдельные рабочие интервалы</h3>
    {person.exceptions.map(row=><div key={row.id} className="flex flex-wrap justify-between gap-3 border-t border-line pt-3"><p className="text-sm">{stamp(row.start_at)} — {stamp(row.end_at)} · {row.status==="unavailable" ? "Не работает" : "Дополнительное рабочее время"}<span className="block text-xs text-muted">{row.reason}</span></p>{mayEdit&&<Button variant="ghost" disabled={busy} onClick={()=>run(()=>managementApi.cancelAvailability(person.user_id,row.id,row.revision),"Исключение отменено")}>Отменить исключение</Button>}</div>)}
    {mayEdit&&<form className="space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.availability(person.user_id,{start_local:from,end_local:until,status,reason}),"Интервал сохранён");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm"><FieldCaption>С начала</FieldCaption><Input aria-label="Исключение: начало" type="datetime-local" required value={from} onChange={e=>setFrom(e.target.value)}/></label><label className="text-sm"><FieldCaption>До конца</FieldCaption><Input aria-label="Исключение: конец" type="datetime-local" required value={until} onChange={e=>setUntil(e.target.value)}/></label><label className="text-sm"><FieldCaption>Вид исключения</FieldCaption><Select aria-label="Вид исключения" value={status} onChange={e=>setStatus(e.target.value as "available"|"unavailable")}><option value="unavailable">Не работает: отпуск, отгул, больничный</option><option value="available">Дополнительное рабочее время</option></Select></label><label className="text-sm"><FieldCaption>Причина исключения</FieldCaption><Input aria-label="Причина исключения" required value={reason} onChange={e=>setReason(e.target.value)}/></label></fieldset><p className="text-xs text-muted">Отсутствия имеют приоритет над рабочими сменами. Подтверждённые назначения не переносятся автоматически.</p><Button type="submit" variant="secondary" disabled={busy}>Сохранить исключение</Button></form>}
  </Card>;
}

export function EmployeeCalendar({person,today,timezone}: {person:Pick<StaffMember,"user_id">;today:string;timezone:string}) {
  const [period,setPeriod]=useWorkspaceState(`employee-calendar:${person.user_id}.period`, {start:today,end:today}, (value): value is {start:string;end:string} => {
    if (!value || typeof value !== "object") return false;
    const period = value as {start:string;end:string};
    const date = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
    return date(period.start) && date(period.end) && period.start <= period.end;
  });
  const [start,setStart]=useState(period.start);const [end,setEnd]=useState(period.end);
  const query=useApiQuery(()=>managementApi.workerCalendar(person.user_id,period.start,period.end),[person.user_id,period.start,period.end]);
  const scrollRef = useRef<HTMLUListElement>(null);
  useScrollBoundary(scrollRef, query.status === "success");
  const stamp=(value:string)=>new Intl.DateTimeFormat("ru-RU",{timeZone:timezone,dateStyle:"short",timeStyle:"short"}).format(new Date(value));
  return <Card className="space-y-3 p-5"><h3 className="font-semibold">Календарь смен и исключений</h3><form className="flex flex-wrap items-end gap-3" onSubmit={e=>{e.preventDefault();setPeriod({start,end});}}><label className="text-sm"><FieldCaption>Показать с</FieldCaption><Input aria-label="Календарь сотрудника: с" type="date" required value={start} onChange={e=>setStart(e.target.value)}/></label><label className="text-sm"><FieldCaption>Показать по</FieldCaption><Input aria-label="Календарь сотрудника: по" type="date" min={start} required value={end} onChange={e=>setEnd(e.target.value)}/></label><Button type="submit" variant="secondary">Показать смены</Button></form>
    {query.status==="loading"&&<LoadingState label="Расчёт смен"/>}{query.status==="error"&&<ErrorState description={query.error}/>}{query.status==="success"&&<><ul data-scroll-key={`employee-calendar:${person.user_id}`} ref={scrollRef} className="scroll-boundary max-h-80 space-y-2 overflow-auto">{query.data.intervals.map((row,index)=><li key={index} className="text-sm">{stamp(row.start_at)} — {stamp(row.end_at)} · {row.status==="available" ? "Смена / рабочий интервал" : "Не работает"}</li>)}</ul>{!query.data.intervals.length&&<p className="text-sm text-muted">Рабочих интервалов за период нет.</p>}{query.data.diagnostics.map((row,index)=><Callout key={index} tone="warning">{row.date}: {row.explanation}</Callout>)}</>}
  </Card>;
}

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
  return <details className="rounded-xl border border-line p-4"><summary className="cursor-pointer font-semibold">Новый вид квалификации / допуска</summary><form className="mt-4 space-y-3" onSubmit={e=>{e.preventDefault();run(()=>managementApi.createReference("skills",{code,name,validity_required:expiry}),"Вид допуска добавлен");}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm"><FieldCaption>Код допуска</FieldCaption><Input aria-label="Код допуска" required value={code} onChange={e=>setCode(e.target.value)}/></label><label className="text-sm"><FieldCaption>Название допуска</FieldCaption><Input aria-label="Название допуска" required value={name} onChange={e=>setName(e.target.value)}/></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={expiry} onChange={e=>setExpiry(e.target.checked)}/>Обязателен срок действия</label></fieldset><Button type="submit" variant="secondary" disabled={busy}>Создать вид допуска</Button></form></details>;
}
