import { NavLink, useLocation } from 'react-router-dom';
import { useSession } from '@/shared/session/SessionContext';
import { canOpenSection } from '@/shared/lib/roles';
import { useApiQueryCache } from '@/shared/lib/ApiQueryProvider';
import { warmWorkspacePath } from '@/features/navigation/warmWorkspacePath';
import './journeys.css';

/** Related screens stay discoverable without giving every tool a sidebar entry. */
export function SectionNavigation() {
  const {profile}=useSession(),{pathname}=useLocation(),cache=useApiQueryCache();
  const planning=['/planning','/calendar','/comparisons'].some(path=>pathname===path||pathname.startsWith(path+'/'));
  const equipment=pathname==='/equipment'||pathname.startsWith('/equipment/')||pathname==='/settings/equipment';
  const links=planning&&canOpenSection(profile?.role,'planning') ? [
    {to:'/planning',label:'Планы из Excel',section:'planning'},
    {to:'/calendar',label:'Действующий календарь',section:'calendar'},
    {to:'/comparisons',label:'AI-прогнозы',section:'comparisons'},
  ] : equipment&&profile?.role!=='executor' ? [
    {to:'/equipment',label:'Реестр оборудования',section:'equipment'},
    {to:'/settings/equipment',label:'Оборудование и регламенты',section:'service_settings'},
  ] : [];
  if(!links.length)return null;
  return <nav className="journey-section-nav" aria-label={planning?'Разделы планирования':'Разделы оборудования'}>{links.filter(link=>canOpenSection(profile?.role,link.section)).map(link=><NavLink key={link.to} to={link.to} onMouseEnter={()=>warmWorkspacePath(cache,link.to,profile?.timezone??'UTC')} onFocus={()=>warmWorkspacePath(cache,link.to,profile?.timezone??'UTC')}>{link.label}</NavLink>)}</nav>;
}
