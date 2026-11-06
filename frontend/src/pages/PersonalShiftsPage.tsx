import { readQueries } from "@/shared/api/readQueries";
import { useSession } from "@/shared/session/SessionContext";
import { todayAt } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmployeeCalendar } from "./WorkforceSettingsPage";
import { DEMO_MODE } from "@/shared/api/request";
import { Callout } from "@/shared/ui/Callout";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";

export function PersonalShiftsPage() {
  const {profile}=useSession();
  const tasks=useApiQuery(()=>!profile||DEMO_MODE?Promise.resolve([]):maintenanceApi.listExecutorTasks(profile.userId),[profile?.userId],undefined,DEMO_MODE?undefined:readQueries.tasks.key);
  if(!profile)return null;
  return <div className="space-y-6"><PageHeader title="Мои смены" description="Ваш график, исключения и назначенные работы. Всё время указано в часовом поясе объекта."/>
    {DEMO_MODE ? <Callout>Для просмотра смен нужно подключение к серверу.</Callout> : <EmployeeCalendar personal person={{user_id:profile.userId}} today={todayAt(profile.timezone)} timezone={profile.timezone} tasks={tasks.status==="success"?tasks.data:undefined} tasksLoading={tasks.status==="loading"} tasksError={tasks.status==="error"?tasks.error:undefined}/>}
  </div>;
}
