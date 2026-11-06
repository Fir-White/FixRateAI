import { Link } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import { homePathForRole } from "@/shared/lib/roles";
import { BrandMark } from "@/shared/ui/Brand";
import { buttonClassName } from "@/shared/ui/Button";

export function NotFoundPage() {
  const { profile } = useSession();
  const target = profile ? homePathForRole(profile.role) : "/login";

  return (
    <div className="app-backdrop flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface/90 p-8 text-center shadow-2xl shadow-black/30">
        <BrandMark size={52} className="mx-auto text-ink" />
        <p className="mt-6 text-6xl font-semibold tracking-[-0.06em] text-accent">
          404
        </p>
        <h1 className="mt-3 text-xl font-semibold text-ink">
          Страница не найдена
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Проверьте адрес или вернитесь к рабочему разделу.
        </p>
        <Link to={target} className={buttonClassName("primary", "md", "mt-6")}>
          {profile ? "На главную" : "Войти"}
        </Link>
      </div>
    </div>
  );
}
