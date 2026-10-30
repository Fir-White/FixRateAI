import { Link } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import { ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";
import { buttonClassName } from "@/shared/ui/Button";
import { Card } from "@/shared/ui/Card";

export function AccessDeniedPage({ allowedRoles }: { allowedRoles: Role[] }) {
  const { profile } = useSession();
  const target = profile ? homePathForRole(profile.role) : "/login";

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-xl items-center justify-center">
      <Card className="w-full border-amber-200 p-8 text-center">
        <p className="text-xs font-bold tracking-[0.18em] text-amber-700 uppercase">
          Доступ ограничен
        </p>
        <h1 className="mt-3 text-xl font-black text-slate-950">
          Раздел недоступен для текущей роли
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Разрешённые роли:{" "}
          {allowedRoles.map((role) => ROLE_LABELS[role]).join(", ")}. Скрытие
          навигации не заменяет серверную проверку прав.
        </p>
        <Link to={target} className={buttonClassName("primary", "md", "mt-6")}>
          Вернуться в рабочий раздел
        </Link>
      </Card>
    </div>
  );
}
