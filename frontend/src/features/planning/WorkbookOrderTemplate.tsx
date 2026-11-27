import { useState } from 'react';
import { workbooks } from '@/shared/api/workbooks';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { Input } from '@/shared/ui/Form';
import { ErrorState, LoadingState } from '@/shared/ui/States';

export const ORDER_SHEET = 'Изменения нарядов';
const headers = 'Наряд\tНачало\tПлан, чел.-ч\tПримечание';
const PAGE = 25;

export function WorkbookOrderTemplate({timezone}: {timezone:string}) {
  const [input,setInput] = useState(''), [search,setSearch] = useState(''), [offset,setOffset] = useState(0);
  const [notice,setNotice] = useState(''), [manual,setManual] = useState('');
  const list=useApiQuery(()=>workbooks.issuedOrders(search,offset),[search,offset],undefined,`workbook-issued:${JSON.stringify([search,offset])}`);
  async function copy(text:string, message:string) {
    setManual('');
    try {await navigator.clipboard.writeText(text);setNotice(message);}
    catch {setNotice('Браузер не дал доступ к буферу. Выделите и скопируйте заготовку вручную.');setManual(text);}
  }
  return <section className="space-y-2 border-t border-line p-3" aria-label="Заготовка строки для наряда">
    <p className="text-sm text-muted">Добавьте лист <strong>«{ORDER_SHEET}»</strong>. Заголовки вставьте в A1, наряд — в свободную строку колонки A. Заполните только нужные поля.</p>
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="secondary" onClick={()=>void copy(headers,'Заголовки скопированы. Вставьте их в A1.')}>Скопировать заголовки</Button>
      <form className="flex flex-wrap gap-2" onSubmit={event=>{event.preventDefault();setOffset(0);setSearch(input.trim());}}>
        <Input aria-label="Номер, название работы или оборудование" placeholder="Номер, работа или оборудование" value={input} maxLength={120} onChange={event=>setInput(event.target.value)}/>
        <Button type="submit" variant="secondary">Найти выпущенный наряд</Button>
      </form>
    </div>
    {notice&&<p role="status" className="text-sm">{notice}</p>}
    {manual&&<textarea readOnly aria-label="Заготовка для ручного копирования" value={manual} className="block w-full rounded-lg border border-line p-2 text-sm" onFocus={event=>event.target.select()}/>}
    {list.status==='loading'&&<LoadingState/>}
    {list.status==='error'&&<ErrorState description={list.error}/>}
    {list.status==='success'&&<>{list.data.items.length===0?<p className="text-sm text-muted">Подходящих выпущенных нарядов нет.</p>:
      <ul className="max-h-[24dvh] space-y-1 overflow-auto" aria-label="Выпущенные наряды">
        {list.data.items.map(task=><li key={task.task_id} className="flex flex-wrap items-center justify-between gap-2 border-b border-line py-1">
          <span className="min-w-0 break-words text-sm"><strong>{task.title||'Наряд ТО'}</strong> · {task.task_id.slice(0,8)}{task.asset_code&&` · ${task.asset_code}`}
            {task.planned_start_at&&` · ${new Date(task.planned_start_at).toLocaleDateString('ru-RU',{timeZone:timezone})}`}</span>
          <Button variant="secondary" aria-label={`Скопировать строку наряда ${task.task_id.slice(0,8)}`} onClick={()=>void copy(task.task_id,'Строка скопирована. Вставьте её в свободную ячейку колонки A.')}>Скопировать строку</Button>
        </li>)}
      </ul>}
      {(offset>0||list.data.has_more)&&<nav className="flex gap-2" aria-label="Страницы выпущенных нарядов">
        <Button variant="secondary" disabled={!offset} onClick={()=>setOffset(value=>value-PAGE)}>Назад</Button>
        <Button variant="secondary" disabled={!list.data.has_more} onClick={()=>setOffset(value=>value+PAGE)}>Далее</Button>
      </nav>}
    </>}
  </section>;
}
