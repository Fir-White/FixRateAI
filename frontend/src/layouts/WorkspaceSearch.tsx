import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { IconButton } from '@/shared/ui/Button';
import { Icon } from '@/shared/ui/Icon';
import { Input } from '@/shared/ui/Form';
import { Modal } from '@/shared/ui/Modal';

export function WorkspaceSearch({items}: {items: readonly {to:string;label:string}[]}) {
  const [open,setOpen] = useState(false);
  const [query,setQuery] = useState('');

  function show() {
    setQuery('');
    setOpen(true);
  }

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((!event.ctrlKey&&!event.metaKey) || event.key.toLowerCase()!=='k' || document.querySelector('[role="dialog"][aria-modal="true"]')) return;
      event.preventDefault();
      show();
    }
    document.addEventListener('keydown',shortcut);
    return () => document.removeEventListener('keydown',shortcut);
  }, []);

  const term = query.toLocaleLowerCase('ru').trim();
  const matches = items.filter(item=>item.label.toLocaleLowerCase('ru').includes(term));
  return <>
    <IconButton label="Поиск по рабочему пространству" variant="ghost" className="e3-workspace-search" onClick={show}>
      <Icon name="search" size={18}/>
    </IconButton>
    <Modal open={open} title="Поиск по рабочему пространству" onClose={()=>setOpen(false)} instant>
      <Input data-dialog-autofocus aria-label="Найти раздел" placeholder="Название раздела" value={query} onChange={event=>setQuery(event.target.value)}/>
      {matches.length ? <ul className="e3-search-results">
        {matches.map(item=><li key={item.to}><Link to={item.to} onClick={()=>setOpen(false)}>{item.label}<Icon name="chevron" size={15}/></Link></li>)}
      </ul> : <p className="mt-4 text-muted">Разделы не найдены.</p>}
    </Modal>
  </>;
}
