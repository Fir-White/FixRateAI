import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { registryApi } from '@/shared/api/registry';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { useSession } from '@/shared/session/SessionContext';
import { canOpenSection } from '@/shared/lib/roles';
import { Button, buttonClassName } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { PageHeader } from '@/shared/ui/PageHeader';
import { FieldCaption, Input, Select } from '@/shared/ui/Form';
import { Callout } from '@/shared/ui/Callout';
import { LoadingState, ErrorState, EmptyState } from '@/shared/ui/States';
import { systemGroups, usageUnits, type RegistryItem, type RegistrySystem, type SystemGroup } from '@/shared/types/registry';
import { ComponentPanel } from './ComponentPanel';
import { RegistryExcel } from './RegistryExcel';
import './registry.css';

const failure = (error: unknown) => error instanceof Error ? error.message : 'Не удалось сохранить';
export function EquipmentRegistry() {
  const {profile, switchSite} = useSession();
  const [refresh, setRefresh] = useState(0); const [group, setGroup] = useState<SystemGroup | 'unclassified'>('electricity');
  const [search, setSearch] = useState(''); const [selected, setSelected] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const mayEdit = profile?.role === 'chief_engineer' || profile?.role === 'admin';
  const query = useApiQuery(async () => {
    const [registry, sites] = await Promise.all([registryApi.load(), registryApi.sites()]);
    if (!Array.isArray(registry.items) || !Array.isArray(registry.systems) || !Array.isArray(sites)) throw new Error('Не удалось загрузить реестр оборудования');
    return {registry, sites};
  }, [profile?.siteId, refresh]);
  const systems = query.data?.registry.systems ?? [];
  const all = query.data?.registry.items ?? [];
  const items = useMemo(() => all.filter(item => {
    const system = systems.find(row => row.id === item.system_id);
    return (system?.system_group ?? 'unclassified') === group && (!search.trim() || [item.name, item.asset_code, item.location,
      ...item.services.map(service => service.title), ...item.components.map(part => part.name)].join(' ').toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  }), [all, systems, group, search]);
  const active = all.find(row => row.equipment_id === selected);
  return <div className="space-y-6 registry-page"><PageHeader title="Работы + реестр оборудования" description="Оборудование, регламенты ТО и наработка деталей по зданиям." actions={mayEdit ? <Link to="/settings/equipment" className={buttonClassName('primary')}>Добавить оборудование</Link> : undefined}/>
    {error && <p role="alert"><Callout tone="danger">{error}</Callout></p>}
    {query.status === 'loading' && <LoadingState/>}{query.status === 'error' && <ErrorState description={query.error}/>}
    {query.status === 'success' && <>
      <RegistryExcel mayImport={mayEdit} onSaved={() => setRefresh(n => n+1)}/>
      <Card className="space-y-4 p-5"><div className="registry-tools"><label className="space-y-1 text-sm"><FieldCaption>Здание</FieldCaption><Select aria-label="Здание" value={query.data.registry.site_id} disabled={busy} onChange={async e => {setBusy(true); setError(''); try{await switchSite(e.target.value);}catch(error){setError(failure(error));setBusy(false);}}}>{query.data.sites.map(site => <option key={site.site_id} value={site.site_id}>{site.name}</option>)}</Select></label><label className="space-y-1 text-sm"><FieldCaption>Поиск оборудования, работы или детали</FieldCaption><Input aria-label="Поиск по реестру" value={search} onChange={e => setSearch(e.target.value)} placeholder="Название, номер или расположение"/></label></div>
        {mayEdit && <BuildingForm timezone={profile?.timezone ?? 'Asia/Yekaterinburg'} onSaved={() => setRefresh(n => n+1)}/>}
        <div className="registry-tabs" role="tablist" aria-label="Инженерные системы">{(Object.entries(systemGroups) as [SystemGroup, string][]).map(([key, label]) => <Button key={key} role="tab" id={`registry-tab-${key}`} aria-controls="registry-table-panel" aria-selected={group === key} variant={group === key ? 'primary' : 'ghost'} onClick={() => {setGroup(key);setSelected('');}}>{label} <span>{all.filter(item => systems.find(system => system.id === item.system_id)?.system_group === key).length}</span></Button>)}<Button role="tab" id="registry-tab-unclassified" aria-controls="registry-table-panel" aria-selected={group === 'unclassified'} variant={group === 'unclassified' ? 'primary' : 'ghost'} onClick={() => {setGroup('unclassified');setSelected('');}}>Без группы <span>{all.filter(item => !systems.find(system => system.id === item.system_id)?.system_group).length}</span></Button></div>
      </Card>
      {systems.some(system => !system.system_group) && <Callout>Есть системы без группы. Их оборудование сохранено во вкладке «Без группы». {mayEdit ? 'Укажите группу ниже, чтобы распределить его по таблицам.' : 'Главный инженер может указать группу системы.'}</Callout>}
      {mayEdit && <SystemGroups systems={systems} onSaved={() => setRefresh(n => n+1)}/>}
      <div id="registry-table-panel" role="tabpanel" aria-labelledby={`registry-tab-${group}`}>
        {!items.length ? <EmptyState title="В этой таблице пока нет оборудования" description={search ? 'Измените поисковый запрос.' : 'Добавьте оборудование или укажите группу существующей системы.'}/> : <Card className="overflow-hidden"><div className="registry-scroll"><table className="registry-table" aria-label={`${group === 'unclassified' ? 'Без группы' : systemGroups[group]} — работы и оборудование`}><thead><tr><th>Оборудование</th><th>Работы и периодичность</th><th>Трудозатраты на одно ТО</th><th>Детали и наработка</th><th><span className="sr-only">Действия</span></th></tr></thead><tbody>{items.map(item => <RegistryRow key={item.equipment_id} item={item} system={systems.find(system => system.id === item.system_id)} selected={selected === item.equipment_id} canConfigure={canOpenSection(profile?.role,'service_settings')} onSelect={() => setSelected(selected === item.equipment_id ? '' : item.equipment_id)}/>)}</tbody></table></div></Card>}
      </div>
      {active && <section className="space-y-4" aria-label={`Детали: ${active.name}`}><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">{active.name} · {active.asset_code}</h2>{mayEdit && <Link to={`/settings/equipment?equipment=${encodeURIComponent(active.equipment_id)}`} className={buttonClassName('secondary')}>Настроить оборудование и работы</Link>}</div><ComponentPanel equipmentId={active.equipment_id} onChanged={() => setRefresh(n => n+1)}/></section>}
    </>}
  </div>;
}

function RegistryRow({item, system, selected, canConfigure, onSelect}: {item: RegistryItem; system?: RegistrySystem; selected: boolean; canConfigure: boolean; onSelect: () => void}) {
  const totals = new Map<string, {hours: number; incomplete: boolean}>();
  for(const service of item.services) { const total = totals.get(service.maintenance_type) ?? {hours: 0, incomplete: false};
    if(service.norm_unit === 'person_hour' && service.norm_value !== null) total.hours += Number(service.norm_value); else total.incomplete = true;
    totals.set(service.maintenance_type, total);
  }
  return <tr><td><Link className="font-semibold text-accent" to={`/equipment/${encodeURIComponent(item.equipment_id)}`}>{item.name}</Link><p className="font-mono">{item.asset_code}</p><p>{system?.name} · {item.location || 'Расположение не указано'}</p>{item.status !== 'active' && <p>{item.status === 'retired' ? 'Списано' : 'В ремонте'}</p>}</td>
    <td>{!item.services.length ? 'Регламенты не заданы' : item.services.map(service => <div key={service.binding_id} className="registry-operation"><strong>{service.maintenance_type} · {service.title}</strong><p>{service.source_text || 'Периодичность не указана'}</p><p>{service.norm_value ?? 'Нет нормы'} {service.norm_unit === 'person_hour' ? 'чел.-ч' : service.norm_unit === 'elapsed_hour' ? 'ч длительности' : '(единица не подтверждена)'} · {service.crew_size} чел. · {service.enabled ? 'Действует' : 'Черновик'}</p></div>)}</td>
    <td>{[...totals].map(([type, value]) => <p key={type}><strong>{type}: {value.hours.toLocaleString('ru-RU')} чел.-ч</strong>{value.incomplete && <small>Известная часть; есть неподтверждённые нормы</small>}</p>)}{!totals.size && 'Нет данных'}<small>Дневная и месячная нагрузка — в календаре.</small></td>
    <td>{item.components.filter(part => !part.removed_on).map(part => <p key={part.component_id}><strong>{part.name}</strong><br/>{Number(part.current_usage).toLocaleString('ru-RU')} {usageUnits[part.usage_unit]} · {part.remaining_usage === null ? 'Ресурс не задан' : `остаток ${Number(part.remaining_usage).toLocaleString('ru-RU')} ${usageUnits[part.usage_unit]}`}</p>)}{!item.components.some(part => !part.removed_on) && 'Не внесены'}</td>
    <td><Button variant="secondary" aria-expanded={selected} onClick={onSelect}>{selected ? 'Скрыть детали' : 'Детали и наработка'}</Button>{canConfigure && <Link className="mt-3 block text-accent underline" to={`/settings/equipment?equipment=${encodeURIComponent(item.equipment_id)}`}>Работы и регламенты</Link>}</td></tr>;
}

function SystemGroups({systems, onSaved}: {systems: RegistrySystem[]; onSaved: () => void}) {
  const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  return <details className="fr-rule-section"><summary>Группы инженерных систем</summary><div className="space-y-3 p-4">{systems.map(system => <label className="registry-tools text-sm" key={system.id}><span>{system.name} · {system.code}{!system.is_active ? ' (неактивна)' : ''}</span><Select aria-label={`Группа системы ${system.name}`} value={system.system_group ?? ''} disabled={!!busy} onChange={async e => {setBusy(system.id);setError('');try{await registryApi.classify(system.id, system.revision, (e.target.value || null) as SystemGroup | null);onSaved();}catch(error){setError(failure(error));}finally{setBusy('');}}}><option value="">Без группы</option>{Object.entries(systemGroups).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></label>)}{error && <p role="alert">{error}</p>}</div></details>;
}

function BuildingForm({timezone, onSaved}: {timezone: string; onSaved: () => void}) {
  const [name, setName] = useState(''); const [address, setAddress] = useState(''); const [zone, setZone] = useState(timezone);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  return <details><summary className="cursor-pointer text-sm text-accent">Добавить здание</summary><form className="mt-4 space-y-3" onSubmit={async e => {e.preventDefault();if(busy)return;setBusy(true);setError('');try{await registryApi.createBuilding({name,address: address || null,timezone: zone});setName('');setAddress('');setNotice('Здание создано и доступно в списке. Доступ сотрудников настраивается отдельно.');onSaved();}catch(error){setError(failure(error));}finally{setBusy(false);}}}><p className="text-sm text-muted">Создатель и действующие администраторы текущего здания получат доступ к новому. Роли остальных сотрудников не переносятся.</p><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3"><label className="text-sm"><FieldCaption>Название здания</FieldCaption><Input aria-label="Название здания" required value={name} onChange={e => setName(e.target.value)}/></label><label className="text-sm"><FieldCaption>Адрес здания</FieldCaption><Input aria-label="Адрес здания" value={address} onChange={e => setAddress(e.target.value)}/></label><label className="text-sm"><FieldCaption>Часовой пояс здания</FieldCaption><Input aria-label="Часовой пояс здания" required value={zone} onChange={e => setZone(e.target.value)}/></label></fieldset>{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}<Button variant="secondary" type="submit" disabled={busy}>Создать здание</Button></form></details>;
}
