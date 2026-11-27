import { lazy,Suspense,useCallback,useEffect,useRef,useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { CatalogImports, type CatalogWorkspace } from '@/features/equipment/CatalogImports';
import { useSession } from '@/shared/session/SessionContext';
import { DEMO_MODE } from '@/shared/api/request';
import { PageHeader } from '@/shared/ui/PageHeader';
import { Callout } from '@/shared/ui/Callout';
import { canOpenSection,hasPermission } from '@/shared/lib/roles';
import { JourneySteps } from '@/shared/ui/JourneySteps';
import { LoadingState } from '@/shared/ui/States';
import { localEditorOrigin } from '@/features/planning/officeOrigin';
const RequirementsPanel=lazy(()=>import('@/features/planning/RequirementsPanel'));
const OrderTable=lazy(()=>import('@/features/planning/OrderTable').then(module=>({default:module.OrderTable})));
const WorkbookWorkspace=lazy(()=>import('@/features/planning/WorkbookWorkspace').then(module=>({default:module.WorkbookWorkspace})));
const loadCatalogEditor=()=>import('@/features/planning/WorkbookEditor');
const CatalogWorkbookEditor=lazy(()=>loadCatalogEditor().then(module=>({default:module.CatalogWorkbookEditor})));

function currentMonth(timeZone:string){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit'}).formatToParts();
  return `${parts.find(part=>part.type==='year')?.value}-${parts.find(part=>part.type==='month')?.value}`;
}

export function PlanningPage() {
  const {profile}=useSession(),[params,setParams]=useSearchParams();
  const {key:locationKey}=useLocation();
  const [target,setTarget]=useState<{catalog:string;opener:HTMLButtonElement;scope:string;locationKey:string;request?:number}>();
  const requestId=useRef(0);
  const [primed,setPrimed]=useState(false),[generation,setGeneration]=useState(0);
  const [saved,setSaved]=useState<{book:string;version:number;scope:string}>();
  const mayEditPlan=hasPermission(profile,'edit_plan');
  const mayImport=profile?.permissionProfile==='mvp'?hasPermission(profile,'prepare_catalog'):mayEditPlan;
  const mayEditOrders=hasPermission(profile,'order_table');
  const mayApprove=hasPermission(profile,'approve_exception');
  const mayReadWorkbooks=profile?.role==='chief_engineer'||profile?.role==='engineer';
  const mayEditWorkbooks=hasPermission(profile,'edit_source_workbook');
  const mode=params.get('mode'),requestedMonth=params.get('order_month')??'';
  const activeMode=mode==='requirements'||(mode==='orders'&&mayEditOrders)||(mode==='workbooks'&&mayReadWorkbooks)?mode:'catalog';
  const scope=`${profile?.userId}:${profile?.siteId}:${profile?.role}`;
  const origin=profile?.workbookEditorOrigin;
  const warmEditor=useCallback(()=>{
    void loadCatalogEditor().catch(()=>undefined);
    if (localEditorOrigin(origin)&&!document.hidden) setPrimed(true);
  },[origin]);
  useEffect(()=>{
    if(DEMO_MODE||!mayEditWorkbooks||activeMode!=='catalog'||params.has('catalog')) return;
    if(typeof window.requestIdleCallback==='function') {
      const idle=window.requestIdleCallback(warmEditor,{timeout:800});
      return ()=>window.cancelIdleCallback(idle);
    }
    const timer=window.setTimeout(warmEditor,200);
    return ()=>window.clearTimeout(timer);
  },[activeMode,mayEditWorkbooks,params,warmEditor]);
  useEffect(()=>{
    setTarget(current=>current?.locationKey===locationKey&&current.scope===scope?current:undefined);
  },[locationKey,scope]);
  const retained=mayEditWorkbooks&&activeMode==='catalog'&&target?.scope===scope&&target.locationKey===locationKey?target:undefined;
  const opening=retained?.request===undefined?undefined:retained;
  useEffect(()=>{
    if (!retained||opening) return;
    const timeout=window.setTimeout(()=>{
      setTarget(undefined);
      setGeneration(value=>value+1);
    },60_000);
    return ()=>window.clearTimeout(timeout);
  },[retained,opening]);
  const openWorkbook=mayEditWorkbooks?(catalog:string,opener:HTMLButtonElement)=>{
    warmEditor();
    setTarget({catalog,opener,scope,locationKey,request:++requestId.current});
  }:undefined;
  const closeWorkbook=(keep=false)=>{
    if (keep) setTarget(current=>current&&{...current,request:undefined});
    else {
      setTarget(undefined);
      setGeneration(value=>value+1);
    }
  };
  const update=(values:Record<string,string|null>)=>setParams(previous=>{const next=new URLSearchParams(previous);for(const [key,value] of Object.entries(values)){if(value)next.set(key,value);else next.delete(key);}return next;});
  const workspace:CatalogWorkspace={
    catalogId:params.get('catalog')??'',stage:params.get('stage')==='plan'?'plan':'prepare',
    draftId:params.get('draft')??'',draftRevision:Number(params.get('revision'))||null,
    planView:params.get('view')??'work',
    selectCatalog:id=>update({catalog:id,stage:null,draft:null,revision:null,view:null}),
    selectStage:stage=>update({stage}),
    selectDraft:record=>update({draft:record?.draft_id??null,revision:record?String(record.revision):null}),
    selectPlanView:view=>update({view}),
    loadMonth:params.get('load_month')??'',selectLoadMonth:month=>update({load_month:month||null}),
  };
  const portfolioWorkspace:CatalogWorkspace={...workspace,catalogId:'',draftId:params.get('portfolio')??'',draftRevision:Number(params.get('portfolio_revision'))||null,planView:params.get('portfolio_view')??'work',
    selectDraft:record=>update({portfolio:record?.draft_id??null,portfolio_revision:record?String(record.revision):null}),
    selectPlanView:view=>update({portfolio_view:view}),
    loadMonth:params.get('portfolio_month')??'',selectLoadMonth:month=>update({portfolio_month:month||null}),
  };
  const renderWorkbookEditor=(catalog:string,filename:string)=><Suspense fallback={opening?<LoadingState/>:null}>
    <CatalogWorkbookEditor key={`${locationKey}:${scope}:${generation}`} catalog={catalog} filename={filename} origin={origin}
      request={opening?.catalog===catalog?opening.request:undefined}
      timezone={profile?.timezone??'UTC'} onClose={keep=>{closeWorkbook(keep);if(opening)requestAnimationFrame(()=>opening.opener.focus({preventScroll:true}));}}
      onSaved={book=>{
        closeWorkbook();
        setSaved({book:book.book_id,version:book.version,scope});
        update({mode:'workbooks',book:book.book_id,version:String(book.version),from_catalog:null});
      }}/>
  </Suspense>;
  return <div className="space-y-6"><PageHeader title="Планирование ТО" description="Проверьте обязательные работы по регламентам или подготовьте план из сохранённого Excel."/>
    {DEMO_MODE?<Callout>Планы из Excel доступны при подключении к рабочему серверу.{canOpenSection(profile?.role,'calendar')&&<> В демонстрационном режиме можно посмотреть <Link className="text-accent underline" to="/calendar">пример календаря</Link>.</>}</Callout>:<JourneySteps key={scope} label="Представления планирования" numbered={false} value={activeMode} onChange={id=>update({mode:id==='catalog'?null:id})} steps={[
      {id:'catalog',title:'Планы из Excel',content:()=> <CatalogImports mayImport={mayImport} mayConfirm={mayApprove} mayPlan={mayEditPlan} siteName={profile?.siteName} timezone={profile?.timezone} workspace={workspace} onOpenWorkbook={openWorkbook} onWarmWorkbook={mayEditWorkbooks?warmEditor:undefined} openWorkbookId={opening?.catalog} keptWorkbookId={retained?.catalog} primeWorkbook={mayEditWorkbooks&&activeMode==='catalog'&&primed} renderWorkbookEditor={renderWorkbookEditor}/>},
      {id:'requirements',title:'Общий состав обязательств',content:()=> <Suspense fallback={<LoadingState/>}><RequirementsPanel mayApprove={mayApprove} mayEdit={mayEditPlan} workspace={portfolioWorkspace} timezone={profile?.timezone??'UTC'} catalogId={params.get('requirements_catalog')??''} initialStart={params.get('requirements_start')??undefined} initialEnd={params.get('requirements_end')??undefined} mayConfigure={canOpenSection(profile?.role,'service_settings')} mayViewTasks={canOpenSection(profile?.role,'tasks')} onCatalog={id=>update({requirements_catalog:id})} onCalculate={(start,end)=>update({requirements_start:start,requirements_end:end})} onPrepare={()=>update({mode:null,catalog:params.get('requirements_catalog'),stage:'prepare',draft:null,revision:null,view:null})}/></Suspense>},
      ...(mayEditOrders?[{id:'orders',title:'Таблица нарядов ТО',content:()=> <Suspense fallback={<LoadingState/>}><OrderTable month={/^20[0-9]{2}-(0[1-9]|1[0-2])$/.test(requestedMonth)?requestedMonth:currentMonth(profile?.timezone??'UTC')} timezone={profile?.timezone??'UTC'} onMonth={month=>update({order_month:month})}/></Suspense>}]:[]),
      ...(mayReadWorkbooks?[{id:'workbooks',title:'Исходные книги Excel',content:()=> <Suspense fallback={<LoadingState/>}>
        {saved?.scope===scope&&saved.book===params.get('book')&&String(saved.version)===params.get('version')&&
          <p role="status">Версия {saved.version} сохранена. Оригинал не изменился. Если готовили правку наряда, откройте «Применить к выпущенному наряду».</p>}
        <WorkbookWorkspace bookId={params.get('book')??''} version={Number(params.get('version')??1)} fromCatalog={params.get('from_catalog')??undefined}
          timezone={profile?.timezone??'UTC'} mayEdit={mayEditWorkbooks}
          onSelect={(book,version)=>update({mode:'workbooks',book:book||null,version:version?String(version):null,from_catalog:null})}
          onCatalog={catalog=>update({mode:null,catalog,stage:'prepare',draft:null,revision:null,view:null})}/>
      </Suspense>}]:[]),
    ]}/>}
    <div className="journey-context-links"><Link to="/equipment">Проверить оборудование →</Link>{canOpenSection(profile?.role,'workforce_settings')&&<Link to="/settings/workforce">Проверить сотрудников и смены →</Link>}</div>
  </div>;
}
