import { useSession } from "@/shared/session/SessionContext";
import { homePathForRole } from "@/shared/lib/roles";
import { AccessErrorPage } from "./AccessErrorPage";

export function AccessDeniedPage() {
  const { profile } = useSession();

  return (
    <AccessErrorPage code={403} title="Раздел недоступен"
      target={profile ? homePathForRole(profile.role) : "/login"}
      action={profile?.role === "executor" ? "К моим заданиям" : "Вернуться в рабочий раздел"}>
      <p>У вашей роли нет доступа к этому разделу.</p>
      <p>Если он нужен для работы, обратитесь к администратору.</p>
    </AccessErrorPage>
  );
}
