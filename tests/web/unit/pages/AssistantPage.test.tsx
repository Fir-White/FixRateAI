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
it('retains the composer when switching specializations and returning to the saved conversation',async()=>{
  const user=userEvent.setup();show();const input=await screen.findByLabelText('Сообщение помощнику');await user.type(input,'Сохранённый вопрос');
  await user.click(screen.getByRole('button',{name:'Фотоанализ'}));await user.click(screen.getByRole('button',{name:/Мой диалог/}));
  expect(await screen.findByLabelText('Сообщение помощнику')).toHaveValue('Сохранённый вопрос');
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
