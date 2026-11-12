import { useEffect, useId, useRef, useState, type MouseEvent, type ReactNode, type SyntheticEvent } from "react";
import { createPortal } from "react-dom";
import { NavLink, useLocation } from "react-router-dom";
import brandMark from "@/assets/fixrate-mark.svg";
import brandWordmark from "@/assets/fixrate-wordmark.svg";
import { useDialogFocus } from "@/shared/lib/useDialogFocus";
import { useScrollBoundary } from "@/shared/lib/useScrollBoundary";
import { Icon } from "@/shared/ui/Icon";
import type { NavigationItem } from "./navigation";
import "./Sidebar.css";

interface SidebarProps {
  items: readonly NavigationItem[];
  expanded: boolean;
  mobile: boolean;
  open: boolean;
  onClose: () => void;
  onToggle: () => void;
  footer?: ReactNode;
}

export function Sidebar({ items, expanded, mobile, open, onClose, onToggle, footer }: SidebarProps) {
  const location = useLocation();
  const dialogRef = useDialogFocus<HTMLElement>(mobile && open, onClose);
  const tooltipId = useId();
  const [tooltip, setTooltip] = useState<{ to: string; label: string; left: number; top: number } | null>(null);
  const tooltipSuspended = useRef(false);
  const labelsVisible = mobile || expanded;
  const hidden = mobile && !open;
  useScrollBoundary(dialogRef, !hidden);

  useEffect(() => { setTooltip(null); }, [expanded, mobile, open]);
  useEffect(() => {
    const dismiss = () => { tooltipSuspended.current = true; setTooltip(null); };
    const visibility = () => { if (document.hidden) dismiss(); };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Tab" && !event.altKey && !event.ctrlKey && !event.metaKey) tooltipSuspended.current = false;
    };
    window.addEventListener("blur", dismiss);
    window.addEventListener("focus", dismiss);
    document.addEventListener("visibilitychange", visibility);
    document.documentElement.addEventListener("pointerleave", dismiss);
    document.addEventListener("keydown", keyboard, true);
    return () => {
      window.removeEventListener("blur", dismiss);
      window.removeEventListener("focus", dismiss);
      document.removeEventListener("visibilitychange", visibility);
      document.documentElement.removeEventListener("pointerleave", dismiss);
      document.removeEventListener("keydown", keyboard, true);
    };
  }, []);

  const showTooltip = (event: SyntheticEvent<HTMLAnchorElement>, item: NavigationItem) => {
    if (mobile || expanded) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const sidebar = event.currentTarget.closest("aside")!.getBoundingClientRect();
    setTooltip({ to: item.to, label: item.label, left: sidebar.right + 10, top: bounds.top + bounds.height / 2 });
  };

  const navigateOnce = (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    setTooltip(null);
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    // A detail page still needs a working link back to its section's root.
    if (location.pathname.replace(/\/+$/, "") === to.replace(/\/+$/, "")) event.preventDefault();
    if (mobile) onClose();
  };



  return <>
    {mobile && open && <button type="button" className="ops-sidebar-backdrop" aria-label="Закрыть меню" tabIndex={-1} onClick={onClose} />}
    <aside
      ref={dialogRef}
      id="application-sidebar"
      className="ops-sidebar scroll-boundary"
      data-expanded={labelsVisible}
      data-open={open}
      data-mobile={mobile}
      role={mobile ? "dialog" : undefined}
      aria-modal={mobile && open ? true : undefined}
      aria-label={mobile ? "Мобильная навигация" : "Рабочее пространство"}
      aria-hidden={hidden || undefined}
      inert={hidden}
    >
      <div className="ops-sidebar-header">
        <div className="ops-sidebar-brand">
          {mobile ? <span className="ops-sidebar-brand-mark"><img src={brandMark} alt="FixRate AI" /></span> :
            <button type="button" className="ops-sidebar-brand-control" aria-label={expanded ? "Свернуть меню" : "Развернуть меню"} aria-expanded={expanded} aria-controls="application-sidebar" onClick={onToggle}>
              <span className="ops-sidebar-brand-mark"><img src={brandMark} alt="" /><span className="ops-sidebar-brand-action"><Icon name="sidebar" size={20} /></span></span>
            </button>}
          <span className="ops-sidebar-label ops-sidebar-brand-name"><img src={brandWordmark} alt="FixRate AI" width="157" height="24" /></span>
        </div>
        {mobile && <button type="button" className="ops-sidebar-toggle" aria-label="Закрыть меню" aria-expanded={open} aria-controls="application-sidebar" onClick={onClose}>
          <span className="ops-sidebar-icon"><Icon name="close" size={18} /></span>
          <span className="topbar-hint" aria-hidden="true">Закрыть меню</span>
        </button>}
      </div>

      <nav aria-label="Основная навигация" className="ops-sidebar-nav scroll-boundary" data-scroll-key="sidebar" onScroll={() => setTooltip(null)}>
        <p className="fr-nav-caption ops-sidebar-label">Рабочее пространство</p>
        <ul>
          {items.map((item, index) => <li key={item.to}>
            {item.to.startsWith("/settings") && !items[index-1]?.to.startsWith("/settings") && <p className="fr-nav-caption fr-nav-divider ops-sidebar-label">Управление</p>}
            <NavLink
              to={item.to}
              end={item.end}
              aria-label={item.label}
              aria-describedby={tooltip?.to === item.to ? tooltipId : undefined}
              className="ops-sidebar-link"
              onMouseEnter={event => { tooltipSuspended.current = false; showTooltip(event, item); }}
              onMouseLeave={() => setTooltip(null)}
              onFocus={event => { if (!tooltipSuspended.current) showTooltip(event, item); }}
              onBlur={() => setTooltip(null)}
              onKeyDown={event => { if (event.key === "Escape") setTooltip(null); }}
              onClick={event => navigateOnce(event, item.to)}
            >
              <span className="ops-sidebar-icon"><Icon name={item.icon} size={20} /></span>
              <span className="ops-sidebar-label">{item.label}</span>
            </NavLink>
          </li>)}
        </ul>
      </nav>
      {footer && <div className="ops-sidebar-footer">{footer}</div>}
    </aside>
    {tooltip && !mobile && !expanded && createPortal(<div id={tooltipId} role="tooltip" className="ops-sidebar-tooltip" style={{ left: tooltip.left, top: tooltip.top }}>{tooltip.label}</div>, document.body)}
  </>;
}
