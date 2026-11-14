import {useRef,useState} from 'react';
import {draftPlansApi as api,type DraftRecord} from '@/shared/api/draftPlans';
import {useApiQuery} from '@/shared/lib/useApiQuery';
import {Button} from '@/shared/ui/Button';
import {FieldCaption,Textarea} from '@/shared/ui/Form';
import {LoadingState,ErrorState} from '@/shared/ui/States';
import {Callout} from '@/shared/ui/Callout';

export default function UndoPlanPanel({record,onSaved}:{record:DraftRecord;onSaved:(r:DraftRecord)=>void}) {
  const query=useApiQuery(()=>api.undoView(record.draft_id,record.revision),[record.draft_id,record.revision]);
  const [reason,setReason]=useState(''),[consent,setConsent]=useState(false),[unlock,setUnlock]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const attempt=useRef({signature:'',key:crypto.randomUUID()});
  if(query.status==='loading')return <LoadingState label="Проверка возможности отмены"/>;
  if(query.status==='error')return <ErrorState description={query.error}/>;
  const choice=query.data;
  return <section className="space-y-3 rounded-xl border border-line p-4" aria-label="Отмена собственного изменения"><h3 className="font-semibold">Отменить последнее своё изменение</h3><Callout>{choice.explanation}</Callout>
    {choice.can_undo&&<fieldset disabled={busy} className="min-w-0 space-y-3"><p className="text-sm">Изменение версии {record.revision} будет отменено. Содержимое версии {choice.restores_revision} вернётся в новой версии {record.revision+1} после проверки текущих ограничений.</p>
      <label className="block"><FieldCaption>Причина отмены изменения</FieldCaption><Textarea aria-label="Причина отмены изменения" maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)}/></label>
      {choice.requires_unlock&&<label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={unlock} onChange={e=>setUnlock(e.target.checked)}/>Разрешаю отменить изменённые закрепления сегментов</label>}
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>Подтверждаю восстановление предыдущего состояния новой версией</label>
      <Button disabled={!reason.trim()||!consent||(choice.requires_unlock&&!unlock)} onClick={async()=>{setBusy(true);setError('');const signature=JSON.stringify({reason,unlock});if(attempt.current.signature!==signature)attempt.current={signature,key:crypto.randomUUID()};try{onSaved(await api.undo(record.draft_id,{expected_revision:record.revision,idempotency_key:attempt.current.key,reason,unlock}));}catch(e){setError(e instanceof Error?e.message:'Не удалось отменить изменение');}finally{setBusy(false);}}}>Отменить изменение новой версией</Button>
    </fieldset>}{error&&<div role="alert"><Callout tone="danger">{error}</Callout><p className="text-sm">Причина сохранена. При конфликте откройте актуальную версию из истории.</p></div>}
  </section>;
}
