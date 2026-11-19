import { useSession } from "@/shared/session/SessionContext";
import { homePathForRole } from "@/shared/lib/roles";
import { AccessErrorPage } from "./AccessErrorPage";

export function NotFoundPage() {
  const { profile } = useSession();

  return (
    <AccessErrorPage code={404} title="Страница не найдена"
      target={profile ? homePathForRole(profile.role) : "/login"}
      action={profile ? "На главную" : "Войти"}>
      <p>Проверьте адрес или вернитесь в рабочее пространство.</p>
    </AccessErrorPage>
  );
}
