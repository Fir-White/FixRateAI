import { useState } from 'react';
import { readQueries } from '@/shared/api/readQueries';
import { DEMO_MODE } from '@/shared/api/request';
import { ROLE_LABELS } from '@/shared/lib/roles';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { useSession } from '@/shared/session/SessionContext';
import { Callout } from '@/shared/ui/Callout';
import { Icon } from '@/shared/ui/Icon';
import { Modal } from '@/shared/ui/Modal';
import { LoadingState } from '@/shared/ui/States';

export function WorkspaceSite({name, selected}: {name: string; selected?: string}) {
  const [open, setOpen] = useState(false);
  return DEMO_MODE ? <strong className="e3-site-name">{name}</strong> : <>
    <button type="button" className="e3-site-name" onClick={() => setOpen(true)}
      aria-haspopup="dialog" aria-expanded={open} title={name}>
      <span>{name}</span><Icon name="chevron" size={13}/>
    </button>
    {open && <SiteDialog selected={selected} onClose={() => setOpen(false)}/>}
  </>;
}

function SiteDialog({selected, onClose}: {selected?: string; onClose: () => void}) {
  const { switchSite } = useSession();
  const sites = useApiQuery(readQueries.sites.load, [], undefined, readQueries.sites.key);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function select(siteId: string) {
    if (pending) return;
    if (siteId === selected) {
      onClose();
      return;
    }
    setPending(true);
    setError('');
    try {
      await switchSite(siteId);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не удалось открыть объект');
      setPending(false);
    }
  }

  return <Modal open title="Выбрать объект" onClose={() => { if (!pending) onClose(); }} instant>
    {sites.status === 'loading' && <LoadingState label="Загрузка объектов"/>}
    {sites.status === 'error' && <Callout tone="danger">{sites.error}</Callout>}
    {sites.status === 'success' && <ul className="e3-site-options">
      {sites.data.map(site => <li key={site.site_id}>
        <button type="button" disabled={pending} aria-current={site.site_id === selected || undefined}
          onClick={() => void select(site.site_id)}>
          <span><strong>{site.name}</strong><small>{ROLE_LABELS[site.role]}</small></span>
          {site.site_id === selected && <Icon name="check" size={18}/>}
        </button>
      </li>)}
      {sites.data.length === 0 && <li>Доступных объектов нет</li>}
    </ul>}
    {error && <Callout tone="danger">{error}</Callout>}
  </Modal>;
}
