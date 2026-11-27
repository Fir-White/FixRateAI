import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { workbooks, type OrderPreview, type WorkbookVersion } from '@/shared/api/workbooks';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { Callout } from '@/shared/ui/Callout';
import { FieldCaption, Input, Select } from '@/shared/ui/Form';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { ORDER_SHEET } from './WorkbookOrderTemplate';

export function WorkbookOrderChanges({book, timezone}: {book: WorkbookVersion; timezone: string}) {
  const [opened,setOpened] = useState(false);
  return <details className="fr-rule-section" onToggle={event=>{if(event.currentTarget.open) setOpened(true);}}>
    <summary>Применить к выпущенному наряду</summary>
    {opened&&<OrderReview book={book} timezone={timezone}/>}
  </details>;
}

function OrderReview({book, timezone}: {book: WorkbookVersion; timezone: string}) {
  const [row,setRow] = useState<number|null>(null), [reason,setReason] = useState('');
  const [offset,setOffset] = useState(0), [refresh,reload] = useState(0);
  const [review,setReview] = useState<{preview:OrderPreview;key:string}|null>(null);
  const [confirmed,setConfirmed] = useState(false), [busy,setBusy] = useState(false);
  const [error,setError] = useState(''), [applied,setApplied] = useState('');
  const change=review?.preview.items[0];
  const rows=useApiQuery(()=>workbooks.orderRows(book.book_id,book.version,offset),[book.book_id,book.version,offset,refresh],undefined,`workbook-order-rows:${book.book_id}:${book.version}:${offset}`);
  const data=rows.data;
  const valid=data?.items.filter(item=>!item.issue)??[];
  const selected=valid.find(item=>item.row_number===row)??valid[0];
  const body={row_number:selected?.row_number??0,reason:reason.trim()};

  function reset() {setReview(null);setConfirmed(false);setError('');setApplied('');}
  async function preview(event:FormEvent) {
    event.preventDefault();
    if (!selected || !body.reason) return;
    reset();setBusy(true);
    try {
      const result=await workbooks.orderPreview(book.book_id,book.version,body);
      setReview({preview:result,key:crypto.randomUUID()});
    } catch (reason) {setError(reason instanceof Error?reason.message:'Не удалось проверить изменения.');}
    finally {setBusy(false);}
  }
  async function apply() {
    const digest=review?.preview.preview_digest;
    if (!review?.preview.can_apply||!digest||(review.preview.requires_assigned_confirmation&&!confirmed)) return;
    setBusy(true);setError('');
    try {
      const result=await workbooks.orderApply(book.book_id,book.version,{
        ...body,preview_digest:digest,idempotency_key:review.key,confirm_assigned:confirmed,
      });
      setApplied(result.items[0].task_id);setReview(null);setConfirmed(false);
    } catch (reason) {setError(reason instanceof Error?reason.message:'Не удалось применить изменение.');}
    finally {setBusy(false);}
  }
  const window = (start: string|null, end: string|null) => `${start?.replace('T',' ')??'—'} → ${end?.replace('T',' ')??'—'}`;
  return <div className="space-y-4 p-4">
      <p className="text-sm text-muted">FixRate читает лист «{ORDER_SHEET}» из версии {book.version}. Пустые ячейки не меняют данные; «—» очищает примечание. Время — по часовому поясу объекта ({timezone}).</p>
      {rows.status==='loading'&&<LoadingState/>}
      {rows.status==='error'&&<ErrorState description={rows.error} action={<Button onClick={()=>reload(value=>value+1)}>Повторить</Button>}/>}
      {data?.issue&&<Callout tone="warning">{data.issue}</Callout>}
      {data&&!data.issue&&!data.total&&<Callout>В этой версии нет строк правок. Откройте последнюю версию на редактирование и выберите «Правки наряда», чтобы скопировать заготовку.</Callout>}
      {!!data?.total&&<ul className="space-y-1 text-sm" aria-label="Строки, которые нужно исправить">
        {data.items.filter(item=>item.issue).map(item=><li key={item.row_number}>Строка {item.row_number}{item.title&&` · ${item.title}`}: {item.issue}</li>)}
      </ul>}
      {!!data&&data.total>25&&<nav className="flex flex-wrap gap-2" aria-label="Страницы строк правок">
        <Button variant="secondary" disabled={busy||offset===0} onClick={()=>{setOffset(offset-25);reset();}}>Предыдущие строки</Button>
        <Button variant="secondary" disabled={busy||offset+25>=data.total} onClick={()=>{setOffset(offset+25);reset();}}>Следующие строки</Button>
      </nav>}
      {selected&&<form className="space-y-3" onSubmit={preview}>
        <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2">
          <label><FieldCaption>Наряд из сохранённой книги</FieldCaption><Select value={selected.row_number} onChange={event=>{setRow(Number(event.target.value));reset();}}>
            {valid.map(item=><option key={item.row_number} value={item.row_number}>{item.title||'Наряд ТО'} · {item.task_id?.slice(0,8)} · строка {item.row_number}</option>)}
          </Select></label>
          <label><FieldCaption>Основание правки</FieldCaption><Input required maxLength={1000} value={reason} onChange={event=>{setReason(event.target.value);reset();}}/></label>
        </fieldset>
        <Button type="submit" variant="secondary" disabled={busy||!body.reason}>Проверить изменения наряда</Button>
      </form>}
      {error&&<p role="alert"><Callout tone="danger">{error}</Callout></p>}
      {applied&&<p role="status">Наряд обновлён. <Link to={`/tasks/${applied}`} className="text-accent underline">Открыть этот наряд</Link></p>}
      {change?.action==='blocked'&&<Callout tone="warning">{change.issue}</Callout>}
      {change&&change.action!=='blocked'&&<section aria-label="Изменения выпущенного наряда" className="space-y-3 border-t border-line pt-4">
        <h3 className="font-semibold">{change.title}{change.equipment&&` · ${change.equipment}`}</h3>
        <Link to={`/tasks/${change.task_id}`} target="_blank" rel="noreferrer" className="text-accent underline">Сверить наряд</Link>
        <dl className="space-y-2 text-sm">
          <div><dt>Плановое окно ({timezone})</dt><dd>{window(change.before_start,change.before_end)} → {window(change.planned_start,change.planned_end)}</dd></div>
          <div><dt>План, чел.-ч</dt><dd>{change.before_hours??'—'} → {change.planned_person_hours??'—'}</dd></div>
          <div><dt>Примечание</dt><dd className="break-words whitespace-pre-wrap">{change.before_note||'—'} → {change.note||'—'}</dd></div>
          <div><dt>Обязательный срок не меняется</dt><dd>{change.due_date}</dd></div>
        </dl>
        {review?.preview.requires_assigned_confirmation&&<label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={confirmed} disabled={busy} onChange={event=>setConfirmed(event.target.checked)}/>
          Подтверждаю перенос и уведомление прежних исполнителей: {change.worker_names.join(', ')}
        </label>}
        <Button disabled={busy||!review?.preview.can_apply||!!review.preview.requires_assigned_confirmation&&!confirmed} onClick={()=>void apply()}>Подтвердить и применить к наряду</Button>
      </section>}
    </div>;
}
