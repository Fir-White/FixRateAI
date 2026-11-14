import { lazy,Suspense } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CatalogImports, type CatalogWorkspace } from '@/features/equipment/CatalogImports';
import { useSession } from '@/shared/session/SessionContext';
import { DEMO_MODE } from '@/shared/api/request';
import { PageHeader } from '@/shared/ui/PageHeader';
import { Callout } from '@/shared/ui/Callout';
import { buttonClassName } from '@/shared/ui/Button';
import { canOpenSection } from '@/shared/lib/roles';
import { JourneySteps } from '@/shared/ui/JourneySteps';
import { LoadingState } from '@/shared/ui/States';
const RequirementsPanel=lazy(()=>import('@/features/planning/RequirementsPanel'));

export function PlanningPage() {
  const {profile}=useSession(),[params,setParams]=useSearchParams();
  const mayImport=['chief_engineer','admin','dispatcher'].includes(profile?.role??'');
  const update=(values:Record<string,string|null>)=>setParams(previous=>{const next=new URLSearchParams(previous);for(const [key,value] of Object.entries(values)){if(value)next.set(key,value);else next.delete(key);}return next;});
  const workspace:CatalogWorkspace={
    catalogId:params.get('catalog')??'',stage:params.get('stage')==='plan'?'plan':'prepare',
    draftId:params.get('draft')??'',draftRevision:Number(params.get('revision'))||null,
    planView:params.get('view')??'work',
    selectCatalog:id=>update({catalog:id,stage:null,draft:null,revision:null,view:null}),
    selectStage:stage=>update({stage}),
    selectDraft:record=>update({draft:record?.draft_id??null,revision:record?String(record.revision):null}),
    selectPlanView:view=>update({view}),
  };
  const portfolioWorkspace:CatalogWorkspace={...workspace,catalogId:'',draftId:params.get('portfolio')??'',draftRevision:Number(params.get('portfolio_revision'))||null,planView:params.get('portfolio_view')??'work',
    selectDraft:record=>update({portfolio:record?.draft_id??null,portfolio_revision:record?String(record.revision):null}),
    selectPlanView:view=>update({portfolio_view:view}),
  };
  return <div className="space-y-6"><PageHeader title="Планирование ТО" description="Проверьте обязательные работы по регламентам или подготовьте план из сохранённого Excel."/>
    {DEMO_MODE?<Callout>Планы из Excel доступны при подключении к рабочему серверу.{canOpenSection(profile?.role,'calendar')&&<> В демонстрационном режиме можно посмотреть <Link className="text-accent underline" to="/calendar">пример календаря</Link>.</>}</Callout>:<JourneySteps key={`${profile?.siteId}:${profile?.role}`} label="Представления планирования" numbered={false} value={params.get('mode')==='requirements'?'requirements':'catalog'} onChange={id=>update({mode:id==='requirements'?'requirements':null})} steps={[
      {id:'catalog',title:'Планы из Excel',content:()=> <CatalogImports mayImport={mayImport} mayConfirm={profile?.role==='chief_engineer'} mayPlan={mayImport} siteName={profile?.siteName} timezone={profile?.timezone} workspace={workspace}/>},
      {id:'requirements',title:'Общий состав обязательств',content:()=> <Suspense fallback={<LoadingState/>}><RequirementsPanel mayApprove={profile?.role==='chief_engineer'} mayEdit={mayImport} workspace={portfolioWorkspace} timezone={profile?.timezone??'UTC'} catalogId={params.get('requirements_catalog')??''} initialStart={params.get('requirements_start')??undefined} initialEnd={params.get('requirements_end')??undefined} mayConfigure={canOpenSection(profile?.role,'service_settings')} mayViewTasks={canOpenSection(profile?.role,'tasks')} onCatalog={id=>update({requirements_catalog:id})} onCalculate={(start,end)=>update({requirements_start:start,requirements_end:end})} onPrepare={()=>update({mode:null,catalog:params.get('requirements_catalog'),stage:'prepare',draft:null,revision:null,view:null})}/></Suspense>},
    ]}/>}
    <div className="journey-context-links"><Link to="/equipment">Проверить оборудование →</Link>{canOpenSection(profile?.role,'workforce_settings')&&<Link to="/settings/workforce">Проверить сотрудников и смены →</Link>}{canOpenSection(profile?.role,'calendar')&&<Link to="/calendar" className={buttonClassName('ghost')}>Открыть действующий календарь</Link>}</div>
  </div>;
}
