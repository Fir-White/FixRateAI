import { Link } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import { ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";
import { buttonClassName } from "@/shared/ui/Button";
import { Card } from "@/shared/ui/Card";
import { Icon } from "@/shared/ui/Icon";

export function AccessDeniedPage({ allowedRoles }: { allowedRoles: Role[] }) {
  const { profile } = useSession();
  const target = profile ? homePathForRole(profile.role) : "/login";

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-xl items-center justify-center">
      <Card className="w-full border-amber-300/25 p-8 text-center">
        <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl border border-amber-300/25 bg-amber-300/10 text-amber-200">
          <Icon name="alert" size={20} />
        </span>
        <p className="mt-5 text-[10px] font-semibold tracking-[0.2em] text-amber-200 uppercase">
          Доступ ограничен
        </p>
        <h1 className="mt-3 text-xl font-semibold tracking-[-0.02em] text-ink">
          Раздел недоступен для текущей роли
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
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
