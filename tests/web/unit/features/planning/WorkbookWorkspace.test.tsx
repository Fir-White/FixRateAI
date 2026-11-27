// @vitest-environment-options {"url":"http://127.0.0.1:8000"}
import { act, fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, expect, test, vi } from 'vitest';

const fakes = vi.hoisted(() => ({
  details: vi.fn(), versions: vi.fn(), start: vi.fn(), snapshot: vi.fn(), commit: vi.fn(),
  orderRows: vi.fn(), orderPreview: vi.fn(), orderApply: vi.fn(), fromCatalog: vi.fn(),
}));
vi.mock('@/shared/api/workbooks', () => ({
  workbooks: {...fakes, download: () => '/test/original.xlsx'},
}));
vi.mock('@/shared/api/request',async importOriginal=>({
  ...await importOriginal<typeof import('@/shared/api/request')>(),DEMO_MODE:false,
}));
vi.mock('@/shared/session/SessionContext',()=>({
  useSession:()=>({profile:{role:'chief_engineer',userId:'chief',siteId:'site',timezone:'UTC',
    workbookEditorOrigin:'http://localhost:8092'}}),
}));
import { WorkbookWorkspace } from '@/features/planning/WorkbookWorkspace';
import { PlanningPage } from '@/pages/PlanningPage';
import { catalogImportsApi } from '@/shared/api/catalogImports';

const book = {book_id:'book', version:1, filename:'Два листа.xlsx', created_at:'2026-11-27T09:00:00Z'};
const select = vi.fn();
beforeEach(() => {
  vi.restoreAllMocks();
  vi.resetAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  fakes.details.mockResolvedValue(book);
  fakes.versions.mockResolvedValue({items:[book],total:1});
});

test('opens Excel inside the selected file row and starts the latest version',async()=>{
  vi.spyOn(catalogImportsApi,'list').mockResolvedValue({items:[{
    import_id:'draft',filename:'Два листа.xlsx',source_sha256:'a'.repeat(64),parser_version:'test',
    status:'draft',created_at:book.created_at,summary:{operation_count:2, group_count:1,
      top_level_group_count:1,maintenance_types:{},empty_duration_count:0,mark_count:0,
      readiness_counts:{},ready_count:0,ready_for_real_plan:false,issue_count:0},
  }],total:1});
  let finish!: (value: typeof book)=>void;
  fakes.fromCatalog.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  fakes.start.mockResolvedValue({api_url:'http://localhost:8092/api.js',document_config:{},session_id:'session'});
  const router=createMemoryRouter([{path:'/planning',element:<PlanningPage/>}],{initialEntries:['/planning']});
  render(<RouterProvider router={router}/>);
  const file=await screen.findByRole('button',{name:/Два листа.xlsx/});
  fireEvent.pointerEnter(file);
  await screen.findByTitle('Локальный редактор Excel',{}, {timeout:5000});
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fakes.fromCatalog).not.toHaveBeenCalled();
  expect(fakes.start).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Регламент и план'})).toBeVisible();
  fireEvent.click(file);
  const editor=await screen.findByRole('region',{name:/Редактор Excel/}, {timeout:5000});
  expect(file.closest('li')).toContainElement(editor);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fakes.fromCatalog).toHaveBeenCalledWith('draft',expect.any(AbortSignal));
  expect(fakes.start).not.toHaveBeenCalled();
  await act(async()=>finish({...book,version:3}));
  expect(fakes.start).toHaveBeenCalledWith('book',3,expect.any(AbortSignal));
  expect(screen.getByTitle('Локальный редактор Excel')).toBeInTheDocument();
  expect(router.state.location.search).toBe('');
});
function mount() {
  const router=createMemoryRouter([{path:'*',element:<WorkbookWorkspace bookId="book" version={1} mayEdit timezone="UTC" onSelect={select} onCatalog={vi.fn()}/> }]);
  render(<RouterProvider router={router}/>);
  return router;
}
async function editorEvent(event: string, fields: object = {}, origin='http://localhost:8092') {
  await screen.findByRole('dialog');
  const frame=await screen.findByTitle<HTMLIFrameElement>('Локальный редактор Excel');
  fireEvent(window,new MessageEvent('message',{origin,source:frame.contentWindow,data:{bridge:'fixrate-office',event,...fields}}));
}

