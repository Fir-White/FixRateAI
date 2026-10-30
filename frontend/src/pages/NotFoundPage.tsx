import { Link } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import { homePathForRole } from "@/shared/lib/roles";
import { buttonClassName } from "@/shared/ui/Button";

export function NotFoundPage() {
  const { profile } = useSession();
  const target = profile ? homePathForRole(profile.role) : "/login";

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f3f5f2] px-4">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <p className="text-6xl font-black tracking-tight text-emerald-700">404</p>
        <h1 className="mt-4 text-xl font-black text-slate-950">
          Страница не найдена
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Проверьте адрес или вернитесь к рабочему разделу.
        </p>
        <Link to={target} className={buttonClassName("primary", "md", "mt-6")}>
          На главную
        </Link>
      </div>
    </div>
  );
}
