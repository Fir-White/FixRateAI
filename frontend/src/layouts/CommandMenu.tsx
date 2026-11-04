import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { NavigationItem } from "./navigation";
import { Modal } from "@/shared/ui/Modal";
import { Input } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";

export function CommandMenu({items}:{items:readonly NavigationItem[]}) {
  const [open,setOpen]=useState(false), [search,setSearch]=useState("");
  useEffect(()=>{const key=(event:KeyboardEvent)=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){event.preventDefault();setOpen(value=>!value);}};window.addEventListener("keydown",key);return ()=>window.removeEventListener("keydown",key);},[]);
  const aliases:Record<string,string>={"/tasks":"наряды назначения", "/calendar":"график ппр", "/comparisons":"ai алгоритм сравнение", "/quality":"приёмка отчёты фото"};
  const filtered=items.filter(item=>`${item.label} ${aliases[item.to]??""}`.toLocaleLowerCase("ru").includes(search.trim().toLocaleLowerCase("ru")));
  const close=()=>{setOpen(false);setSearch("");};
  return <><button type="button" className="fr-command-trigger" onClick={()=>setOpen(true)} aria-label="Быстрый переход к разделу"><Icon name="search" size={15}/><span>Перейти к разделу</span><kbd>Ctrl K</kbd></button>
    <Modal open={open} onClose={close} title="Быстрый переход" description="Только разделы, доступные вашей роли."><Input data-dialog-autofocus aria-label="Название раздела" placeholder="Например, календарь или наряды…" value={search} onChange={e=>setSearch(e.target.value)} leadingIcon={<Icon name="search" size={17}/>}/><nav className="fr-command-results" aria-label="Результаты быстрого перехода">{filtered.map(item=><Link key={item.to} to={item.to} onClick={close}><Icon name={item.icon} size={18}/><span>{item.label}</span><Icon name="chevron" size={15}/></Link>)}{!filtered.length&&<p>Раздел не найден. Попробуйте другое название.</p>}</nav></Modal>
  </>;
}
