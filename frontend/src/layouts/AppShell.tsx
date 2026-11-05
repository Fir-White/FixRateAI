import { MaintenanceInbox } from "@/features/analyst/AnalystPanels";
import { DEMO_MODE } from "@/shared/api/request";
import { useEffect, useRef, useState } from "react";
import {
  Outlet,
  useLocation,
  useNavigationType,
  useNavigate,
} from "react-router-dom";
import { IconButton } from "@/shared/ui/Button";
import { Select } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { useSession } from "@/shared/session/SessionContext";
import { ROLE_LABELS, homePathForRole } from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";
import { usePageEntry } from "@/shared/motion/usePageEntry";
import { useScrollBoundary } from "@/shared/lib/useScrollBoundary";
import { isBoolean, useWorkspaceState } from "@/shared/lib/workspaceState";
import { isAuthEntryNavigation } from "@/shared/motion/authEntry";
import { Sidebar } from "./Sidebar";
import { SidebarAccount } from "./SidebarAccount";
import { NAVIGATION_ITEMS } from "./navigation";
import "./operations.css";

const ROLES: Role[] = ["executive","chief_engineer","dispatcher", "engineer", "executor", "admin"];

export function AppShell({ executor = false }: { executor?: boolean }) {
  const { profile, logout, switchRole } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const navigationType = useNavigationType();
  const contentRef = useRef<HTMLElement>(null);
  const topbarRef = useRef<HTMLElement>(null);
  useScrollBoundary(topbarRef);
  usePageEntry(contentRef, location.key, isAuthEntryNavigation(location.state, navigationType));
  const [menuOpen, setMenuOpen] = useWorkspaceState("sidebar.mobile-open", false, isBoolean);
  const previousPath = useRef(location.pathname);
  const [logoutError, setLogoutError] = useState("");
  const [logoutPending, setLogoutPending] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useWorkspaceState("sidebar.expanded", true, isBoolean);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia?.("(max-width: 1023px)")?.matches ?? false);
  const mobileOpen = isMobile && menuOpen;

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 1023px)");
    const synchronize = () => {
      setIsMobile(media.matches);
      if (!media.matches) setMenuOpen(false);
    };
    synchronize();
    media.addEventListener("change", synchronize);
    return () => media.removeEventListener("change", synchronize);
  }, []);

  useEffect(() => {
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      setMenuOpen(false);
    }
  }, [location.pathname]);

  if (!profile) {
    return null;
  }

  const items = NAVIGATION_ITEMS.filter(item => item.roles.includes(profile.role));
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

  const handleLogout = async () => {
    if (logoutPending) return;
    setLogoutError("");
    setLogoutPending(true);
    try { await logout(); navigate("/login"); }
    catch (error) { setLogoutError(error instanceof Error ? error.message : "Не удалось выйти"); }
    finally { setLogoutPending(false); }
  };

  return (
    <div className="ops-shell app-backdrop min-h-screen text-ink" data-sidebar-expanded={sidebarExpanded}>
      {logoutError && <p role="alert" className="fixed top-2 left-1/2 z-[70] rounded-xl bg-surface p-4 text-rose-200">{logoutError}</p>}
      <a
        href={executor ? "#executor-content" : "#main-content"}
        className="sr-only z-[60] rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-canvas focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Перейти к содержимому
      </a>

      <Sidebar
        items={items}
        homePath={homePathForRole(profile.role)}
        expanded={sidebarExpanded}
        mobile={isMobile}
        open={mobileOpen}
        onToggle={() => setSidebarExpanded(value => !value)}
        onClose={() => setMenuOpen(false)}
        footer={<SidebarAccount key={profile.userId} profile={profile} pending={logoutPending} onLogout={handleLogout} />}
      />

      <div className="ops-stage" inert={mobileOpen} aria-hidden={mobileOpen || undefined}>
        <header ref={topbarRef} className="ops-topbar scroll-boundary sticky top-0 z-30 border-b border-line bg-canvas/80 backdrop-blur-xl">
          <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <IconButton
                label="Открыть меню"
                variant="ghost"
                className="lg:hidden"
                aria-expanded={mobileOpen}
                aria-controls="application-sidebar"
                onClick={() => setMenuOpen(true)}
              >
                <Icon name="menu" size={20} />
              </IconButton>
              <div className="fr-breadcrumb"><span>Рабочее пространство</span><i>/</i><strong>{activeItem?.label ?? "Обзор"}</strong></div>
            </div>

              <div className="fr-topbar-actions"><MaintenanceInbox/>
              {DEMO_MODE && (
                <div className="fr-topbar-actions">
                  <span className="fr-demo-badge">DEMO</span>
                  <Select
                    aria-label="Демонстрационная роль"
                    value={profile.role}
                    onChange={(event) =>
                      handleRoleChange(event.target.value as Role)
                    }
                    className="fr-role-switch h-9 w-auto max-w-36 text-xs"
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </Select>
                </div>
              )}
              </div>

          </div>
        </header>

        <main
          ref={contentRef}
          id={executor ? "executor-content" : "main-content"}
          tabIndex={-1}
          className={`ops-main mx-auto px-4 py-6 sm:px-6 lg:px-8 lg:py-10 ${executor ? "workspace-executor-main" : ""}`}
        >
          <Outlet />
        </main>

      </div>
    </div>
  );
}
