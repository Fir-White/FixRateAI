import { MaintenanceInbox } from "@/features/notifications/MaintenanceInbox";
import { DEMO_MODE } from "@/shared/api/request";
import { useEffect, useRef, useState } from "react";
import {
  Outlet,
  NavLink,
  Link,
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
import { useWorkspaceBack } from "./WorkspaceNavigation";
import { NAVIGATION_ITEMS } from "./navigation";
import "./operations.css";
import { ContentTheme } from "@/shared/ui/ContentTheme";
import { preloadPage } from "@/app/pageModules";
import { SectionNavigation } from "./SectionNavigation";
import { AccessBrand } from "@/shared/ui/Brand";
import { useApiQueryCache } from "@/shared/lib/ApiQueryProvider";
import { warmWorkspacePath } from "@/features/navigation/warmWorkspacePath";
import { WorkspaceSite } from "./WorkspaceSite";
import { WorkspaceSearch } from "./WorkspaceSearch";
import { canOpenSection } from "@/shared/lib/roles";
import { dateLabel, DEMO_DATE } from "@/shared/lib/operations";
import { todayAt } from "@/shared/lib/format";
import "./e3-shell.css";

const ROLES: Role[] = ["director","chief_engineer","dispatcher", "engineer", "executor", "admin"];

export function AppShell({ executor = false }: { executor?: boolean }) {
  const { profile, switchRole } = useSession();
  const navigate = useNavigate();
  const workspaceBack = useWorkspaceBack();
  const location = useLocation();
  const navigationType = useNavigationType();
  const cache = useApiQueryCache();
  const contentRef = useRef<HTMLElement>(null);
  const topbarRef = useRef<HTMLElement>(null);
  useScrollBoundary(topbarRef);
  usePageEntry(contentRef, location.key, isAuthEntryNavigation(location.state, navigationType));
  const [menuOpen, setMenuOpen] = useWorkspaceState("sidebar.mobile-open", false, isBoolean);
  const previousPath = useRef(location.pathname);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia?.("(max-width: 1099px)")?.matches ?? false);
  const mobileOpen = isMobile && menuOpen;

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 1099px)");
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

  const items = NAVIGATION_ITEMS.filter(item => item.roles.includes(profile.role)).map(item => {
    if (item.to === "/dispatcher") return { ...item, to: homePathForRole(profile.role), label: profile.role==='director'?'Обзор объекта':item.label };
    return item;
  });
  const home = homePathForRole(profile.role);
  const searchItems = [...items];
  if(profile.role!=="executor"&&canOpenSection(profile.role,"calendar")) searchItems.push({to:"/calendar",label:"Действующий календарь",icon:"calendar",roles:[profile.role]});
  if(canOpenSection(profile.role,"service_settings")) searchItems.push({to:"/settings/equipment",label:"Настройка обслуживания",icon:"equipment",roles:[profile.role]});
  const warm = (path: string) => warmWorkspacePath(cache,path,profile.timezone);
  const initials = profile.name.trim().split(/\s+/).slice(0,2).map(part => [...part][0]).join("").toLocaleUpperCase("ru-RU");
  const handleRoleChange = (role: Role) => {
    switchRole(role);
    navigate(homePathForRole(role));
  };
  const warmProfile = () => { void preloadPage("/profile")?.catch(() => {}); };


  return (
    <div className="ops-shell e3-shell min-h-screen text-ink">
      <a
        href={executor ? "#executor-content" : "#main-content"}
        className="sr-only z-[60] rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-canvas focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Перейти к содержимому
      </a>

      {isMobile && <Sidebar
        timezone={profile.timezone}
        items={items}
        open={mobileOpen}
        onClose={() => setMenuOpen(false)}
      />}

      <div className="ops-stage" inert={mobileOpen} aria-hidden={mobileOpen || undefined}>
        <header ref={topbarRef} className="e3-topbar scroll-boundary">
          <div className="e3-topbar-inner">
            <Link to={home} className="e3-brand" aria-label="FixRate AI" onMouseEnter={()=>warm(home)}><AccessBrand /></Link>
            {!isMobile && <nav className="e3-navigation" aria-label="Основная навигация">
              {items.filter(item => item.to !== "/assistant").map(item => {
                const path = location.pathname.replace(/\/+$/, "");
                const active = [item.to, ...item.activePaths??[]].some(value=>path===value||(!item.end&&path.startsWith(value+"/")));
                const label = item.to==="/settings/workforce"?"Команда":item.to==="/quality"?"Приёмка":item.label;
                return <Link key={item.to} to={item.to} aria-label={item.label} aria-current={active?"page":undefined}
                  onClick={event=>{if(path===item.to&&event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey)event.preventDefault();}}
                  onMouseEnter={()=>warm(item.to)} onFocus={()=>warm(item.to)} onPointerDown={()=>warm(item.to)}><span>{label}</span></Link>;
              })}
            </nav>}
            <div className="fr-topbar-actions">
              <NavLink to="/assistant" className="e3-assistant-trigger" aria-label="ИИ-помощник" onMouseEnter={()=>warm("/assistant")} onFocus={()=>warm("/assistant")}><Icon name="assistant" size={22}/></NavLink>
              <MaintenanceInbox/>
              <NavLink to="/profile" className="e3-profile-trigger" aria-label="Учётная запись" onMouseEnter={warmProfile} onFocus={warmProfile} onPointerDown={warmProfile}><span aria-hidden="true">{initials}</span></NavLink>
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
              {isMobile && <IconButton label="Открыть меню" variant="ghost" aria-expanded={mobileOpen} aria-controls="application-sidebar" onClick={() => setMenuOpen(true)}><Icon name="menu" size={20}/></IconButton>}
            </div>
          </div>
        </header>
        <div className="e3-context">
          <WorkspaceSite name={profile.siteName} selected={profile.siteId}/>
          <span className="e3-context-role">{ROLE_LABELS[profile.role]}</span>
          {location.pathname.replace(/\/+$/, "") !== home && <button type="button" className="e3-context-back" onClick={workspaceBack}><Icon name="back" size={14}/>Назад</button>}
          <span className="e3-context-date">{dateLabel(DEMO_MODE?DEMO_DATE:todayAt(profile.timezone), {day:"numeric",month:"long",year:"numeric",weekday:"long"})}</span>
          <WorkspaceSearch items={searchItems}/>
        </div>

        <main
          ref={contentRef}
          id={executor ? "executor-content" : "main-content"}
          tabIndex={-1}
          className={`ops-main mx-auto px-4 py-6 sm:px-6 lg:px-8 lg:py-10 ${profile.role === "executor" ? "workspace-executor-main" : ""} ${location.pathname.replace(/\/+$/, "") === "/assistant" ? "ops-main--assistant" : ""}`}
        >
          <ContentTheme><SectionNavigation/><Outlet /></ContentTheme>
        </main>

      </div>
    </div>
  );
}
