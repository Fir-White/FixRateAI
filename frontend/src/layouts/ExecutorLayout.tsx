import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Icon } from "@/shared/ui/Icon";
import { useSession } from "@/shared/session/SessionContext";
import { ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";

const ROLES: Role[] = ["dispatcher", "engineer", "executor", "admin"];

export function ExecutorLayout() {
  const { profile, logout, switchRole } = useSession();
  const navigate = useNavigate();

  if (!profile) {
    return null;
  }

  const handleRoleChange = (role: Role) => {
    switchRole(role);
    navigate(homePathForRole(role));
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-[#f3f5f2] pb-24 text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-[#10231b] px-4 py-3 text-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
          <Link to="/executor" className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/20 text-xs font-black text-emerald-300">
              FR
            </span>
            <div>
              <p className="text-sm font-black">FixRate AI</p>
              <p className="text-[11px] text-emerald-100/60">Кабинет исполнителя</p>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <select
              aria-label="Демонстрационная роль"
              value={profile.role}
              onChange={(event) => handleRoleChange(event.target.value as Role)}
              className="h-9 rounded-lg border border-white/15 bg-white/10 px-2 text-xs font-semibold text-white"
            >
              {ROLES.map((role) => (
                <option key={role} value={role} className="text-slate-900">
                  {ROLE_LABELS[role]}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleLogout}
              title="Выйти"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/15 text-white/80 hover:bg-white/10"
            >
              <Icon name="logout" size={18} />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-5 sm:py-7">
        <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3">
          <div>
            <p className="text-sm font-bold text-slate-900">{profile.name}</p>
            <p className="text-xs text-slate-500">
              {profile.siteName} · {profile.timezone}
            </p>
          </div>
          <span className="rounded-full bg-violet-50 px-2.5 py-1 text-[11px] font-bold text-violet-700">
            synthetic_demo
          </span>
        </div>
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white px-4 py-2">
        <div className="mx-auto flex max-w-3xl items-center justify-around">
          <NavLink
            to="/executor"
            end
            className={({ isActive }) =>
              `flex flex-col items-center gap-1 rounded-xl px-6 py-2 text-xs font-semibold ${
                isActive ? "bg-emerald-50 text-emerald-800" : "text-slate-500"
              }`
            }
          >
            <Icon name="tasks" size={20} />
            Мои задания
          </NavLink>
          <Link
            to="/calendar"
            className="flex flex-col items-center gap-1 rounded-xl px-6 py-2 text-xs font-semibold text-slate-500"
          >
            <Icon name="calendar" size={20} />
            Календарь
          </Link>
          <Link
            to="/equipment"
            className="flex flex-col items-center gap-1 rounded-xl px-6 py-2 text-xs font-semibold text-slate-500"
          >
            <Icon name="equipment" size={20} />
            Оборудование
          </Link>
        </div>
      </nav>
    </div>
  );
}
