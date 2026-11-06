import { useSession } from "@/shared/session/SessionContext";
import { todayAt } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmployeeCalendar } from "./WorkforceSettingsPage";
import { DEMO_MODE } from "@/shared/api/request";
import { Callout } from "@/shared/ui/Callout";

export function PersonalShiftsPage() {
  const {profile}=useSession();
  if(!profile)return null;
  return <div className="space-y-6"><PageHeader title="Мои смены" description={`Рабочие интервалы и исключения. Время объекта: ${profile.timezone}.`}/>
    {DEMO_MODE ? <Callout>Для просмотра смен нужно подключение к серверу.</Callout> : <EmployeeCalendar person={{user_id:profile.userId}} today={todayAt(profile.timezone)} timezone={profile.timezone}/>}
  </div>;
}
