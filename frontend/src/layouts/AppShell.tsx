import { DEMO_MODE } from "@/shared/api/request";
import { useEffect, useState } from "react";
import {
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { BrandLockup } from "@/shared/ui/Brand";
import { Button, IconButton } from "@/shared/ui/Button";
import { Select } from "@/shared/ui/Form";
import { Icon, type IconName } from "@/shared/ui/Icon";
import { useDialogFocus } from "@/shared/lib/useDialogFocus";
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

function NavItems({
  items,
  onNavigate,
}: {
  items: NavItem[];
  onNavigate?: () => void;
}) {
  return (
    <>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl border px-3 py-2.5 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              isActive
                ? "border-line-strong bg-white/[0.065] text-ink"
                : "border-transparent text-muted hover:bg-white/[0.04] hover:text-ink"
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon
                name={item.icon}
                size={18}
                className={isActive ? "text-accent" : ""}
              />
              {item.label}
            </>
          )}
        </NavLink>
      ))}
    </>
  );
}

export function AppShell() {
  const { profile, logout, switchRole } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useDialogFocus<HTMLElement>(menuOpen, () =>
    setMenuOpen(false),
  );

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  if (!profile) {
    return null;
  }

  const items = NAV_BY_ROLE[profile.role];
  const activeItem = items
    .filter(
      (item) =>
        location.pathname === item.to ||
        location.pathname.startsWith(`${item.to}/`),
    )
    .sort((left, right) => right.to.length - left.to.length)[0];

  const handleRoleChange = (role: Role) => {
    switchRole(role);
    navigate(homePathForRole(role));
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="app-backdrop min-h-screen text-ink">
      <a
        href="#main-content"
        className="sr-only z-[60] rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-canvas focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Перейти к содержимому
      </a>

      <aside className="fixed inset-y-0 left-0 z-40 hidden w-72 flex-col border-r border-line bg-canvas-soft/90 px-4 py-5 backdrop-blur-xl lg:flex">
        <div className="px-2">
          <BrandLockup />
        </div>
        <nav aria-label="Основная навигация" className="mt-9 flex flex-1 flex-col gap-1">
          <p className="mb-2 px-3 text-[10px] font-semibold tracking-[0.18em] text-muted uppercase">
            Рабочее пространство
          </p>
          <NavItems items={items} />
        </nav>
        <div className="rounded-xl border border-line bg-white/[0.025] p-4">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            <p className="text-[10px] font-semibold tracking-[0.16em] text-muted uppercase">
              Объект
            </p>
          </div>
          <p className="mt-2 text-sm font-semibold text-ink">
            {profile.siteName}
          </p>
          <p className="mt-1 text-xs text-muted">{profile.timezone}</p>
        </div>
      </aside>

      {menuOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Закрыть меню"
            className="absolute inset-0 bg-black/75 backdrop-blur-sm"
            onClick={() => setMenuOpen(false)}
          />
          <aside
            ref={menuRef}
            id="mobile-navigation"
            role="dialog"
            aria-modal="true"
            aria-label="Мобильная навигация"
            className="relative flex h-full w-[min(20rem,88vw)] flex-col border-r border-line bg-canvas-soft px-4 py-5 shadow-2xl shadow-black/60"
          >
            <div className="flex items-center justify-between px-2">
              <BrandLockup />
              <IconButton
                label="Закрыть меню"
                variant="ghost"
                onClick={() => setMenuOpen(false)}
              >
                <Icon name="close" size={18} />
              </IconButton>
            </div>
            <nav aria-label="Мобильная навигация" className="mt-8 flex-1 space-y-1">
              <p className="mb-2 px-3 text-[10px] font-semibold tracking-[0.18em] text-muted uppercase">
                Рабочее пространство
              </p>
              <NavItems items={items} onNavigate={() => setMenuOpen(false)} />
            </nav>
            <div className="space-y-3 border-t border-line pt-4">
              <label className="block">
                <span className="mb-1.5 block text-[10px] font-semibold tracking-[0.16em] text-muted uppercase">
                  Роль
                </span>
                <Select
                    disabled={!DEMO_MODE}
                  aria-label="Демонстрационная роль"
                  value={profile.role}
                  onChange={(event) =>
                    handleRoleChange(event.target.value as Role)
                  }
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </option>
                  ))}
                </Select>
              </label>
              <Button
                variant="ghost"
                className="w-full justify-start"
                onClick={handleLogout}
              >
                <Icon name="logout" size={18} />
                Выйти
              </Button>
            </div>
          </aside>
        </div>
      ) : null}

      <div className="lg:pl-72" inert={menuOpen} aria-hidden={menuOpen || undefined}>
        <header className="sticky top-0 z-30 border-b border-line bg-canvas/80 backdrop-blur-xl">
          <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <IconButton
                label="Открыть меню"
                variant="ghost"
                className="lg:hidden"
                aria-expanded={menuOpen}
                aria-controls="mobile-navigation"
                onClick={() => setMenuOpen(true)}
              >
                <Icon name="menu" size={20} />
              </IconButton>
              <div className="min-w-0 lg:hidden">
                <BrandLockup size="sm" subtitle="Рабочее пространство" />
              </div>
              <div className="hidden min-w-0 lg:block">
                <p className="text-[10px] font-semibold tracking-[0.16em] text-muted uppercase">
                  Рабочее пространство
                </p>
                <p className="mt-0.5 truncate text-sm font-semibold text-ink">
                  {activeItem?.label ?? "FixRate AI"}
                </p>
              </div>
            </div>

            <div className="hidden items-center gap-2 sm:gap-3 md:flex">
              <span className="hidden items-center gap-2 rounded-lg border border-line bg-white/[0.03] px-2.5 py-1.5 text-[10px] font-semibold tracking-wide text-muted uppercase xl:inline-flex">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                {DEMO_MODE ? "synthetic_demo" : "API подключён"}
              </span>
              <div className="hidden text-right lg:block">
                <p className="text-xs font-semibold text-ink">{profile.name}</p>
                <p className="text-[10px] text-muted">
                  {ROLE_LABELS[profile.role]}
                </p>
              </div>
              <Select
                    disabled={!DEMO_MODE}
                aria-label="Демонстрационная роль"
                value={profile.role}
                onChange={(event) =>
                  handleRoleChange(event.target.value as Role)
                }
                className="h-9 w-auto max-w-36 text-xs md:max-w-40"
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </Select>
              <IconButton label="Выйти" variant="ghost" onClick={handleLogout}>
                <Icon name="logout" size={18} />
              </IconButton>
            </div>
          </div>
        </header>

        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-10"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
