import { useRef, useState } from 'react';
import { registryApi, type ExcelPreview } from '@/shared/api/registry';
import { Button } from '@/shared/ui/Button';
import { FileInput } from '@/shared/ui/FileInput';
import { Card } from '@/shared/ui/Card';
import { Callout } from '@/shared/ui/Callout';

const actions: Record<string,string> = {create:'Добавить',update:'Обновить',unchanged:'Без изменений',needs_confirmation:'Требует уточнения'};
export function RegistryExcel({mayImport,onSaved}: {mayImport:boolean;onSaved:()=>void}) {
  const [file,setFile]=useState<File|null>(null);const [preview,setPreview]=useState<ExcelPreview|null>(null);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
  // A new selection invalidates an in-flight preview, even before React re-renders.
  const version=useRef(0);
  const download=async(template:boolean)=>{setError('');try{await registryApi.downloadExcel(template);}catch(error){setError(error instanceof Error?error.message:'Ошибка выгрузки');}};
  return <Card className="space-y-4 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Excel</h2><div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={()=>void download(false)}>Экспорт реестра</Button>{mayImport&&<Button variant="ghost" onClick={()=>void download(true)}>Скачать шаблон</Button>}</div></div>
    {mayImport&&<details><summary className="cursor-pointer text-sm text-accent">Импортировать оборудование, работы и детали</summary><div className="mt-4 space-y-4"><p className="text-sm text-muted">Сначала проверьте файл. Ошибки нужно исправить до сохранения. Изменённые регламенты сохраняются черновиками; история деталей остаётся доступной.</p>
      <FileInput accept=".xlsx" aria-label="Excel реестра" disabled={busy} onChange={event=>{version.current++;setFile(event.target.files?.[0]??null);setPreview(null);setError('');setNotice('');}}/>
      <Button variant="secondary" disabled={busy||!file} onClick={async()=>{if(!file||busy)return;const current=version.current;setBusy(true);setError('');setPreview(null);try{const result=await registryApi.previewExcel(file);if(current===version.current)setPreview(result);}catch(error){setError(error instanceof Error?error.message:'Ошибка чтения Excel');}finally{setBusy(false);}}}>{busy?'Обработка…':'Проверить файл'}</Button>
      {preview&&<div className="space-y-3" aria-label="Предпросмотр импорта">{preview.warnings.map((warning,index)=><Callout key={index}>{warning}</Callout>)}{preview.errors.length>0&&<Callout tone="danger"><p>Импорт заблокирован: исправьте ошибки.</p><ul>{preview.errors.map((row,index)=><li key={index}>{row.sheet}, строка {row.row}: {row.message}</li>)}</ul></Callout>}
        <p className="text-sm">Строк в предпросмотре: {preview.rows.length}</p><div className="registry-scroll"><table className="registry-table" aria-label="Предпросмотр Excel"><thead><tr><th>Лист и строка</th><th>Изменение</th><th>Запись</th></tr></thead><tbody>{preview.rows.map((row,index)=><tr key={index}><td>{row.sheet} · {row.row}</td><td>{actions[row.action]??row.action}</td><td>{row.label}{row.changes?.map((change,i)=><small key={i}>{change}</small>)}</td></tr>)}</tbody></table></div>
        <Button disabled={busy||!preview.can_import||!file} onClick={async()=>{if(!file||busy||!preview.can_import)return;setBusy(true);setError('');try{const result=await registryApi.importExcel(file,preview.preview_token);setNotice(`Импорт завершён. Сохранено: ${result.imported}, без изменений: ${result.unchanged}.`);setPreview(null);onSaved();}catch(error){setPreview(null);setError(error instanceof Error?error.message:'Ошибка импорта');}finally{setBusy(false);}}}>Сохранить проверенные изменения</Button>
      </div>}
    </div></details>}{error&&<p role="alert"><Callout tone="danger">{error}</Callout></p>}{notice&&<p role="status"><Callout tone="success">{notice}</Callout></p>}
  </Card>;
}
