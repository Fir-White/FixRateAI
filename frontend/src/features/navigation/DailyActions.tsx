import { Link } from 'react-router-dom';
import { useSession } from '@/shared/session/SessionContext';
import { canOpenSection } from '@/shared/lib/roles';
import { Icon, type IconName } from '@/shared/ui/Icon';

export function DailyActions() {
  const {profile}=useSession();
  const director=profile?.role==='director',admin=profile?.role==='admin';
  const choices:{to:string;title:string;description:string;icon:IconName;section:string}[]=admin?[
    {to:'/equipment',title:'Подготовить оборудование',description:'Реестр, инженерные системы и регламенты.',icon:'equipment',section:'equipment'},
    {to:'/settings/workforce',title:'Настроить команду',description:'Сотрудники, доступы, смены и допуски.',icon:'workforce',section:'workforce_settings'},
  ]:director?[
    {to:'/tasks?status=overdue',title:'Проверить отклонения',description:'Просроченные задания и их состояние.',icon:'tasks',section:'tasks'},
    {to:'/calendar',title:'Посмотреть план',description:'Даты работ и выполнение по объекту.',icon:'calendar',section:'calendar'},
    {to:'/reports',title:'Оценить результаты',description:'Трудозатраты, качество и отчётность.',icon:'report',section:'reports'},
  ]:[
    {to:'/tasks?status=attention',title:'Разобрать очередь',description:'Просрочки, назначения и работы без исполнителя.',icon:'tasks',section:'tasks'},
    {to:'/quality',title:'Принять выполненные работы',description:'Отчёты техников, фотографии и результат AI.',icon:'quality',section:'quality'},
    {to:'/planning',title:profile?.role==='engineer'?'Проверить план ТО':'Подготовить план ТО',description:'Excel → состав работ → даты и бригады → выпуск.',icon:'calendar',section:'planning'},
  ];
  return <nav className="journey-launches" aria-label="Основные задачи">{choices.filter(item=>canOpenSection(profile?.role,item.section)).map(item=><Link key={item.to} className="journey-launch" to={item.to}><Icon name={item.icon} size={21}/><div><strong>{item.title}</strong><p>{item.description}</p></div></Link>)}</nav>;
}