test('shows download when editor is offline', async () => {
  fakes.start.mockRejectedValue(new Error('Локальный редактор Excel не настроен.'));
  mount();
  fireEvent.click(await screen.findByRole('button',{name:'Редактировать книгу'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('не настроен');
  expect(screen.getByRole('link',{name:'Скачать XLSX'})).toHaveAttribute('href','/test/original.xlsx');
});

test('waits for persisted version before showing success', async () => {
  fakes.start.mockResolvedValue({api_url:'http://localhost:8092/api.js',document_config:{},session_id:'session'});
  fakes.snapshot.mockImplementation(async (_book,_session,request_id)=>({
    state:'ready',snapshot_sha256:'abc',snapshot_request_id:request_id,
  }));
  let saved!: (value: typeof book) => void;
  fakes.commit.mockImplementation(() => new Promise(resolve => {saved = resolve;}));
  mount();
  fireEvent.click(await screen.findByRole('button',{name:'Редактировать книгу'}));
  await editorEvent('ready',{},'http://127.0.0.1:8000');
  expect(screen.getByRole('button',{name:'Сохранить новую версию'})).toBeDisabled();
  await editorEvent('ready');
  const save = await screen.findByRole('button',{name:'Сохранить новую версию'});
  fireEvent.click(save);
  await vi.waitFor(() => expect(fakes.commit).toHaveBeenCalledTimes(1));
  expect(select).not.toHaveBeenCalled();
  saved({...book,version:2});
  expect(await screen.findByText(/Версия 2 сохранена/)).toBeVisible();
  expect(select).toHaveBeenCalledWith('book',2);
});

test('resumes the previous capture before accepting any new edits',async()=>{
  fakes.start.mockResolvedValue({api_url:'http://localhost:8092/api.js',document_config:{},session_id:'session',
    state:'ready',snapshot_request_id:'existing-request'});
  fakes.snapshot.mockResolvedValue({state:'ready',snapshot_sha256:'abc',snapshot_request_id:'existing-request'});
  fakes.commit.mockResolvedValue({...book,version:2});
  mount();
  fireEvent.click(await screen.findByRole('button',{name:'Редактировать книгу'}));
  const resume=await screen.findByRole('button',{name:'Завершить сохранение'});
  expect(screen.getByTitle('Локальный редактор Excel')).toHaveAttribute('inert');
  fireEvent.click(resume);
  await vi.waitFor(()=>expect(fakes.snapshot).toHaveBeenCalledWith('book','session','existing-request'));
  expect(await screen.findByText(/Версия 2 сохранена/)).toBeVisible();
});

test('does not discard unsaved workbook edits on Back', async()=>{
  fakes.start.mockResolvedValue({api_url:'http://localhost:8092/api.js',document_config:{},session_id:'session'});
  const router=mount();
  await act(()=>router.navigate('/planning'));
  fireEvent.click(await screen.findByRole('button',{name:'Редактировать книгу'}));
  await editorEvent('ready');
  await editorEvent('sync',{syncing:true});
  await editorEvent('sync',{syncing:false});
  const confirm=vi.spyOn(window,'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
  await act(()=>router.navigate(-1));
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(router.state.location.pathname).toBe('/planning');
  expect(screen.getByRole('dialog')).toBeVisible();
  await act(()=>router.navigate(-1));
  expect(router.state.location.pathname).toBe('/');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  confirm.mockRestore();
});

test('finds an issued order by title from the saved workbook and asks for confirmation',async()=>{
  fakes.orderRows.mockResolvedValue({items:[{row_number:4,title:'Проверка вентиляции',task_id:'12345678-1234-1234-1234-123456789012',issue:null}],total:1,has_sheet:true});
  fakes.orderPreview.mockResolvedValue({can_apply:true,requires_assigned_confirmation:true,preview_digest:'digest',
    items:[{action:'reschedule',title:'Проверка вентиляции',task_id:'12345678-1234-1234-1234-123456789012',
      before_start:'2027-01-02T09:00',planned_start:'2027-01-02T10:00',worker_names:['Дежурный техник'],due_date:'2027-01-02'}]});
  fakes.orderApply.mockResolvedValue({items:[{task_id:'12345678-1234-1234-1234-123456789012',revision:2}]});
  mount();
  const details=(await screen.findByText('Применить к выпущенному наряду',{exact:true})).closest('details')!;
  details.open=true;
  fireEvent(details,new Event('toggle'));
  expect(await screen.findByRole('option',{name:/Проверка вентиляции.*строка 4/})).toBeVisible();
  fireEvent.change(screen.getByRole('textbox',{name:'Основание правки'}),{target:{value:'Подтверждён перенос'}});
  fireEvent.click(screen.getByRole('button',{name:'Проверить изменения наряда'}));
  expect(fakes.orderPreview).toHaveBeenCalledWith('book',1,{row_number:4,reason:'Подтверждён перенос'});
  const apply=await screen.findByRole('button',{name:'Подтвердить и применить к наряду'});
  expect(apply).toBeDisabled();
  expect(fakes.orderApply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox',{name:/Подтверждаю перенос/}));
  fireEvent.click(apply);
  expect(await screen.findByRole('link',{name:'Открыть этот наряд'})).toHaveAttribute('href','/tasks/12345678-1234-1234-1234-123456789012');
});
