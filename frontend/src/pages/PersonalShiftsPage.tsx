import { useSession } from "@/shared/session/SessionContext";
import { todayAt } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmployeeCalendar } from "./WorkforceSettingsPage";
import { DEMO_MODE } from "@/shared/api/request";
import { Callout } from "@/shared/ui/Callout";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { Link } from "react-router-dom";
import { buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";

export function PersonalShiftsPage() {
  const {profile}=useSession();
  const tasks=useApiQuery(()=>!profile||DEMO_MODE?Promise.resolve([]):maintenanceApi.listExecutorTasks(profile.userId),[profile?.userId]);
  if(!profile)return null;
  return <div className="space-y-6"><PageHeader title="Мои смены" description="Ваш график, исключения и назначенные работы. Всё время указано в часовом поясе объекта." actions={<Link to="/executor" className={buttonClassName("secondary")}><Icon name="tasks" size={17}/>Мои задания</Link>}/>
    {DEMO_MODE ? <Callout>Для просмотра смен нужно подключение к серверу.</Callout> : <EmployeeCalendar personal person={{user_id:profile.userId}} today={todayAt(profile.timezone)} timezone={profile.timezone} tasks={tasks.status==="success"?tasks.data:undefined} tasksLoading={tasks.status==="loading"} tasksError={tasks.status==="error"?tasks.error:undefined}/>}
  </div>;
}
