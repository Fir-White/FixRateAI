import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Icon, type IconName } from "@/shared/ui/Icon";
import { useSession } from "@/shared/session/SessionContext";
import { ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
}

const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  admin: [
    { to: "/dispatcher", label: "Панель диспетчера", icon: "dashboard" },
    { to: "/equipment", label: "Оборудование", icon: "equipment" },
  ],
  dispatcher: [
    { to: "/dispatcher", label: "Панель диспетчера", icon: "dashboard" },
    { to: "/calendar", label: "Календарь ТО", icon: "calendar" },
    { to: "/equipment", label: "Оборудование", icon: "equipment" },
    { to: "/tasks", label: "Задания", icon: "tasks" },
    { to: "/comparisons", label: "Прогнозы", icon: "forecast" },
  ],
  engineer: [
    { to: "/quality", label: "Контроль качества", icon: "quality" },
    { to: "/calendar", label: "Календарь ТО", icon: "calendar" },
    { to: "/equipment", label: "Оборудование", icon: "equipment" },
    { to: "/tasks", label: "Задания", icon: "tasks" },
    { to: "/comparisons", label: "Прогнозы", icon: "forecast" },
  ],
  executor: [
    { to: "/executor", label: "Мои задания", icon: "executor", end: true },
    { to: "/calendar", label: "Календарь ТО", icon: "calendar" },
    { to: "/equipment", label: "Оборудование", icon: "equipment" },
  ],
};

const ROLES: Role[] = ["dispatcher", "engineer", "executor", "admin"];

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15 text-sm font-black text-emerald-300">
        FR
      </span>
      <div>
        <p className="text-sm font-black tracking-wide text-white">FixRate AI</p>
        <p className="text-[11px] text-emerald-100/60">ТО / ППР</p>
      </div>
    </div>
  );
}

function NavItems({ items, compact = false }: { items: NavItem[]; compact?: boolean }) {
  return (
    <>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
              isActive
                ? compact
                  ? "bg-emerald-50 text-emerald-800"
                  : "bg-white/10 text-white"
                : compact
                  ? "text-slate-600 hover:bg-slate-100"
                  : "text-emerald-50/65 hover:bg-white/5 hover:text-white"
            }`
          }
        >
          <Icon name={item.icon} size={19} />
          {item.label}
        </NavLink>
      ))}
    </>
  );
}

export function AppShell() {
  const { profile, logout, switchRole } = useSession();
  const navigate = useNavigate();

  if (!profile) {
    return null;
  }

  const items = NAV_BY_ROLE[profile.role];

  const handleRoleChange = (role: Role) => {
    switchRole(role);
    navigate(homePathForRole(role));
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-[#f3f5f2] text-slate-900">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-72 flex-col bg-[#10231b] px-4 py-5 lg:flex">
        <div className="px-2">
          <Brand />
        </div>
        <nav className="mt-8 flex flex-1 flex-col gap-1">
          <NavItems items={items} />
        </nav>
        <div className="rounded-2xl bg-white/5 p-4">
          <p className="text-xs font-semibold tracking-wide text-emerald-100/50 uppercase">
            Объект
          </p>
          <p className="mt-2 text-sm font-semibold text-white">
            {profile.siteName}
          </p>
          <p className="mt-1 text-xs text-emerald-50/50">{profile.timezone}</p>
        </div>
      </aside>

      <div className="lg:pl-72">
        <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-[#f3f5f2]/95 backdrop-blur">
          <div className="flex items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3 lg:hidden">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#10231b] text-xs font-black text-white">
                FR
              </span>
              <p className="text-sm font-black text-slate-900">FixRate AI</p>
            </div>

            <div className="hidden items-center gap-2 lg:flex">
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600">
                Демо-данные · synthetic_demo
              </span>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              <div className="hidden text-right sm:block">
                <p className="text-sm font-semibold text-slate-900">
                  {profile.name}
                </p>
                <p className="text-xs text-slate-500">
                  {ROLE_LABELS[profile.role]}
                </p>
              </div>
              <select
                aria-label="Демонстрационная роль"
                value={profile.role}
                onChange={(event) =>
                  handleRoleChange(event.target.value as Role)
                }
                className="h-9 rounded-lg border border-slate-300 bg-white px-2 text-xs font-semibold text-slate-700"
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleLogout}
                title="Выйти"
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
              >
                <Icon name="logout" size={18} />
              </button>
            </div>
          </div>

          <nav className="flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden">
            <NavItems items={items} compact />
          </nav>
        </header>

        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
