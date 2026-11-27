import { useState } from "react";
import { readQueries } from "@/shared/api/readQueries";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { todayAt, pluralize } from "@/shared/lib/format";
import { canOpenSection, hasPermission } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { DEMO_DATE, isOpenTask, isTaskOverdue, isUnassigned, taskWorkDate } from "@/shared/lib/operations";
import { DailyActions } from '@/features/navigation/DailyActions';
import { WorkdayHeading, WorkdayUpcoming } from '@/features/navigation/Workday';
import { ChiefWorkdayTimeline } from '@/features/navigation/ChiefWorkdayTimeline';
import { WorkdayAssistant } from '@/features/assistant/WorkdayAssistant';

export function DispatcherPage() {
  const {profile}=useSession();
  const timezone=profile?.timezone??"Asia/Yekaterinburg";
  const today=DEMO_MODE?DEMO_DATE:todayAt(timezone);
  const admin=profile?.role==="admin";
  const chief=hasPermission(profile,"engineering_workspace");
  const [taskAttempt, setTaskAttempt] = useState(0);
  const canTasks=canOpenSection(profile?.role,"tasks"), canCalendar=canOpenSection(profile?.role,"calendar");
  const query=useApiQuery(readQueries.tasks.load,[taskAttempt],undefined,readQueries.tasks.key);
  const workforce=useApiQuery(()=>admin&&!DEMO_MODE?readQueries.workforce.load():Promise.resolve(null),[admin],undefined,admin&&!DEMO_MODE?readQueries.workforce.key:undefined);
  if(!chief && query.status==="loading")return <LoadingState label="Загрузка оперативного центра"/>;
  if(!chief && query.status==="error")return <ErrorState description={query.error}/>;
  const tasks=query.data??[], open=tasks.filter(isOpenTask);
  const overdue=tasks.filter(isTaskOverdue).length, unassigned=tasks.filter(isUnassigned).length;
  const director=profile?.role==="director";
  const title=director?"Обзор объекта":chief?"С чего начнём рабочий день?":admin?"Рабочее пространство":profile?.role==="engineer"?"Рабочий день инженера":"Рабочий день диспетчера";
  const signals=admin ? (workforce.data?.applications ? [{value:workforce.data.applications.length,label:"Заявки на доступ",to:"/settings/workforce?view=access"}]:[]) : [
    {value:open.length,label:pluralize(open.length,"незавершённая работа","незавершённые работы","незавершённых работ"),to:canTasks?"/tasks?status=open":undefined},
    {value:overdue,label:"Просрочено",to:canTasks?"/tasks?status=overdue":undefined,tone:"danger" as const},
    director
      ? {value:tasks.filter(t=>t.state==="accepted").length,label:"Принято",to:"/tasks?status=accepted"}
      : {value:unassigned,label:"Без исполнителя",to:canTasks?"/tasks?status=unassigned":undefined,tone:"warning" as const},
  ];
  const upcoming=chief ? [] : open.map(task=>({task, date:taskWorkDate(task,timezone)??""}))
    .filter(({date})=>date>=today)
    .sort((a,b)=>a.date.localeCompare(b.date)||(a.task.scheduledStart??"z").localeCompare(b.task.scheduledStart??"z"))
    .map(({task})=>task);
  return <div className={chief ? "fr-overview e3-chief-workday" : "fr-overview"}>
    <WorkdayHeading title={title} description={admin?"Оборудование, команда и доступы.":undefined} label={admin?"Подготовка и доступы":"Сроки и назначения"} signals={chief && query.status!=="success" ? [] : signals}/>
    <WorkdayAssistant chiefWorkday={chief}/>
    {chief
      ? <ChiefWorkdayTimeline query={query} today={today} timezone={timezone} canCalendar={canCalendar}
          onRetry={()=>setTaskAttempt(attempt=>attempt+1)}/>
      : !admin && <WorkdayUpcoming tasks={upcoming} link={canCalendar?`/calendar?date=${today}`:undefined} linkText="Открыть график"/>}
    <DailyActions/>
  </div>;
}
