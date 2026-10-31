import { useState } from "react";
import { DEMO_MODE } from "@/shared/api/request";
import { Navigate, useNavigate } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import {
  ROLE_DESCRIPTIONS,
  ROLE_LABELS,
  homePathForRole,
} from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";
import { BrandLockup, BrandMark } from "@/shared/ui/Brand";
import { Icon } from "@/shared/ui/Icon";

const ROLES: Role[] = ["dispatcher", "engineer", "executor", "admin"];

const ROLE_ICONS = {
  dispatcher: "dashboard",
  engineer: "quality",
  executor: "executor",
  admin: "equipment",
} as const;

export function LoginPage() {
  const { profile, login, signIn, loading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [siteId, setSiteId] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();

  if (profile) {
    return <Navigate to={homePathForRole(profile.role)} replace />;
  }

  if (loading) return <p role="status">Загрузка сессии…</p>;
  if (!DEMO_MODE) return (
    <main className="app-backdrop grid min-h-screen place-items-center p-6">
      <form className="w-full max-w-md space-y-4 rounded-2xl border border-line bg-surface p-8" onSubmit={async event => {
        event.preventDefault(); setPending(true); setError("");
        try { const user = await signIn(email, password, siteId); navigate(homePathForRole(user.role), {replace: true}); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "Ошибка входа"); }
        finally { setPending(false); }
      }}>
        <BrandLockup size="lg" subtitle="Планирование ТО и ППР" />
        <h1 className="text-2xl">Вход в FixRate AI</h1>
        <label className="block">Email<input className="mt-1 block w-full rounded border border-line bg-surface-raised p-2" type="email" required autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label className="block">Пароль<input className="mt-1 block w-full rounded border border-line bg-surface-raised p-2" type="password" required autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label>
        <label className="block">ID объекта (если доступно несколько)<input className="mt-1 block w-full rounded border border-line bg-surface-raised p-2" value={siteId} onChange={e => setSiteId(e.target.value)} /></label>
        {error && <p role="alert" className="text-rose-300">{error}</p>}
        <button className="rounded bg-accent px-4 py-2 text-slate-950" disabled={pending}>{pending ? "Вход…" : "Войти"}</button>
      </form>
    </main>
  );

  const handleLogin = (role: Role) => {
    login(role);
    navigate(homePathForRole(role), { replace: true });
  };

  return (
    <div className="app-backdrop grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="relative flex flex-col justify-between overflow-hidden border-b border-line px-6 py-8 sm:px-10 lg:border-r lg:border-b-0 lg:px-14 lg:py-12">
        <div
          aria-hidden="true"
          className="absolute -top-28 -right-28 h-96 w-96 rounded-full bg-accent/[0.07] blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute bottom-0 left-0 h-72 w-72 rounded-full bg-accent/[0.04] blur-3xl"
        />

        <div className="relative">
          <BrandLockup size="lg" subtitle="Планирование ТО и ППР" />
        </div>

        <div className="relative my-14 max-w-xl">
          <p className="text-[10px] font-semibold tracking-[0.22em] text-accent uppercase">
            Оборудование → регламент → календарь → задание → фотоотчёт → приёмка
          </p>
          <h1 className="mt-5 text-hero leading-[0.98] font-semibold tracking-[-0.045em] text-ink">
            Один процесс обслуживания без разрывов
          </h1>
          <p className="mt-6 max-w-lg text-sm leading-7 text-muted sm:text-base">
            Диспетчер видит просрочки и очередь. Инженер сравнивает прогнозы и
            принимает работу. Исполнитель фиксирует показания и фото. Решение
            остаётся за человеком.
          </p>
        </div>

        <div className="relative grid gap-2 text-sm sm:grid-cols-3">
          <div className="rounded-xl border border-line bg-white/[0.025] p-4">
            <p className="text-xl font-semibold text-ink">93</p>
            <p className="mt-1 text-xs text-muted">вхождения в октябре</p>
          </div>
          <div className="rounded-xl border border-line bg-white/[0.025] p-4">
            <p className="text-xl font-semibold text-ink">2</p>
            <p className="mt-1 text-xs text-muted">независимых прогноза</p>
          </div>
          <div className="rounded-xl border border-line bg-white/[0.025] p-4">
            <p className="text-xl font-semibold text-ink">1</p>
            <p className="mt-1 text-xs text-muted">принятый факт в истории</p>
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center px-5 py-10 sm:px-10 lg:py-12">
        <div className="w-full max-w-lg">
          <div className="mb-7 flex items-center gap-4 lg:hidden">
            <BrandMark size={48} />
            <div>
              <p className="text-lg font-semibold tracking-[-0.03em] text-ink">
                FixRate AI
              </p>
              <p className="text-[10px] font-semibold tracking-[0.18em] text-muted uppercase">
                Демонстрационный вход
              </p>
            </div>
          </div>

          <p className="text-[10px] font-semibold tracking-[0.2em] text-accent uppercase">
            Демонстрационный вход
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-ink sm:text-3xl">
            Выберите роль
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted">
            Пароль и серверная сессия появятся вместе с backend. Сейчас выбор
            роли открывает соответствующий набор экранов.
          </p>

          <div className="mt-7 space-y-2.5">
            {ROLES.map((role) => (
              <button
                key={role}
                type="button"
                onClick={() => handleLogin(role)}
                className="group flex w-full items-center gap-4 rounded-xl border border-line bg-surface/70 p-4 text-left transition-colors hover:border-line-strong hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-line-strong bg-white/[0.035] text-ink-soft transition-colors group-hover:text-accent">
                  <Icon name={ROLE_ICONS[role]} size={21} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-ink">
                    {ROLE_LABELS[role]}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-muted">
                    {ROLE_DESCRIPTIONS[role]}
                  </span>
                </span>
                <Icon
                  name="chevron"
                  size={17}
                  className="shrink-0 text-muted transition-colors group-hover:text-accent"
                />
              </button>
            ))}
          </div>

          <p className="mt-6 rounded-xl border border-amber-300/20 bg-amber-300/[0.06] p-3 text-xs leading-5 text-amber-200/85">
            Это демонстрационная сессия на клиенте. Права, site scope и запрет
            собственной приёмки должны проверяться backend.
          </p>
        </div>
      </section>
    </div>
  );
}
