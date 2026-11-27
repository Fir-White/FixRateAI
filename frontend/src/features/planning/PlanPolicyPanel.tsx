import { useRef,useState } from 'react';
import { draftPlansApi as api,type DraftPolicy,type DraftRecord } from '@/shared/api/draftPlans';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { FieldCaption,Textarea } from '@/shared/ui/Form';
import { LoadingState,ErrorState } from '@/shared/ui/States';
import { Callout } from '@/shared/ui/Callout';
import { PolicyFields,PolicySummary,reviewedPolicy } from './PolicyFields';

export default function PlanPolicyPanel({record,mayEdit,timezone,onSaved}:{record:DraftRecord;mayEdit:boolean;timezone:string;onSaved:(r:DraftRecord)=>void}) {
  const [open,setOpen]=useState(false),[retry,setRetry]=useState(0);
  const query=useApiQuery(()=>api.policy(record.draft_id,record.revision),[record.draft_id,record.revision,retry],undefined,`plan-policy:${record.draft_id}:${record.revision}`);
  return <section className="space-y-3 rounded-xl border border-line p-4" aria-label="Параметры расчёта и доступ объекта"><h3 className="font-semibold">Параметры расчёта и доступ объекта</h3>
    {query.status==='loading'&&<LoadingState/>}{query.status==='error'&&<><ErrorState description={query.error}/><Button variant="secondary" onClick={()=>setRetry(n=>n+1)}>Повторить загрузку параметров</Button></>}
    {query.status==='success'&&<><PolicySummary value={query.data.policy} timezone={timezone}/>{(query.data.policy.format_version!==2||query.data.policy.access_status!=='confirmed'||!query.data.policy.capacity_confirmed)&&<Callout>Уточните и подтвердите условия перед расчётом и выпуском. Неизвестные значения блокируют утверждение.</Callout>}
      {mayEdit&&<Button variant="secondary" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'Свернуть параметры':'Изменить условия расчёта'}</Button>}
      {mayEdit&&<div hidden={!open} inert={!open}><Editor record={record} policy={query.data.policy} timezone={timezone} onSaved={onSaved}/></div>}
    </>}
  </section>;
}

function Editor({record,policy,timezone,onSaved}:{record:DraftRecord;policy:DraftPolicy;timezone:string;onSaved:(r:DraftRecord)=>void}) {
  const [value,setValue]=useState(()=>reviewedPolicy(policy)),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const requestKey=useRef({signature:'',key:crypto.randomUUID()});
  const save=async()=>{if(busy)return;setBusy(true);setError('');const signature=JSON.stringify({value,reason});if(requestKey.current.signature!==signature)requestKey.current={signature,key:crypto.randomUUID()};try{onSaved(await api.changePolicy(record.draft_id,{expected_revision:record.revision,idempotency_key:requestKey.current.key,reason,policy:value}));}catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить параметры');}finally{setBusy(false);}};
  return <div className="space-y-3 border-t border-line pt-4"><p className="text-sm text-muted">Сохранение создаёт новую версию. Часы, бригады и ручные закрепления сохраняются; их соответствие новым условиям будет проверено заново. Действующие задания не изменяются.</p>
    <fieldset disabled={busy} className="min-w-0 space-y-4"><legend className="sr-only">Редактирование условий расчёта</legend><PolicyFields value={value} onChange={setValue} timezone={timezone}/>
      <label className="block"><FieldCaption>Причина изменения условий</FieldCaption><Textarea aria-label="Причина изменения условий" value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label>
      <Button disabled={!reason.trim()} onClick={()=>void save()}>{busy?'Сохранение…':'Сохранить условия новой версией'}</Button>
    </fieldset>{error&&<div role="alert" className="space-y-2"><Callout tone="danger">{error}</Callout><p className="text-sm">Введённые значения сохранены в форме. Если план изменён другим инженером, откройте актуальную версию перед повторным изменением.</p></div>}
  </div>;
}
