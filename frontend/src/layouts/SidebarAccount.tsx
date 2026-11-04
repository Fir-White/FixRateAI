import { useEffect, useId, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ROLE_LABELS } from "@/shared/lib/roles";
import { useScrollBoundary } from "@/shared/lib/useScrollBoundary";
import type { SessionProfile } from "@/shared/types/domain";
import { Icon } from "@/shared/ui/Icon";

export function SidebarAccount({ profile, pending, onLogout }: { profile: SessionProfile; pending: boolean; onLogout: () => void }) {
  const [view, setView] = useState<"menu" | "profile" | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useScrollBoundary(panelRef, view !== null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const firstAction = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const location = useLocation();
  const initials = profile.name.trim().split(/\s+/).slice(0, 2).map(part => [...part][0] ?? "").join("").toLocaleUpperCase("ru-RU") || "FR";

  useEffect(() => { setView(null); }, [location.pathname, profile.userId]);
  useEffect(() => {
    if (!view) return;
    firstAction.current?.focus();
    const outside = (event: PointerEvent) => { if (!rootRef.current?.contains(event.target as Node)) setView(null); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [view]);

  return <div className="workspace-account" ref={rootRef} onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setView(null);
  }} onKeyDown={event => {
    if (view && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setView(null); buttonRef.current?.focus(); }
  }}>
    {view && <div ref={panelRef} className="workspace-account-panel scroll-boundary" id={panelId} role="dialog" aria-label={view === "profile" ? "Мой профиль" : "Меню аккаунта"}>
      {view === "profile" ? <>
        <button type="button" className="workspace-account-action" ref={firstAction} onClick={() => setView("menu")}><Icon name="back" size={16} />Назад к меню</button>
        <h2>Мой профиль</h2>
        <dl>
          <dt>Имя</dt><dd>{profile.name}</dd>
          <dt>Email</dt><dd>{profile.email}</dd>
          <dt>Роль</dt><dd>{ROLE_LABELS[profile.role]}</dd>
          <dt>Объект</dt><dd>{profile.siteName}</dd>
          <dt>Часовой пояс</dt><dd>{profile.timezone}</dd>
        </dl>
      </> : <>
        <p className="workspace-account-heading">{profile.name}<small>{profile.siteName}</small></p>
        <button type="button" className="workspace-account-action" ref={firstAction} onClick={() => setView("profile")}><Icon name="user" size={17} />Мой профиль</button>
        <button type="button" className="workspace-account-action workspace-account-logout" disabled={pending} onClick={onLogout}><Icon name="logout" size={17} />{pending ? "Выход…" : "Выйти из аккаунта"}</button>
      </>}
    </div>}
    <button type="button" className="workspace-account-trigger" ref={buttonRef} title={`${profile.name} · ${ROLE_LABELS[profile.role]}`} aria-label={`Меню аккаунта: ${profile.name}`} aria-haspopup="dialog" aria-expanded={!!view} aria-controls={view ? panelId : undefined} onClick={() => setView(value => value ? null : "menu")}>
      <span className="workspace-account-avatar" aria-hidden="true">{initials}</span>
      <span className="ops-sidebar-label workspace-account-label"><strong>{profile.name}</strong><small>{ROLE_LABELS[profile.role]}</small></span>
      <span className="workspace-account-more" aria-hidden="true">···</span>
    </button>
  </div>;
}
