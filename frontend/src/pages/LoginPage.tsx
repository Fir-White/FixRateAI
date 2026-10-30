import { Navigate, useNavigate } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import {
  ROLE_DESCRIPTIONS,
  ROLE_LABELS,
  homePathForRole,
} from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";
import { Icon } from "@/shared/ui/Icon";

const ROLES: Role[] = ["dispatcher", "engineer", "executor", "admin"];

const ROLE_ICONS = {
  dispatcher: "dashboard",
  engineer: "quality",
  executor: "executor",
  admin: "equipment",
} as const;

export function LoginPage() {
  const { profile, login } = useSession();
  const navigate = useNavigate();

  if (profile) {
    return <Navigate to={homePathForRole(profile.role)} replace />;
  }

  const handleLogin = (role: Role) => {
    login(role);
    navigate(homePathForRole(role), { replace: true });
  };

  return (
    <div className="grid min-h-screen bg-[#f3f5f2] lg:grid-cols-[1.05fr_1fr]">
      <section className="relative flex flex-col justify-between overflow-hidden bg-[#10231b] px-6 py-8 text-white sm:px-10 lg:px-14 lg:py-12">
        <div className="absolute -top-24 -right-24 h-80 w-80 rounded-full bg-emerald-500/10 blur-2xl" />
        <div className="absolute bottom-0 left-0 h-64 w-64 rounded-full bg-amber-400/10 blur-2xl" />

        <div className="relative flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/20 text-sm font-black text-emerald-300">
            FR
          </span>
          <div>
            <p className="text-lg font-black">FixRate AI</p>
            <p className="text-xs text-emerald-100/60">
              Планирование ТО и ППР
            </p>
          </div>
        </div>

        <div className="relative my-12 max-w-xl">
          <p className="text-xs font-bold tracking-[0.2em] text-emerald-300 uppercase">
            Оборудование → регламент → календарь → задание → фотоотчёт → приёмка
          </p>
          <h1 className="mt-5 text-4xl leading-tight font-black tracking-tight sm:text-5xl">
            Один процесс обслуживания без разрывов
          </h1>
          <p className="mt-5 max-w-lg text-sm leading-7 text-emerald-50/70">
            Диспетчер видит просрочки и очередь. Инженер сравнивает прогнозы и
            принимает работу. Исполнитель фиксирует показания и фото. Решение
            остаётся за человеком.
          </p>
        </div>

        <div className="relative grid gap-3 text-sm text-emerald-50/70 sm:grid-cols-3">
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <p className="text-xl font-black text-white">93</p>
            <p className="mt-1 text-xs">вхождения в октябре</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <p className="text-xl font-black text-white">2</p>
            <p className="mt-1 text-xs">независимых прогноза</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <p className="text-xl font-black text-white">1</p>
            <p className="mt-1 text-xs">принятый факт в истории</p>
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-lg">
          <p className="text-xs font-bold tracking-[0.18em] text-emerald-700 uppercase">
            Демонстрационный вход
          </p>
          <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">
            Выберите роль
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Пароль и серверная сессия появятся вместе с backend. Сейчас выбор
            роли открывает соответствующий набор экранов.
          </p>

          <div className="mt-6 space-y-3">
            {ROLES.map((role) => (
              <button
                key={role}
                type="button"
                onClick={() => handleLogin(role)}
                className="group flex w-full items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-300 hover:shadow-md"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                  <Icon name={ROLE_ICONS[role]} size={22} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-bold text-slate-900">
                    {ROLE_LABELS[role]}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">
                    {ROLE_DESCRIPTIONS[role]}
                  </span>
                </span>
                <Icon
                  name="chevron"
                  size={18}
                  className="shrink-0 text-slate-400 group-hover:text-emerald-700"
                />
              </button>
            ))}
          </div>

          <p className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
            Это демонстрационная сессия на клиенте. Права, site scope и запрет
            собственной приёмки должны проверяться backend.
          </p>
        </div>
      </section>
    </div>
  );
}
