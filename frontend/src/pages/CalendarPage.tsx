import { ScheduleMatrix,PlanApproval } from "@/features/analyst/AnalystPanels";
import { canOperate } from "@/shared/lib/roles";
import {useEffect,useState} from "react";
import {Link,useSearchParams} from "react-router-dom";
import {maintenanceApi} from "@/shared/api/maintenance";
import {DEMO_MODE} from "@/shared/api/request";
import {useSession} from "@/shared/session/SessionContext";
import {useApiQuery} from "@/shared/lib/useApiQuery";
import {useWorkspaceState} from "@/shared/lib/workspaceState";
import {useMediaQuery} from "@/shared/lib/useMediaQuery";
import {DEMO_DATE,dateLabel,isDateKey,shiftDay,weekFor} from "@/shared/lib/operations";
import {formatDate,formatMonth,todayAt} from "@/shared/lib/format";
import {taskPathForRole} from "@/shared/lib/roles";
import {PageHeader} from "@/shared/ui/PageHeader";
import {Card} from "@/shared/ui/Card";
import {Button,IconButton,buttonClassName} from "@/shared/ui/Button";
import {Select} from "@/shared/ui/Form";
import {Icon} from "@/shared/ui/Icon";
import {Callout} from "@/shared/ui/Callout";
import {Drawer} from "@/shared/ui/Drawer";
import {ErrorState,LoadingState} from "@/shared/ui/States";
import {PlanningRunPanel} from "@/features/planning/PlanningRunPanel";
import {CalendarBoard,OCCURRENCE_LABELS,type CalendarView} from "@/features/calendar/CalendarBoard";
import type {CalendarOccurrence,CalendarPreview,CalendarPreviewOccurrence} from "@/shared/types/domain";
import "@/features/calendar/calendar.css";
import "@/features/calendar/calendar-v2.css";

