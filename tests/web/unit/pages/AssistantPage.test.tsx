import {beforeEach,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {AssistantPage} from '@/pages/AssistantPage';
import {assistantApi as api,type ChatCapabilities,type ChatView} from '@/shared/api/assistant';
import {WorkspaceStateScope} from '@/shared/lib/workspaceState';
vi.mock('@/shared/session/SessionContext',()=>({useSession:()=>({profile:{userId:'TEST',siteId:'TEST-SITE',role:'chief_engineer'}})}));
const caps:ChatCapabilities={available:true,model_ref:'TEST',prompt_version:'TEST',agents:[{id:'assistant',title:'Ассистент',description:'Работа'},{id:'planner',title:'Планирование',description:'Планы'},{id:'photo',title:'Фотоанализ',description:'Фото'}],tools:{assistant:[],planner:[],photo:[]}};
const chat={conversation_id:'chat',title:'Мой диалог',agent:'assistant' as const,created_at:'2026-11-14',updated_at:'2026-11-14'};
const view:ChatView={conversation:chat,turns:[],total:0,actions:[]};
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(api,'capabilities').mockResolvedValue(caps);vi.spyOn(api,'list').mockResolvedValue({items:[chat],total:1});vi.spyOn(api,'read').mockResolvedValue(view);vi.spyOn(api,'send').mockResolvedValue({turn_id:'new',status:'running'});});
function show(path='/assistant?chat=chat'){return render(<WorkspaceStateScope.Provider value="TEST:TEST-SITE:chief_engineer"><MemoryRouter initialEntries={[path]}><AssistantPage/></MemoryRouter></WorkspaceStateScope.Provider>);}
it.each([true,false])('stages a dropped workbook without submitting (open chat: %s)',async(existing)=>{
  const user=userEvent.setup();
  const mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  const book=new File(['test'],'План.xlsx',{type:mime});
  const saved={attachment_id:'workbook',original_name:book.name,mime_type:mime,size_bytes:book.size,created_at:'2026-11-14',sha256:'a'.repeat(64)};
  const upload=vi.spyOn(api,'upload').mockResolvedValue(saved);
  if(!existing){
    vi.spyOn(api,'create').mockResolvedValue(chat);
    vi.mocked(api.read).mockResolvedValue({...view,pending_attachments:[saved]});
  }
  show(existing?'/assistant?chat=chat':'/assistant');
  const input=await screen.findByLabelText('Сообщение помощнику');
  await user.type(input,'Проверь план');
  const target=existing?screen.getByRole('region',{name:'Сообщения'}):screen.getByRole('heading',{name:'С чего начнём?'});
  const dataTransfer={types:['Files'],files:[book],dropEffect:'none'};
  fireEvent.dragEnter(target,{dataTransfer});
  expect(fireEvent.dragOver(target,{dataTransfer})).toBe(false);
  expect(fireEvent.drop(target,{dataTransfer})).toBe(false);
  const files=await screen.findByRole('list',{name:'Вложения к сообщению'});
  expect(within(files).getByRole('link',{name:'План.xlsx'})).toBeVisible();
  expect(upload).toHaveBeenCalledExactlyOnceWith('chat',book);
  expect(screen.getByLabelText('Сообщение помощнику')).toHaveValue('Проверь план');
  expect(api.send).not.toHaveBeenCalled();
});
it('does not intercept a drop of plain text into the composer',async()=>{
  const upload=vi.spyOn(api,'upload');
  show();
  const input=await screen.findByLabelText('Сообщение помощнику');
  const dataTransfer={types:['text/plain'],files:[]};
  expect(fireEvent.dragOver(input,{dataTransfer})).toBe(true);
  expect(fireEvent.drop(input,{dataTransfer})).toBe(true);
  expect(upload).not.toHaveBeenCalled();
});
it('clears the file drop hint when leaving the chat even if the drag data was cleared',async()=>{
  show();
  const zone=await screen.findByRole('region',{name:'Диалог с ИИ'});
  fireEvent.dragEnter(zone,{dataTransfer:{types:['Files'],files:[]}});
  expect(screen.getByText('Отпустите, чтобы прикрепить файлы')).toBeVisible();
  fireEvent.dragLeave(zone,{dataTransfer:{types:[],files:[]}});
  expect(screen.queryByText('Отпустите, чтобы прикрепить файлы')).not.toBeInTheDocument();
});
it.each(['drop','picker','new chat'] as const)('keeps nonalphabetic attachment order in the draft and send: %s',async(method)=>{
  const user=userEvent.setup();
  const mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  const batch=[new File(['z'],'Z.xlsx',{type:mime}),new File(['a'],'A.xlsx',{type:mime})];
  const staged=batch.map(file=>({attachment_id:file.name,original_name:file.name,mime_type:mime,
    size_bytes:file.size,created_at:'2026-11-24T11:00:00Z',sha256:'a'.repeat(64)}));
  const upload=vi.spyOn(api,'upload').mockResolvedValueOnce(staged[0]).mockResolvedValueOnce(staged[1]);
  if(method==='new chat'){
    vi.spyOn(api,'create').mockResolvedValue(chat);
    // These files have equal timestamps; the server's identifier tie-breaker is not selection order.
    vi.mocked(api.read).mockResolvedValue({...view,pending_attachments:staged});
  }
  show(method==='new chat'?'/assistant':'/assistant?chat=chat');
  await screen.findByLabelText('Сообщение помощнику');
  if(method==='picker'){
    fireEvent.change(screen.getByLabelText('Прикрепить файл'),{target:{files:batch}});
  }else{
    const zone=screen.getByRole('region',{name:method==='new chat'?'Новый чат':'Сообщения'});
    fireEvent.drop(zone,{dataTransfer:{types:['Files'],files:batch}});
  }
  await waitFor(()=>expect(upload).toHaveBeenCalledTimes(2));
  const files=await screen.findByRole('list',{name:'Вложения к сообщению'});
  await waitFor(()=>expect(within(files).getAllByRole('link').map(link=>link.textContent)).toEqual(['Z.xlsx','A.xlsx']));
  await user.click(screen.getByRole('button',{name:'Отправить'}));
  expect(api.send).toHaveBeenCalledExactlyOnceWith('chat','',expect.any(String),['Z.xlsx','A.xlsx']);
});
it('stages pasted screenshots without sending or changing the draft',async()=>{
  const user=userEvent.setup();
  const file=new File(['image'],'clipboard.png',{type:'image/png'});
  const upload=vi.spyOn(api,'upload').mockResolvedValue({attachment_id:'photo',original_name:'clipboard.png',mime_type:'image/png',size_bytes:5,created_at:'2026-11-14',sha256:'a'.repeat(64)});
  show();const input=await screen.findByLabelText('Сообщение помощнику');
  await user.type(input,'Проверь снимок');
  fireEvent.paste(input,{clipboardData:{files:[file]}});
  expect(await screen.findByRole('button',{name:'Открыть фото: clipboard.png'})).toBeVisible();
  expect(upload).toHaveBeenCalledWith('chat',file);
  expect(input).toHaveValue('Проверь снимок');
  expect(api.send).not.toHaveBeenCalled();
});
it('keeps text typed while the first screenshot uploads in a new chat',async()=>{
  const user=userEvent.setup();
  const photo={attachment_id:'photo',original_name:'clip.png',mime_type:'image/png',size_bytes:5,created_at:'2026-11-14',sha256:'a'.repeat(64)};
  vi.spyOn(api,'create').mockResolvedValue(chat);
  let finish!: (value:typeof photo)=>void;
  const upload=vi.spyOn(api,'upload').mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  vi.mocked(api.read).mockResolvedValue({...view,pending_attachments:[photo]});
  show('/assistant');
  const input=await screen.findByLabelText('Сообщение помощнику');
  fireEvent.paste(input,{clipboardData:{files:[new File(['image'],'clip.png',{type:'image/png'})]}});
  await waitFor(()=>expect(upload).toHaveBeenCalledOnce());
  await user.type(input,'Уточнение');
  finish(photo);
  await screen.findByRole('list',{name:'Вложения к сообщению'});
  expect(screen.getByLabelText('Сообщение помощнику')).toHaveValue('Уточнение');
  expect(api.send).not.toHaveBeenCalled();
});
it('opens a previously sent photo in the chat and returns focus on Escape',async()=>{
  const user=userEvent.setup();
  vi.mocked(api.read).mockResolvedValue({...view,total:1,turns:[{turn_id:'sent',content:'Фото до работы',answer:'Получено',status:'completed',error_code:null,trace:[],created_at:'2026-11-14T08:15:00Z',model_ref:null,attachments:[{attachment_id:'photo',original_name:'до.png',mime_type:'image/png',size_bytes:5,created_at:'2026-11-14',sha256:'a'.repeat(64)}]}]});
  show();
  const thumbnail=await screen.findByRole('button',{name:'Открыть фото: до.png'});
  await user.click(thumbnail);
  const preview=within(screen.getByRole('dialog',{name:'до.png'})).getByRole('img',{name:'до.png'});
  expect(preview).toHaveAttribute('src','/api/v1/assistant/attachments/photo');
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(thumbnail).toHaveFocus();
});
it('resumes the saved task with a stable source and keeps the composer draft',async()=>{
  const user=userEvent.setup();
  vi.mocked(api.read).mockResolvedValue({...view,total:1,turns:[{turn_id:'saved-task',content:'Проверь два пункта',answer:'Первый проверен',status:'completed',error_code:null,trace:[],created_at:'2026-11-14T08:15:00Z',model_ref:null,workflow:{outcome:'partial',goals:[{id:'done',title:'Первый пункт',status:'completed'},{id:'pending',title:'Второй пункт',status:'blocked'}]}}]});
  show();const input=await screen.findByLabelText('Сообщение помощнику');await user.type(input,'Другой черновик');
  await user.click(screen.getByRole('button',{name:'Продолжить поручение'}));
  await waitFor(()=>expect(api.send).toHaveBeenCalledWith('chat','Продолжить сохранённое поручение.',expect.any(String),[],undefined,'saved-task'));
  expect(input).toHaveValue('Другой черновик');expect(screen.getByText(/Поручение не завершено/)).toBeVisible();
});
it('keeps a finished reply distinct from an unconfirmed business task',async()=>{
  vi.mocked(api.read).mockResolvedValue({...view,total:1,turns:[{turn_id:'awaiting',content:'Подготовь изменение',answer:'Карточка подготовлена',status:'completed',error_code:null,trace:[],created_at:'2026-11-14T08:15:00Z',finished_at:'2026-11-14T08:16:05Z',model_ref:null,workflow:{outcome:'awaiting_confirmation',goals:[{id:'change',title:'Изменение оборудования',status:'awaiting_confirmation',action_id:'action'}]}}]});
  show();expect(await screen.findByText(/Поручение ожидает подтверждения/)).toBeVisible();
  expect(screen.getByText('Ответ завершён за 1 минуту 5 секунд')).toBeVisible();
  expect(screen.queryByText('Поручение выполнено')).not.toBeInTheDocument();
});
it('keeps the draft while changing model and sends the saved preference revision',async()=>{
  const user=userEvent.setup();
  vi.mocked(api.capabilities).mockResolvedValue({...caps,model_preference:{selection:{provider:'aitunnel',model:'cloud-test'},revision:7,is_default:false,available:true}});
  vi.spyOn(api,'models').mockResolvedValue({providers:[{id:'ollama',name:'Локальные',status:'ready',error_code:null,models:[{id:'local-test',name:'local-test',description:'Установлена локально',selectable:true}]}]});
  vi.spyOn(api,'selectModel').mockResolvedValue({selection:{provider:'ollama',model:'local-test',digest:'sha256:fixture'},revision:8,is_default:false,available:true});
  show();const input=await screen.findByLabelText('Сообщение помощнику');await user.type(input,'Мой запрос');
  await user.click(screen.getByRole('button',{name:'Выбрать модель: cloud-test'}));
  await user.click(await screen.findByRole('button',{name:/local-test/}));
  expect(input).toHaveValue('Мой запрос');
  expect(await screen.findByRole('button',{name:'Выбрать модель: local-test'})).toBeVisible();
  await user.click(screen.getByRole('button',{name:'Отправить'}));
  await waitFor(()=>expect(api.send).toHaveBeenCalledWith('chat','Мой запрос',expect.any(String),[],8));
});
it('retains the composer when opening a new chat and returning through right-hand history',async()=>{
  const user=userEvent.setup();show();const input=await screen.findByLabelText('Сообщение помощнику');await user.type(input,'Сохранённый вопрос');
  await user.click(screen.getAllByRole('button',{name:/Новый чат/})[0]);await user.click(screen.getByRole('button',{name:/^Мой диалог/}));
  expect(await screen.findByLabelText('Сообщение помощнику')).toHaveValue('Сохранённый вопрос');
});
it('stops the active response without sending a new message',async()=>{
  const user=userEvent.setup();const stop=vi.spyOn(api,'stop').mockResolvedValue({stopped:true});
  vi.mocked(api.read).mockResolvedValue({...view,turns:[{turn_id:'running',content:'Вопрос',answer:'',status:'running',error_code:null,trace:[],created_at:'2026-11-14T08:15:00Z',model_ref:null}],total:1});show();
  await user.click(await screen.findByRole('button',{name:'Остановить ответ'}));await waitFor(()=>expect(stop).toHaveBeenCalledWith('chat','running'));expect(api.send).not.toHaveBeenCalled();
});
it('requires confirmation before deleting a chat',async()=>{
  const user=userEvent.setup();const remove=vi.spyOn(api,'remove').mockResolvedValue({deleted:true});show();
  await user.click(await screen.findByRole('button',{name:'Удалить чат Мой диалог'}));expect(remove).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Отмена'}));expect(remove).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Удалить чат Мой диалог'}));await user.click(screen.getByRole('button',{name:'Удалить чат'}));
  await waitFor(()=>expect(remove).toHaveBeenCalledWith('chat'));
});
it('opens a blank composer without creating a conversation and always starts the unified agent',async()=>{
  const user=userEvent.setup();vi.spyOn(api,'create').mockResolvedValue(chat);show('/assistant');
  const input=await screen.findByLabelText('Сообщение помощнику');expect(api.create).not.toHaveBeenCalled();expect(api.read).not.toHaveBeenCalled();
  expect(screen.queryByRole('button',{name:'Фотоанализ'})).not.toBeInTheDocument();
  await user.type(input,'Первая задача');await user.keyboard('{Enter}');await waitFor(()=>expect(api.send).toHaveBeenCalled());expect(api.create).toHaveBeenCalledWith('assistant');
});
it('shows server activity and local timestamps without exposing an unfinished answer',async()=>{
  const user=userEvent.setup();
  const turn={turn_id:'t',content:'Проверь назначение',answer:'INTERNAL PARTIAL',status:'running' as const,error_code:null,trace:[{tool:'assignment_preview',status:'running'}],created_at:'2026-11-14T08:15:00Z',model_ref:null};
  vi.mocked(api.read).mockResolvedValue({...view,turns:[turn],total:1});show();
  expect(await screen.findByText(/Проверяю состав бригады, допуски и время/)).toHaveAttribute('role','status');expect(screen.queryByText('INTERNAL PARTIAL')).not.toBeInTheDocument();
  const details=screen.getByText(/Проверяю состав бригады/).closest('details')!;expect(details).toHaveAttribute('open');
  await user.click(details.querySelector('summary')!);expect(details).not.toHaveAttribute('open');
  await user.click(details.querySelector('summary')!);expect(details).toHaveAttribute('open');
  const timestamps=screen.getAllByText(/13:15/,{selector:'time'});
  expect(timestamps).toHaveLength(2);
  timestamps.forEach(time=>expect(time).toHaveAttribute('datetime',turn.created_at));
});
it('collapses distinct progress stages and keeps the completed duration after reload',async()=>{
  const user=userEvent.setup();
  const turn={turn_id:'t',content:'Проверь',answer:'Готово',status:'completed' as const,error_code:null,trace:[{tool:'tasks_find',status:'completed'},{tool:'tasks_list',status:'completed'},{tool:'tasks_find',status:'completed'},{tool:'staff_find',status:'denied'}],created_at:'2026-11-14T08:15:00Z',finished_at:'2026-11-14T08:16:05Z',model_ref:null};
  vi.mocked(api.read).mockResolvedValue({...view,turns:[turn],total:1});show();
    const toggle=await screen.findByLabelText('Время выполнения: 1 мин 5 сек');expect(toggle).toHaveTextContent('Ответ завершён за 1 минуту 5 секунд');
  expect(toggle.closest('details')).not.toHaveAttribute('open');
  await user.click(toggle);expect(screen.getAllByText('Ищу подходящие задания и ближайшее ТО')).toHaveLength(1);
  await user.click(toggle);expect(toggle.closest('details')).not.toHaveAttribute('open');
});
it('updates the elapsed time while the assistant is running',async()=>{
  const turn={turn_id:'t',content:'Проверь',answer:'',status:'running' as const,error_code:null,trace:[],created_at:new Date().toISOString(),model_ref:null};
  vi.mocked(api.read).mockResolvedValue({...view,turns:[turn],total:1});show();
  expect(await screen.findByLabelText('Время выполнения: 0 мин 0 сек')).toBeInTheDocument();
  await waitFor(()=>expect(screen.getByLabelText('Время выполнения: 0 мин 1 сек')).toBeInTheDocument(),{timeout:2500});
});
it('explains actual search results and distinguishes reasons an action failed',async()=>{
  const user=userEvent.setup();
  const turn={turn_id:'t',content:'Проверь',answer:'Результат',status:'completed' as const,error_code:null,trace:[{tool:'tasks_find',status:'completed',fact:{total:30,shown:25}},{tool:'task_assign',status:'denied',code:404},{tool:'staff_find',status:'denied',code:403}],created_at:'2026-11-14T08:15:00Z',finished_at:'2026-11-14T08:16:05Z',model_ref:null};
  vi.mocked(api.read).mockResolvedValue({...view,turns:[turn],total:1});show();
  await user.click(await screen.findByLabelText('Время выполнения: 1 мин 5 сек'));
  expect(screen.getByText(/по условиям найдено 30, проверено на странице: 25/)).toBeVisible();
  expect(screen.getByText(/указанная запись не найдена/)).toBeVisible();
  expect(screen.getByText(/доступ к этому действию ограничен/)).toBeVisible();
});
it('keeps technical error codes available only after opening details',async()=>{
  const user=userEvent.setup();
  const turn={turn_id:'failed',content:'Вопрос',answer:'Не удалось ответить.',status:'failed' as const,error_code:'OLLAMA_TIMEOUT',trace:[],created_at:'2026-11-14T08:15:00Z',finished_at:'2026-11-14T08:16:05Z',model_ref:null};
  vi.mocked(api.read).mockResolvedValue({...view,turns:[turn],total:1});show();
  const toggle=await screen.findByText('Технические сведения');
  expect(toggle.closest('details')).not.toHaveAttribute('open');
  await user.click(toggle);expect(screen.getByText('Код: OLLAMA_TIMEOUT')).toBeVisible();
});
it('retries a lost first-send response without creating another conversation or request key',async()=>{
  const user=userEvent.setup();vi.spyOn(api,'create').mockResolvedValue(chat);vi.mocked(api.send).mockRejectedValue(new Error('Соединение потеряно'));show('/assistant');
  await user.type(await screen.findByLabelText('Сообщение помощнику'),'Первая задача');
  await user.click(screen.getByRole('button',{name:'Отправить'}));await screen.findByRole('alert');await user.click(screen.getByRole('button',{name:'Отправить'}));
  await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(2));expect(api.create).toHaveBeenCalledTimes(1);expect(vi.mocked(api.send).mock.calls[0][2]).toBe(vi.mocked(api.send).mock.calls[1][2]);
});
it('keeps text and idempotency key on a failed send',async()=>{
  const user=userEvent.setup();vi.mocked(api.send).mockRejectedValue(new Error('Соединение потеряно'));show();
  await user.type(await screen.findByLabelText('Сообщение помощнику'),'Мой запрос');await user.click(screen.getByRole('button',{name:'Отправить'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Соединение потеряно');expect(screen.getByLabelText('Сообщение помощнику')).toHaveValue('Мой запрос');
  await user.click(screen.getByRole('button',{name:'Отправить'}));await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.send).mock.calls[0][2]).toBe(vi.mocked(api.send).mock.calls[1][2]);
});
it('shows provider unavailability and disables sending',async()=>{
  vi.mocked(api.capabilities).mockResolvedValue({...caps,available:false});show();
  await screen.findByLabelText('Сообщение помощнику');expect(screen.getByRole('button',{name:'Отправить'})).toBeDisabled();expect(screen.getByText(/ИИ пока не подключён/)).toBeVisible();
});
it('stages a selected file without importing or sending a chat message',async()=>{
  const user=userEvent.setup();vi.spyOn(api,'upload').mockResolvedValue({attachment_id:'file',original_name:'TEST.xlsx',mime_type:'application/octet-stream',size_bytes:12,sha256:'TEST',created_at:'2026-11-14'});
  show();await screen.findByLabelText('Сообщение помощнику');const file=new File(['PK TEST ONLY'],'TEST.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
  await user.upload(screen.getByLabelText('Прикрепить файл'),file);expect(api.upload).toHaveBeenCalledWith('chat',file);expect(api.send).not.toHaveBeenCalled();
});
it('uses a new turn key when the user repeats an already accepted message',async()=>{
  const user=userEvent.setup();show();
  for(let i=0;i<2;i++){const input=await screen.findByLabelText('Сообщение помощнику');await user.type(input,'Повторяемый запрос');await user.click(screen.getByRole('button',{name:'Отправить'}));await waitFor(()=>expect(input).toHaveValue(''));}
  expect(api.send).toHaveBeenCalledTimes(2);expect(vi.mocked(api.send).mock.calls[0][2]).not.toBe(vi.mocked(api.send).mock.calls[1][2]);
});

const file={attachment_id:'file',original_name:'TEST.xlsx',mime_type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',size_bytes:12,sha256:'TEST',created_at:'2026-11-14'};
it('places the chat history and toggle button on the left, collapses history, retains the draft and restores the scoped preference',async()=>{
  const user=userEvent.setup(),first=show();
  await user.type(await screen.findByLabelText('Сообщение помощнику'),'Не потеряй текст');
  const history=screen.getByRole('complementary',{name:'История диалогов'});
  const regions=screen.getByRole('region',{name:'Диалог с ИИ'});
  expect(history.compareDocumentPosition(regions)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const toggle=screen.getByRole('button',{name:'Свернуть историю чатов'});
  const nav=screen.getByRole('navigation',{name:'Разделы помощника'});
  expect(toggle.compareDocumentPosition(nav)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await user.click(toggle);
  expect(screen.queryByRole('complementary',{name:'История диалогов'})).not.toBeInTheDocument();
  expect(screen.getByLabelText('Сообщение помощнику')).toHaveValue('Не потеряй текст');
  first.unmount();show();
  const expand=await screen.findByRole('button',{name:'Развернуть историю чатов'});
  expect(expand).toHaveAttribute('aria-expanded','false');await user.click(expand);
  expect(screen.getByRole('complementary',{name:'История диалогов'})).toBeVisible();
});
it('sends an uploaded file without requiring text and clears only the submitted selection',async()=>{
  const user=userEvent.setup();vi.spyOn(api,'upload').mockResolvedValue(file);show();
  await user.upload(await screen.findByLabelText('Прикрепить файл'),new File(['TEST ONLY'],'TEST.xlsx',{type:file.mime_type}));
  expect(api.send).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Отправить'})).toBeEnabled();
  expect(screen.queryByText(/Enter — отправить/)).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Отправить'}));
  await waitFor(()=>expect(api.send).toHaveBeenCalledWith('chat','',expect.any(String),['file']));
  await waitFor(()=>expect(screen.queryByRole('list',{name:'Вложения к сообщению'})).not.toBeInTheDocument());
  expect(screen.getByRole('button',{name:'Отправить'})).toBeDisabled();
});
it('carries a file from the welcome screen into a file-only message',async()=>{
  const user=userEvent.setup();vi.spyOn(api,'create').mockResolvedValue(chat);vi.spyOn(api,'upload').mockResolvedValue(file);
  vi.mocked(api.read).mockResolvedValue({...view,attachments:[file],pending_attachments:[file]});show('/assistant');
  await user.upload(await screen.findByLabelText('Прикрепить файл'),new File(['TEST ONLY'],'TEST.xlsx',{type:file.mime_type}));
  await screen.findByRole('list',{name:'Вложения к сообщению'});expect(api.create).toHaveBeenCalledTimes(1);expect(api.send).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Отправить'}));
  await waitFor(()=>expect(api.send).toHaveBeenCalledWith('chat','',expect.any(String),['file']));
});
it('keeps files and the same request key after a failed file-only send',async()=>{
  const user=userEvent.setup();vi.spyOn(api,'upload').mockResolvedValue(file);vi.mocked(api.send).mockRejectedValue(new Error('Соединение потеряно'));show();
  await user.upload(await screen.findByLabelText('Прикрепить файл'),new File(['TEST ONLY'],'TEST.xlsx',{type:file.mime_type}));
  await user.click(screen.getByRole('button',{name:'Отправить'}));await screen.findByRole('alert');
  await user.click(screen.getByRole('button',{name:'Отправить'}));await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.send).mock.calls[0]).toEqual(vi.mocked(api.send).mock.calls[1]);
  expect(screen.getByRole('list',{name:'Вложения к сообщению'})).toHaveTextContent('TEST.xlsx');
});
it('does not attach files from previous messages to a new text-only message',async()=>{
  const user=userEvent.setup();vi.mocked(api.read).mockResolvedValue({...view,attachments:[file],pending_attachments:[]});show();
  await user.type(await screen.findByLabelText('Сообщение помощнику'),'Другой вопрос');await user.click(screen.getByRole('button',{name:'Отправить'}));
  await waitFor(()=>expect(api.send).toHaveBeenCalledWith('chat','Другой вопрос',expect.any(String),[]));
});
