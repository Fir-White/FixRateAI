import { beforeEach,expect,it,vi } from 'vitest';
import { render,screen,waitFor,within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PublicationPanel from '@/features/planning/PublicationPanel';
import { publicationApi as api,type PublicationProposal } from '@/shared/api/publication';
import type { DraftRecord } from '@/shared/api/draftPlans';

const record={draft_id:'draft',revision:3} as DraftRecord;
const proposal=(state:PublicationProposal['state']='prepared'):PublicationProposal=>({proposal_id:'proposal',draft_id:'draft',base_revision:3,state,created_at:'2026-11-13T12:00:00Z',expires_at:'2026-11-13T12:30:00Z',reason:'Проверенный источник',scope_note:'Выбранная строка, январь 2027',proposal_digest:'a'.repeat(64),summary:{added_tasks:2,changed_tasks:0,cancelled_tasks:0,occurrences:1,segments:2,total_person_hours:'3',selected_rows:1,unselected_rows:216,months:['2027-01']},validation:{validator_version:'test',status:'valid',checked_at:'2026-11-13T12:00:00Z',input_sha256:'a',resource_sha256:'b',total_issues:0,issue_counts:{},issues:[],total_person_hours:'3',placed_person_hours:'3',unplaced_segments:0,days:[],ready_for_real_plan:false},blockers:[],blocker_count:0,can_approve:state==='prepared',decided_by:state==='prepared'?null:'chief',decision_reason:state==='prepared'?null:'Проверено',approval_token:state==='approved'?'token':null,publication_id:state==='published'?'publication':null,published_at:null});
beforeEach(()=>{
  vi.restoreAllMocks();vi.spyOn(api,'list').mockResolvedValue({items:[],total:0});vi.spyOn(api,'profiles').mockResolvedValue({items:[{row_number:209,code:'1.4',title:'Обслуживание фильтра',included_rows:[]}],total:1});
  vi.spyOn(api,'prepare').mockResolvedValue(proposal());vi.spyOn(api,'get').mockResolvedValue(proposal());vi.spyOn(api,'changes').mockResolvedValue({items:[],total:0,worker_labels:{},equipment_labels:{}});
  vi.spyOn(api,'approve').mockResolvedValue(proposal('approved'));vi.spyOn(api,'reject').mockResolvedValue(proposal('rejected'));vi.spyOn(api,'publish').mockResolvedValue(proposal('published'));
});
const mount=(chief=true)=>render(<PublicationPanel record={record} mayEdit mayApprove={chief} timezone="Asia/Yekaterinburg"/>);
async function opened(user:ReturnType<typeof userEvent.setup>,state:PublicationProposal['state']='prepared',chief=true){
  vi.mocked(api.list).mockResolvedValue({items:[proposal(state)],total:1});vi.mocked(api.get).mockResolvedValue(proposal(state));mount(chief);
  await user.click(await screen.findByRole('button',{name:/версия 3 ·/}));return screen.findByRole('region',{name:'Предложение публикации'});
}
it('does not prepare, approve or publish by opening the screen',async()=>{
  mount();await waitFor(()=>expect(api.list).toHaveBeenCalled());expect(api.prepare).not.toHaveBeenCalled();expect(api.approve).not.toHaveBeenCalled();expect(api.publish).not.toHaveBeenCalled();
});
it('requires human instructions and an exact explicit scope before saving a proposal',async()=>{
  const user=userEvent.setup();mount();await user.click(screen.getByRole('button',{name:'Подготовить предложение к публикации'}));
  await user.click(await screen.findByRole('button',{name:'1.4 · Обслуживание фильтра'}));
  await user.type(screen.getByLabelText('Инструкция выполнения'),'Выполнить согласованный регламент');await user.type(screen.getByLabelText('Меры безопасности'),'Согласованные меры безопасности');
  await user.type(screen.getByLabelText('Основание инструкции'),'Методика инженера');await user.type(screen.getByLabelText('Чек-лист: один пункт на строку'),'Первый пункт\nВторой пункт\n');
  await user.click(screen.getByText('Типы ответов и фотофиксация'));
  await user.selectOptions(screen.getByLabelText('Тип ответа, пункт 1'),'number');await user.type(screen.getByLabelText('Единица измерения, пункт 1'),'бар');
  await user.click(screen.getByRole('checkbox',{name:'Фото до и после, пункт 1'}));
  await user.type(screen.getByLabelText('Состав и границы публикации'),'Один фильтр, выбранный горизонт');await user.type(screen.getByLabelText('Основание предложения'),'Проверено');
  await user.click(screen.getByRole('button',{name:'Сохранить предложение на утверждение'}));
  await waitFor(()=>expect(api.prepare).toHaveBeenCalledTimes(1));const body=vi.mocked(api.prepare).mock.calls[0][1];
  expect(body.expected_revision).toBe(3);expect(body.profiles[0].checklist.map(c=>c.text)).toEqual(['Первый пункт','Второй пункт']);expect(api.publish).not.toHaveBeenCalled();
  expect(body.profiles[0].checklist[0]).toEqual(expect.objectContaining({answer_kind:'number',unit:'бар',photo_required:true}));
});
it('keeps approval and live publication separate and requires consent twice',async()=>{
  const user=userEvent.setup(),panel=await opened(user);expect(within(panel).getByRole('button',{name:'Утвердить предложение'})).toBeDisabled();
  await user.type(within(panel).getByLabelText('Основание решения главного инженера'),'Проверено ограничение и состав');
  await user.click(within(panel).getByRole('checkbox',{name:'Проверены выбранный состав, ограничения, инструкции, чек-листы и назначения'}));
  await user.click(within(panel).getByRole('button',{name:'Утвердить предложение'}));
  await waitFor(()=>expect(api.approve).toHaveBeenCalledTimes(1));expect(api.publish).not.toHaveBeenCalled();
  expect(await within(panel).findByRole('button',{name:'Опубликовать утверждённый план'})).toBeDisabled();
  await user.click(within(panel).getByRole('checkbox',{name:'Создать утверждённые задания и назначения в рабочем календаре и уведомить исполнителей'}));
  await user.click(within(panel).getByRole('button',{name:'Опубликовать утверждённый план'}));
  await waitFor(()=>expect(api.publish).toHaveBeenCalledWith('proposal','a'.repeat(64),'token',expect.any(String)));
  expect(await within(panel).findByRole('status',{name:'Состояние предложения'})).toHaveTextContent('Опубликовано');
});
it('does not expose chief decisions to a preparation-only role',async()=>{
  const user=userEvent.setup(),panel=await opened(user,'prepared',false);expect(within(panel).queryByRole('button',{name:'Утвердить предложение'})).not.toBeInTheDocument();expect(panel).toHaveTextContent('доступны главному инженеру');
});
it('preserves the decision reason on stale failure and does not publish automatically',async()=>{
  vi.mocked(api.approve).mockRejectedValue(new Error('PLAN_STALE: доступность изменилась'));const user=userEvent.setup(),panel=await opened(user);
  await user.type(within(panel).getByLabelText('Основание решения главного инженера'),'Моё решение');await user.click(within(panel).getByRole('checkbox',{name:/Проверены выбранный состав/}));await user.click(within(panel).getByRole('button',{name:'Утвердить предложение'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('PLAN_STALE');expect(within(panel).getByLabelText('Основание решения главного инженера')).toHaveValue('Моё решение');expect(api.publish).not.toHaveBeenCalled();
});
it('shows blockers and supports explicit rejection with a reason',async()=>{
  const value={...proposal(),can_approve:false,blocker_count:1,blockers:[{code:'UNPLACED',message:'Работа не размещена',row_number:209,occurrence_id:null,segment_id:null,date:null}]};
  vi.mocked(api.list).mockResolvedValue({items:[value],total:1});vi.mocked(api.get).mockResolvedValue(value);const user=userEvent.setup();mount();await user.click(await screen.findByRole('button',{name:/версия 3 ·/}));
  const panel=await screen.findByRole('region',{name:'Предложение публикации'});expect(panel).toHaveTextContent('Работа не размещена');await user.type(within(panel).getByLabelText('Основание решения главного инженера'),'Нужно исправить размещение');await user.click(within(panel).getByRole('button',{name:'Отклонить предложение'}));await waitFor(()=>expect(api.reject).toHaveBeenCalledTimes(1));
});
