import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {AssistantPage} from '@/pages/AssistantPage';
import {assistantApi as api,type ChatCapabilities,type ChatView} from '@/shared/api/assistant';
vi.mock('@/shared/session/SessionContext',()=>({useSession:()=>({profile:{userId:'TEST',siteId:'TEST-SITE',role:'chief_engineer'}})}));
const caps:ChatCapabilities={available:true,model_ref:'TEST',prompt_version:'TEST',agents:[{id:'assistant',title:'Ассистент',description:'Работа'},{id:'planner',title:'Планирование',description:'Планы'},{id:'photo',title:'Фотоанализ',description:'Фото'}],tools:{assistant:[],planner:[],photo:[]}};
const chat={conversation_id:'chat',title:'Мой диалог',agent:'assistant' as const,created_at:'2026-11-14',updated_at:'2026-11-14'};
const view:ChatView={conversation:chat,turns:[],total:0,actions:[]};
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(api,'capabilities').mockResolvedValue(caps);vi.spyOn(api,'list').mockResolvedValue({items:[chat],total:1});vi.spyOn(api,'read').mockResolvedValue(view);vi.spyOn(api,'send').mockResolvedValue({turn_id:'new',status:'running'});});
function show(path='/assistant?chat=chat'){render(<MemoryRouter initialEntries={[path]}><AssistantPage/></MemoryRouter>);}
it('retains the composer when opening a new chat and returning through right-hand history',async()=>{
  const user=userEvent.setup();show();const input=await screen.findByLabelText('Сообщение помощнику');await user.type(input,'Сохранённый вопрос');
  await user.click(screen.getAllByRole('button',{name:/Новый чат/})[0]);await user.click(screen.getByRole('button',{name:/Мой диалог/}));
  expect(await screen.findByLabelText('Сообщение помощнику')).toHaveValue('Сохранённый вопрос');
});
it('opens a blank composer without creating a conversation and always starts the unified agent',async()=>{
  const user=userEvent.setup();vi.spyOn(api,'create').mockResolvedValue(chat);show('/assistant');
  const input=await screen.findByLabelText('Сообщение помощнику');expect(api.create).not.toHaveBeenCalled();expect(api.read).not.toHaveBeenCalled();
  expect(screen.queryByRole('button',{name:'Фотоанализ'})).not.toBeInTheDocument();
  await user.type(input,'Первая задача');await user.keyboard('{Enter}');await waitFor(()=>expect(api.send).toHaveBeenCalled());expect(api.create).toHaveBeenCalledWith('assistant');
});
it('shows server activity and local timestamps without exposing an unfinished answer',async()=>{
  const turn={turn_id:'t',content:'Проверь назначение',answer:'INTERNAL PARTIAL',status:'running' as const,error_code:null,trace:[{tool:'assignment_preview',status:'running'}],created_at:'2026-11-14T08:15:00Z',model_ref:null};
  vi.mocked(api.read).mockResolvedValue({...view,turns:[turn],total:1});show();
  expect(await screen.findByText(/Проверяю состав бригады, допуски и время/)).toHaveAttribute('role','status');expect(screen.queryByText('INTERNAL PARTIAL')).not.toBeInTheDocument();
  expect(screen.getByText(/13:15/,{selector:'time'})).toHaveAttribute('datetime',turn.created_at);
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