export function CalendarPage() {
 const {profile}=useSession();const [params]=useSearchParams();
 const timezone=profile?.timezone??"Asia/Yekaterinburg",today=DEMO_MODE?DEMO_DATE:todayAt(timezone);
 const supplied=params.get("date");const initial=isDateKey(supplied)?supplied:today;
 const [anchor,setAnchor]=useWorkspaceState("calendar.anchor",initial,isDateKey);
 const [view,setView]=useWorkspaceState<CalendarView>("calendar.view","month",(v):v is CalendarView=>["month","week","agenda"].includes(String(v)));
 const [workspaceView,setWorkspaceView]=useState<"calendar"|"matrix">("calendar");
 const compact=useMediaQuery("(max-width: 767px)");const actualView=compact?"agenda":view;
 const weekPeriod=workspaceView==="calendar"&&(compact||actualView==="week");
 useEffect(()=>{if(isDateKey(supplied))setAnchor(supplied);},[supplied]);
 const [mode,setMode]=useState<"saved"|"preview">("saved"),[calculation,setCalculation]=useState(0);
 const [equipment,setEquipment]=useState(""),[selectedId,setSelectedId]=useState<string|null>(null);
 const year=+anchor.slice(0,4),month=+anchor.slice(5,7), mayPreview=canOperate(profile?.role);
 const scope=`${anchor}:${actualView}:${compact}:${workspaceView}:${mode}:${calculation}`;
 const query=useApiQuery(async()=>{
  if(mode==="preview"){const preview=await maintenanceApi.previewCalendar(year,month);return {scope,preview,items:preview.items as CalendarOccurrence[]};}
  const months=weekPeriod?[...new Set(weekFor(anchor).map(day=>day.slice(0,7)))]:[anchor.slice(0,7)];
  const lists=await Promise.all(months.map(value=>maintenanceApi.listCalendar(+value.slice(0,4),+value.slice(5,7))));
  return {scope,preview:null,items:[...new Map(lists.flat().map(item=>[item.id,item])).values()]};
 },[scope]);
 const tasksQuery=useApiQuery(()=>maintenanceApi.listTasks(),[]);
 const data=query.status==="success"&&query.data.scope===scope?query.data:null;
 const visibleWeek = weekFor(anchor);
 const items=(data?.items??[]).filter(item=>(!equipment||item.equipmentId===equipment) && (!isDateKey(item.occurrenceDate) || (compact ? item.occurrenceDate===anchor : !weekPeriod || visibleWeek.includes(item.occurrenceDate))));
 const options=[...new Map((data?.items??[]).filter(item=>item.equipmentId).map(item=>[item.equipmentId!,item.equipmentName])).entries()];
 const selected=items.find(item=>item.id===selectedId);
 const selectedTask=tasksQuery.status==="success"?tasksQuery.data.find(task=>task.id===selected?.taskId):undefined;
 const previewSelected=selected&&"mandatoryDueDate" in selected?selected as CalendarPreviewOccurrence:null;
 const deadline=previewSelected?.mandatoryDueDate??selectedTask?.mandatoryDueDate;
 const taskPath=selected?.taskId?taskPathForRole(profile?.role,selected.taskId):null;
 const pending=query.status==="loading"||(query.status==="success"&&!data);
 const shift=(delta:number)=>{setSelectedId(null);if(weekPeriod){const next=shiftDay(anchor,delta*7);if(isDateKey(next))setAnchor(next);}else{const date=new Date(Date.UTC(year,month-1+delta,1));const next=date.toISOString().slice(0,10);if(isDateKey(next))setAnchor(next);}};
 const stats={overdue:items.filter(item=>item.isOverdue || ("deadlinePassed" in item && item.deadlinePassed)).length,fulfilled:items.filter(item=>item.status==="fulfilled").length,unknown:data?.preview?data.preview.diagnostics.filter(item=>item.status==="needs_input"||item.status==="manual_review").length:items.filter(item=>item.requiresInput).length};
 return <div className="space-y-6 fr-calendar-page"><PageHeader title="График ТО и ППР" description="Регламент задаёт границы. План помогает организовать исполнение." actions={mayPreview?<Button disabled={pending||DEMO_MODE||year>2100} title={DEMO_MODE?"В DEMO расчёт недоступен: нужен API":undefined} onClick={()=>{setWorkspaceView("calendar");setMode("preview");setCalculation(v=>v+1);setSelectedId(null);}}><Icon name="calendar" size={16}/>{mode==="preview"?"Пересчитать график":"Рассчитать график"}</Button>:undefined}/>
 {!DEMO_MODE&&<div className="fr-segmented" aria-label="Рабочее представление"><button type="button" aria-pressed={workspaceView==="calendar"} onClick={()=>setWorkspaceView("calendar")}>Календарь</button><button type="button" aria-pressed={workspaceView==="matrix"} onClick={()=>{setWorkspaceView("matrix");setMode("saved");setSelectedId(null);}}>Матрица обязательств</button></div>}
 {mode==="preview"&&<Callout tone="warning"><strong>Предварительный расчёт · не сохранён</strong><p>Результаты ниже относятся к расчёту. График не сохранён, сотрудники не назначены.</p><Button variant="secondary" onClick={()=>setMode("saved")}>Сохранённый график</Button></Callout>}
 {data?.preview&&canOperate(profile?.role)&&!DEMO_MODE&&<PlanningRunPanel key={`${scope}:${data.preview.generationToken}`} preview={data.preview} onRecalculate={()=>setCalculation(v=>v+1)}/>}
 <div className="fr-calendar-toolbar"><div className="fr-calendar-period"><IconButton label={weekPeriod?"Предыдущая неделя":"Предыдущий месяц"} onClick={()=>shift(-1)} disabled={year<=2000&&month===1}><Icon name="back" size={16}/></IconButton><h2>{weekPeriod?`${dateLabel(weekFor(anchor)[0],{day:"numeric",month:"short"})} — ${dateLabel(weekFor(anchor)[6],{day:"numeric",month:"short"})}`:formatMonth(year,month)}</h2><IconButton label={weekPeriod?"Следующая неделя":"Следующий месяц"} onClick={()=>shift(1)} disabled={year>=(mode==="preview"?2100:2200)&&month===12}><Icon name="chevron" size={16}/></IconButton><button className="fr-text-button" type="button" onClick={()=>{setAnchor(today);setSelectedId(null);}}>{DEMO_MODE?"Дата демо":"Сегодня"}</button></div>
 {!compact&&workspaceView==="calendar"&&<div className="fr-segmented" aria-label="Вид календаря">{([['month','Месяц'],['week','Неделя'],['agenda','Список']] as const).map(([value,label])=><button key={value} type="button" aria-pressed={view===value} onClick={()=>{setView(value);setSelectedId(null);}}>{label}</button>)}</div>}</div>
 {compact&&workspaceView==="calendar"&&<div className="fr-week-picker fr-calendar-mobile-days" aria-label="День календаря">{visibleWeek.map(day=><button type="button" key={day} aria-pressed={day===anchor} aria-label={dateLabel(day,{day:"numeric",month:"long"})} className={day===anchor?"is-selected":""} onClick={()=>{setAnchor(day);setSelectedId(null);}}><span>{dateLabel(day,{weekday:"short"})}</span><strong>{day.slice(8)}</strong></button>)}</div>}
 {workspaceView==="calendar"&&<><Card className="fr-calendar-surface"><div className="fr-calendar-filterline"><Select aria-label="Оборудование календаря" value={equipment} onChange={e=>setEquipment(e.target.value)}><option value="">Всё оборудование</option>{options.map(([id,name])=><option key={id} value={id}>{name}</option>)}</Select><div className="fr-calendar-counters"><span><strong>{items.length}</strong> работ</span><span><i className="is-fulfilled"/>{stats.fulfilled} выполнено</span><span className={stats.overdue?"fr-danger":""}><i className="is-overdue"/>{stats.overdue} просрочено</span>{stats.unknown>0&&<span className="fr-warning">{stats.unknown} требуют уточнения</span>}</div></div>
 {pending&&<LoadingState label={mode==="preview"?"Расчёт графика":"Загрузка календаря"}/>} {query.status==="error"&&<ErrorState description={query.error}/>}
 {data&&<CalendarBoard items={items} year={year} month={month} anchor={anchor} today={today} view={actualView} onSelect={item=>setSelectedId(item.id)}/>}
 <div className="fr-calendar-legend"><span><i className="is-planned"/>Запланировано</span><span><i className="is-fulfilled"/>Выполнено</span><span><i className="is-overdue"/>Просрочено</span><span>Часовой пояс · {timezone}</span></div></Card>
 <div className="fr-calendar-disclaimer"><Icon name="quality" size={18}/><p>{mode==="preview"?"Даты расчёта в прошлом требуют проверки.":"Календарная дата — не замена обязательному сроку наряда. Нажмите на работу, чтобы увидеть нормативную границу и детали."}{DEMO_MODE&&" DEMO: сохранённый пример октября 2026 года, расчёт через сервер недоступен."}</p></div></>}
 {!DEMO_MODE&&workspaceView==="matrix"&&<ScheduleMatrix year={year} month={month}/>}
 {!DEMO_MODE&&mode==="saved"&&<PlanApproval year={year} month={month} onSaved={()=>setCalculation(v=>v+1)}/>}
 {data?.preview&&<PreviewDiagnostics preview={data.preview}/>}
 <Drawer open={!!selected} onClose={()=>setSelectedId(null)} title={selected?.operationTitle??"Работа"} footer={<>{taskPath&&<Link to={taskPath} className={buttonClassName("primary")}>Открыть наряд <Icon name="chevron" size={16}/></Link>}{selected?.equipmentId&&<Link to={`/equipment/${selected.equipmentId}`} className={buttonClassName("secondary")}>Оборудование</Link>}</>}>
 {selected&&<><p className="fr-drawer-equipment">{selected.equipmentName}</p><span className={`fr-calendar-status ${selected.isOverdue?"fr-danger":""}`}>{selected.isOverdue?"Просрочено · ":""}{OCCURRENCE_LABELS[selected.status]}</span><dl className="fr-detail-dates"><div><dt>Исходная дата обязательства</dt><dd>{formatDate(selected.sourceDate??selected.occurrenceDate)}</dd></div><div><dt>Календарная дата выполнения</dt><dd>{isDateKey(selected.occurrenceDate)?formatDate(selected.occurrenceDate):"Требует уточнения"}</dd></div><div className="is-mandatory"><dt>Обязательный срок</dt><dd>{deadline?formatDate(deadline):tasksQuery.status==="error"?"Не удалось загрузить срок наряда":tasksQuery.status==="loading"?"Загрузка срока…":"Не передан в данных"}</dd></div><div><dt>Операция / вид ТО</dt><dd>{selected.operationCode} · {selected.maintenanceType??"Не указан"}</dd></div><div><dt>Наряд</dt><dd>{selectedTask?.code??(selected.taskId?"Связанный наряд":"Не создан")}</dd></div></dl>
 {selected.requiresInput&&<Callout tone="warning">Исходные данные требуют уточнения. Работа не считается подтверждённой только по наличию даты.</Callout>}
 {previewSelected&&<><p className="fr-detail-explanation">{previewSelected.explanation}</p><dl className="fr-detail-dates"><div><dt>Бригада</dt><dd>{previewSelected.crewSize} чел.</dd></div><div><dt>Длительность</dt><dd>{previewSelected.planningDurationMinutes===null?"Требует уточнения":`${previewSelected.planningDurationMinutes} мин.`}</dd></div><div><dt>Норма</dt><dd>{previewSelected.rawNormValue??"Не задана"} · {previewSelected.normUnit==="person_hour"?"чел.-ч":previewSelected.normUnit==="elapsed_hour"?"часы бригады":"Единица не подтверждена"}</dd></div></dl></>}
 <p className="fr-detail-explanation">AI-рекомендация не может перенести обязательный срок на более позднюю дату.</p></>}
 </Drawer></div>;
}
function PreviewDiagnostics({preview}: {preview: CalendarPreview}) {
  const labels = {ok: "Рассчитано", needs_input: "Нужны данные", manual_review: "Ручная проверка", skipped: "Не действует"};
  return <Card className="overflow-hidden">
    <div className="border-b border-line p-5">
      <h2 className="font-semibold text-ink">Результат по оборудованию и операциям</h2>
      <p className="mt-1 text-sm text-muted">{preview.timezone} · Для каждой привязки показаны даты, нагрузка или причина отсутствия расчёта.</p>
    </div>
    {preview.diagnostics.length === 0 ? <p className="p-5 text-sm text-muted">Нет привязанных операций для расчёта.</p> : <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="bg-white/[0.03] text-muted"><tr>
          <th className="p-4">Оборудование / операция</th><th className="p-4">Результат</th>
          <th className="p-4">Нагрузка за месяц</th><th className="p-4">Пояснение</th>
        </tr></thead>
        <tbody>{preview.diagnostics.map(item => <tr key={item.bindingId} className="border-t border-line align-top">
          <td className="p-4"><p>{item.equipmentName}</p><p>{item.operationCode} {item.operationTitle}</p>
            </td>
          <td className="p-4"><p>{labels[item.status]}</p><p className="text-xs text-muted">Дат: {item.occurrencesCount}</p></td>
          <td className="p-4"><p>{item.totalPersonHours === null ? "Человеко-часы требуют уточнения" : `${item.totalPersonHours} чел.-ч`}</p>
            <p className="text-xs text-muted">{item.totalPlanningPersonMinutes === null ? "Длительность требует уточнения" : `${item.totalPlanningPersonMinutes} чел.-мин.`}</p></td>
          <td className="min-w-64 p-4"><p>{item.explanation}</p>
            {item.warnings.includes("EQUIPMENT_OUT_OF_SERVICE") && <p className="mt-1 text-amber-200">Оборудование недоступно для работы; возможность исполнения нужно проверить отдельно.</p>}
            {item.warnings.includes("HISTORY_AFTER_CUTOFF_IGNORED") && <p className="mt-1 text-xs text-muted">Более поздние приёмки не использованы в расчёте.</p>}
            {item.nextDueDate && <p className="mt-1 text-xs">Следующий обязательный срок: {formatDate(item.nextDueDate)}</p>}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </Card>;
}
