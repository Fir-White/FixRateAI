import { Link, useLocation } from "react-router-dom";
import type { MouseEvent } from "react";
import { useDialogFocus } from "@/shared/lib/useDialogFocus";
import { useScrollBoundary } from "@/shared/lib/useScrollBoundary";
import { useApiQueryCache } from "@/shared/lib/ApiQueryProvider";
import { warmWorkspacePath } from "@/features/navigation/warmWorkspacePath";
import { AccessBrand } from "@/shared/ui/Brand";
import { Icon } from "@/shared/ui/Icon";
import type { NavigationItem } from "./navigation";
import "./Sidebar.css";

export function Sidebar({items, open, onClose, timezone}: {
  items: readonly NavigationItem[]; open: boolean; onClose: () => void; timezone: string;
}) {
  const cache = useApiQueryCache();
  const warm = (path: string) => warmWorkspacePath(cache,path,timezone);
  const pathname = useLocation().pathname.replace(/\/+$/,'');
  const dialog = useDialogFocus<HTMLElement>(open,onClose);
  useScrollBoundary(dialog,open);

  function follow(event: MouseEvent<HTMLAnchorElement>, path: string) {
    if (event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (pathname===path) event.preventDefault();
    onClose();
  }

  return <>
    {open&&<button type="button" className="ops-sidebar-backdrop" aria-label="Закрыть меню" tabIndex={-1} onClick={onClose}/>}
    <aside ref={dialog} id="application-sidebar" className="ops-sidebar scroll-boundary" role="dialog"
      aria-label="Мобильная навигация" aria-modal={open||undefined} aria-hidden={!open||undefined} inert={!open} data-open={open}>
      <header className="ops-sidebar-header"><AccessBrand/>
        <button type="button" className="ops-sidebar-toggle" aria-label="Закрыть меню" onClick={onClose}><Icon name="close" size={20}/></button>
      </header>
      <nav aria-label="Основная навигация" className="ops-sidebar-nav scroll-boundary" data-scroll-key="sidebar">
        <ul>{items.map((item,index)=>{
          const active=[item.to,...item.activePaths??[]].some(path=>pathname===path||!item.end&&pathname.startsWith(path+'/'));
          const showGroup=item.group&&item.group!==items[index-1]?.group;
          return <li key={item.to}>
            {showGroup&&<p className="fr-nav-caption">{item.group}</p>}
            <Link to={item.to} aria-current={active?"page":undefined} className="ops-sidebar-link"
              onFocus={()=>warm(item.to)} onPointerDown={()=>warm(item.to)} onClick={event=>follow(event,item.to)}>
              <Icon name={item.icon} size={19}/><span>{item.label}</span>
            </Link>
          </li>;
        })}</ul>
      </nav>
    </aside>
  </>;
}
