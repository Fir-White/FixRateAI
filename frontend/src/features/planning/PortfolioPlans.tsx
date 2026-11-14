import { useRef,useState } from 'react';
import { draftPlansApi,type DraftRecord,type DraftPolicy } from '@/shared/api/draftPlans';
import { portfolioPlansApi as api,type PortfolioPreview } from '@/shared/api/portfolioPlans';
import type { RequirementsRequest } from '@/shared/api/requirements';
import type { CatalogWorkspace } from '@/features/equipment/CatalogImports';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { Input,Textarea,FieldCaption } from '@/shared/ui/Form';
import { LoadingState,ErrorState } from '@/shared/ui/States';
import { Callout } from '@/shared/ui/Callout';
import { PlanningPages } from './PlanningChoices';
import { SavedPlan } from './CatalogPlans';
import { newPolicy,PolicyFields } from './PolicyFields';

export function PortfolioPlans({workspace,timezone,mayEdit,mayApprove=false}:{workspace:CatalogWorkspace;timezone:string;mayEdit:boolean;mayApprove?:boolean}) {
  const [offset,setOffset]=useState(0);
  const query=useApiQuery(()=>api.list(offset),[offset],undefined,`portfolio-plans:${offset}`);
  if(workspace.draftId)return <section className="space-y-4" aria-label="Общий сохранённый план"><Button variant="ghost" onClick={()=>workspace.selectDraft(null)}>← Все общие планы</Button><LinkedPortfolio workspace={workspace} timezone={timezone} mayEdit={mayEdit} mayApprove={mayApprove}/></section>;
  return <section className="space-y-3" aria-label="Сохранённые общие планы"><h2 className="text-lg font-semibold">Сохранённые общие планы</h2>{query.status==='loading'&&<LoadingState/>}{query.status==='error'&&<ErrorState description={query.error}/>}{query.status==='success'&&<><ul className="space-y-2">{query.data.items.map(x=><li key={x.draft_id}><Button variant="secondary" className="max-w-full whitespace-normal break-words text-left" onClick={()=>workspace.selectDraft(x)}>{x.title} · версия {x.revision} · {x.total_person_hours} чел.-ч</Button></li>)}</ul>{!query.data.total&&<p className="text-sm text-muted">Сохранённых общих планов пока нет. Рассчитайте состав ниже и сохраните новый черновик.</p>}<PlanningPages offset={offset} total={query.data.total} onPage={setOffset}/></>}</section>;
}

function LinkedPortfolio({workspace,timezone,mayEdit,mayApprove=false}:{workspace:CatalogWorkspace;timezone:string;mayEdit:boolean;mayApprove?:boolean}) {
  const query=useApiQuery(async()=>{
    const versions=await draftPlansApi.versions(workspace.draftId,0),head=versions.items[0];
    if(!head||head.source_kind!=='portfolio')throw new Error('Общий план не найден. Вернитесь к списку.');
    const record=workspace.draftRevision&&workspace.draftRevision!==head.revision?(await draftPlansApi.overview(workspace.draftId,workspace.draftRevision)).record:head;
    return {record,head:head.revision};
  },[workspace.draftId,workspace.draftRevision],undefined,`linked-portfolio:${workspace.draftId}:${workspace.draftRevision}`);
  if(query.status==='loading')return <LoadingState label="Открытие общего плана"/>;
  if(query.status==='error')return <ErrorState description={query.error}/>;
  return <SavedPlan key={`${query.data.record.draft_id}:${query.data.record.revision}`} record={query.data.record} timezone={timezone} mayEdit={mayEdit&&query.data.record.revision===query.data.head} mayApprove={mayApprove} onSaved={workspace.selectDraft} onPickVersion={workspace.selectDraft} workspace={workspace}/>;
}

export function SavePortfolio({requirements,timezone,onSaved}:{requirements:RequirementsRequest;timezone:string;onSaved:(r:DraftRecord)=>void}) {
  const [policy,setPolicy]=useState<DraftPolicy>(()=>({...newPolicy(),day_start_minute:requirements.catalog?.policy.day_start_minute??null,night_start_minute:requirements.catalog?.policy.night_start_minute??null}));
  const [title,setTitle]=useState('Общий план ТО'),[reason,setReason]=useState(''),[preview,setPreview]=useState<PortfolioPreview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const key=useRef(crypto.randomUUID());
  const input={kind:'portfolio' as const,requirements,policy};
  return <section className="space-y-3 rounded-xl border border-line p-4" aria-label="Сохранение общего состава"><h3 className="font-semibold">Сохранить общий состав в план</h3><p className="text-sm text-muted">В новую версию войдут только новые работы всего выбранного состава. Поиск и страница списка не ограничивают план. Выданные и принятые задания сохраняются в сведениях об источнике.</p>
    <fieldset disabled={busy} className="min-w-0 space-y-4"><details><summary>Условия расчёта: полезное время и доступ</summary><div className="mt-3"><PolicyFields value={policy} timezone={timezone} onChange={p=>{setPolicy(p);setPreview(null);key.current=crypto.randomUUID();}}/></div></details><p className="text-sm">Неизвестные условия можно уточнить в сохранённом плане. Размещение требует подтверждённых условий и реальных смен сотрудников.</p>
      <Button variant="secondary" onClick={async()=>{setBusy(true);setError('');setPreview(null);try{setPreview(await api.preview(input));key.current=crypto.randomUUID();}catch(e){setError(e instanceof Error?e.message:'Не удалось проверить общий план');}finally{setBusy(false);}}}>Проверить общий черновик</Button>
      {preview&&<div className="space-y-3"><p>{preview.total_occurrences} новых работ · {preview.total_person_hours} чел.-ч. Уже выдано или принято: {preview.excluded_occurrences}.</p><ul className="space-y-2 text-sm">{preview.issues.map((x,i)=><li key={i}>{x.message}</li>)}</ul>{preview.total_issues>preview.issues.length&&<p>Показаны первые {preview.issues.length} из {preview.total_issues} замечаний. Полный состав замечаний доступен выше.</p>}
        <label className="block"><FieldCaption>Название общего плана</FieldCaption><Input aria-label="Название общего плана" maxLength={256} value={title} onChange={e=>{setTitle(e.target.value);key.current=crypto.randomUUID();}}/></label><label className="block"><FieldCaption>Основание общего плана</FieldCaption><Textarea aria-label="Основание общего плана" maxLength={2000} value={reason} onChange={e=>{setReason(e.target.value);key.current=crypto.randomUUID();}}/></label>
        <Button disabled={!preview.can_save||!title.trim()||!reason.trim()} onClick={async()=>{setBusy(true);setError('');try{onSaved(await api.create(input,preview.input_sha256,key.current,title,reason));}catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить общий план');}finally{setBusy(false);}}}>Сохранить общий план</Button>
      </div>}
    </fieldset>{error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}
  </section>;
}
