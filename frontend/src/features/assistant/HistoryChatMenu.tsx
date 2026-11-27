import {useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {Icon} from '@/shared/ui/Icon';

export function HistoryChatMenu({title,pinned,busy,onRename,onPin,onMultiSelect,onDelete}:{
  title:string;
  pinned:boolean;
  busy:boolean;
  onRename:()=>void;
  onPin:()=>void;
  onMultiSelect:()=>void;
  onDelete:()=>void;
}){
  const [open,setOpen]=useState(false);
  const id=useId();
  const root=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null);
  const close=()=>{setOpen(false);trigger.current?.focus({preventScroll:true});};
  useLayoutEffect(()=>{
    if(!open||!panel.current||!trigger.current)return;
    const element=panel.current, anchor=trigger.current.getBoundingClientRect();
    if(typeof element.showPopover==='function'){
      element.setAttribute('popover','manual');
      element.showPopover();
    }
    const {width,height}=element.getBoundingClientRect();
    element.style.left=`${Math.max(8,Math.min(anchor.right-width,window.innerWidth-width-8))}px`;
    const top=anchor.bottom+height+12<=window.innerHeight?anchor.bottom+4:Math.max(8,anchor.top-height-4);
    element.style.top=`${top}px`;
    element.querySelector('button')?.focus({preventScroll:true});
  },[open]);
  useEffect(()=>{
    if(!open)return;
    const outside=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false);};
    const dismiss=()=>setOpen(false);
    document.addEventListener('pointerdown',outside);
    window.addEventListener('scroll',dismiss,true);
    window.addEventListener('resize',dismiss);
    return()=>{
      document.removeEventListener('pointerdown',outside);
      window.removeEventListener('scroll',dismiss,true);
      window.removeEventListener('resize',dismiss);
    };
  },[open]);
  const invoke=(action:()=>void)=>{close();action();};
  return <div className="assistant-history-controls" ref={root} onBlur={event=>{
    if(open&&event.relatedTarget&&!event.currentTarget.contains(event.relatedTarget))setOpen(false);
  }} onKeyDown={event=>{
    if(open&&event.key==='Escape'){
      event.preventDefault();event.stopPropagation();close();
    }
  }}>
    <button type="button" ref={trigger} className="assistant-history-more" title="Действия чата"
      aria-label={`Действия чата: ${title}`} aria-expanded={open} aria-controls={open?id:undefined}
      onClick={()=>setOpen(value=>!value)}><Icon name="more" size={19}/></button>
    {open&&<div id={id} ref={panel} className="assistant-history-menu" role="group" aria-label="Действия чата">
      <button type="button" onClick={()=>invoke(onRename)} disabled={busy}><Icon name="edit" size={17}/>Переименовать</button>
      <button type="button" onClick={()=>invoke(onPin)} disabled={busy}><Icon name={pinned?'unpin':'pin'} size={17}/>{pinned?'Открепить':'Закрепить'}</button>
      <button type="button" onClick={()=>invoke(onMultiSelect)}><Icon name="tasks" size={17}/>Выбрать несколько</button>
      <button type="button" className="assistant-history-danger" onClick={()=>invoke(onDelete)}><Icon name="trash" size={17}/>Удалить</button>
    </div>}
  </div>;
}
