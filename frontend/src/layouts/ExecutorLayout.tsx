import { DEMO_MODE } from "@/shared/api/request";
import { useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { BrandLockup } from "@/shared/ui/Brand";
import { IconButton } from "@/shared/ui/Button";
import { Select } from "@/shared/ui/Form";
import { Icon, type IconName } from "@/shared/ui/Icon";
import { useSession } from "@/shared/session/SessionContext";
import { ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";
import { usePageEntry } from "@/shared/motion/usePageEntry";
import { isAuthEntryNavigation } from "@/shared/motion/authEntry";

const ROLES: Role[] = ["dispatcher", "engineer", "executor", "admin"];

const BOTTOM_NAV: { to: string; label: string; icon: IconName; end?: boolean }[] =
  [
    { to: "/executor", label: "Задания", icon: "tasks", end: true },
    { to: "/calendar", label: "Календарь", icon: "calendar" },
    { to: "/equipment", label: "Оборудование", icon: "equipment" },
    { to: "/my-shifts", label: "Мои смены", icon: "calendar" },
  ];

export function ExecutorLayout() {
  const { profile, logout, switchRole } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const navigationType = useNavigationType();
  const contentRef = useRef<HTMLElement>(null);
  usePageEntry(contentRef, location.key, isAuthEntryNavigation(location.state, navigationType));
  const [logoutError, setLogoutError] = useState("");

  if (!profile) {
    return null;
  }

  const handleRoleChange = (role: Role) => {
    switchRole(role);
    navigate(homePathForRole(role));
  };

  const handleLogout = async () => {
    setLogoutError("");
    try { await logout(); navigate("/login"); }
    catch (error) { setLogoutError(error instanceof Error ? error.message : "Не удалось выйти"); }
  };

  return (
    <div className="app-backdrop min-h-screen pb-28 text-ink">
      {logoutError && <p role="alert" className="rounded-xl bg-surface p-4 text-rose-200">{logoutError}</p>}
      <a
        href="#executor-content"
        className="sr-only z-[60] rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-canvas focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Перейти к содержимому
      </a>

      <header className="sticky top-0 z-30 border-b border-line bg-canvas/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
          <Link
            to="/executor"
            className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
          >
            <BrandLockup size="sm" subtitle="Кабинет исполнителя" />
          </Link>
          <div className="flex items-center gap-2">
            <Select
              disabled={!DEMO_MODE}
              aria-label="Демонстрационная роль"
              value={profile.role}
              onChange={(event) => handleRoleChange(event.target.value as Role)}
              className="h-9 w-auto max-w-36 text-xs"
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
        ref={contentRef}
        id="executor-content"
        tabIndex={-1}
        className="mx-auto max-w-3xl px-4 py-5 sm:py-7"
      >
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface/80 px-4 py-3">
          <div>
            <p className="text-sm font-semibold text-ink">{profile.name}</p>
            <p className="mt-0.5 text-xs text-muted">
              {profile.siteName} · {profile.timezone}
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white/[0.03] px-2 py-1 text-[10px] font-semibold tracking-wide text-muted uppercase">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            {DEMO_MODE ? "synthetic_demo" : "API подключён"}
          </span>
        </div>
        <Outlet />
      </main>

      <nav
        aria-label="Навигация исполнителя"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-canvas/90 px-4 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur-xl"
      >
        <div className="mx-auto flex max-w-3xl items-center justify-around">
          {BOTTOM_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex min-w-24 flex-col items-center gap-1 rounded-xl px-4 py-2 text-[11px] font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  isActive
                    ? "bg-white/[0.06] text-accent"
                    : "text-muted hover:bg-white/[0.04] hover:text-ink"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon name={item.icon} size={20} className={isActive ? "text-accent" : ""} />
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
