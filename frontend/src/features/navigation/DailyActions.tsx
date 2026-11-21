import { Link } from 'react-router-dom';
import { useSession } from '@/shared/session/SessionContext';
import { canOpenSection } from '@/shared/lib/roles';
import { Icon, type IconName } from '@/shared/ui/Icon';

export function DailyActions() {
  const {profile}=useSession();
  const director=profile?.role==='director',admin=profile?.role==='admin';
  if (!director && !admin) return null;
  const choices:{to:string;title:string;description:string;icon:IconName;section:string}[]=admin?[
    {to:'/equipment',title:'Подготовить оборудование',description:'Реестр, инженерные системы и регламенты.',icon:'equipment',section:'equipment'},
    {to:'/settings/workforce',title:'Настроить команду',description:'Сотрудники, доступы, смены и допуски.',icon:'workforce',section:'workforce_settings'},
  ]:[
    {to:'/tasks?status=overdue',title:'Проверить отклонения',description:'Просроченные задания и их состояние.',icon:'tasks',section:'tasks'},
    {to:'/calendar',title:'Посмотреть план',description:'Даты работ и выполнение по объекту.',icon:'calendar',section:'calendar'},
    {to:'/reports',title:'Оценить результаты',description:'Трудозатраты, качество и отчётность.',icon:'report',section:'reports'},
  ];
  return <nav className="journey-launches" aria-label="Основные задачи">{choices.filter(item=>canOpenSection(profile?.role,item.section)).map(item=><Link key={item.to} className="journey-launch" to={item.to}><Icon name={item.icon} size={21}/><div><strong>{item.title}</strong><p>{item.description}</p></div></Link>)}</nav>;
}
