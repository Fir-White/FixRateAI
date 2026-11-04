import {useId,type ReactNode} from "react";
import {createPortal} from "react-dom";
import {useDialogFocus} from "@/shared/lib/useDialogFocus";
import {IconButton} from "./Button";
import {Icon} from "./Icon";
export function Drawer({open,title,onClose,children,footer}:{open:boolean;title:string;onClose:()=>void;children:ReactNode;footer?:ReactNode}) {
  const label=useId(),ref=useDialogFocus<HTMLDivElement>(open,onClose);
  if(!open)return null;
  return createPortal(<div className="fr-drawer-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)onClose();}}><div ref={ref} className="fr-drawer" role="dialog" aria-modal="true" aria-labelledby={label}><header><div><p className="fr-eyebrow">График обслуживания</p><h2 id={label}>{title}</h2></div><IconButton label="Закрыть подробности" variant="ghost" onClick={onClose}><Icon name="close" size={18}/></IconButton></header><div className="fr-drawer-content">{children}</div>{footer&&<footer>{footer}</footer>}</div></div>,document.querySelector(".workspace-root")??document.body);
}
