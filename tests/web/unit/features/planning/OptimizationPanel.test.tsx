import { beforeEach,afterEach,expect,it,vi } from 'vitest';
import { fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OptimizationPanel from '@/features/planning/OptimizationPanel';
import { optimizationApi as api,type OptimizationRun,type OptimizationVariant } from '@/shared/api/optimization';
import type { DraftRecord } from '@/shared/api/draftPlans';

const record={draft_id:'draft',revision:1} as DraftRecord;
const options={grid_minutes:60 as const,time_limit_seconds:10,replan_existing:false,start_buffer_minutes:5,random_seed:1,weights:{daily_peak:10,worker_spread:3,changes:10,earliness:0}};
const variant:OptimizationVariant={kind:'optimized',method_version:'test',solver_status:'FEASIBLE',coverage_status:'FEASIBLE',optimality_proven:false,optimality_scope:'discrete_candidate_model',model_complete:true,duration_seconds:1,applicable:true,metrics:{total_occurrences:1,covered_occurrences:1,mandatory_work_coverage:'1',total_person_hours:'3',placed_person_hours:'3',unplaced_segments:0,peak_daily_person_hours:'3',peak_daily_utilization:'0.5',daily_load_balance:'0',staff_utilization:'0.25',fairness_spread:'0.1',changed_assignments:0,unfilled_slots:0},validation:{validator_version:'test',status:'valid',checked_at:'2026-11-13T12:00:00Z',input_sha256:'a',resource_sha256:'b',total_issues:0,issue_counts:{},issues:[],total_person_hours:'3',placed_person_hours:'3',unplaced_segments:0,days:[],ready_for_real_plan:false}};
const run=(state:OptimizationRun['state']='succeeded'):OptimizationRun=>({run_id:'run',draft_id:'draft',base_revision:1,created_at:'2026-11-13T12:00:00Z',state,options,error_code:null,applied_revision:null,applied_kind:null,result:state==='succeeded'?{completion_reason:'time_limit',model_complete:true,candidate_count:5,variable_count:10,diagnostics:[],diagnostic_counts:{},baseline:null,optimized:variant}:null});
beforeEach(()=>{
  vi.restoreAllMocks();vi.spyOn(api,'list').mockResolvedValue({items:[],total:0});vi.spyOn(api,'start').mockResolvedValue(run('queued'));
  vi.spyOn(api,'get').mockResolvedValue(run());vi.spyOn(api,'cancel').mockResolvedValue(run('cancelled'));vi.spyOn(api,'placements').mockResolvedValue({items:[],worker_labels:{},occurrence_labels:{},total:0});vi.spyOn(api,'apply').mockResolvedValue({...record,revision:2});
});
afterEach(()=>{vi.restoreAllMocks();});
const mount=(mayEdit=true,onSaved=vi.fn())=>render(<OptimizationPanel record={record} mayEdit={mayEdit} timezone="Asia/Yekaterinburg" onSaved={onSaved}/>);

it('does not launch calculations on opening and keeps a readonly role readonly',async()=>{
  mount(false);await waitFor(()=>expect(api.list).toHaveBeenCalled());expect(api.start).not.toHaveBeenCalled();
  expect(screen.queryByRole('button',{name:'Рассчитать два варианта'})).not.toBeInTheDocument();
});
it('runs asynchronously, cancels explicitly and displays the actual terminal state',async()=>{
  const user=userEvent.setup();mount();await user.click(screen.getByRole('button',{name:'Рассчитать два варианта'}));
  expect(await screen.findByRole('status')).toHaveTextContent('В очереди');
  expect(api.start).toHaveBeenCalledWith('draft',1,expect.any(String),expect.objectContaining({replan_existing:false}));
  await user.click(screen.getByRole('button',{name:'Отменить расчёт'}));
  await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('Отменён'));
});
it('reuses an idempotency key after transport failure with the same options',async()=>{
  vi.mocked(api.start).mockRejectedValueOnce(new Error('Сеть недоступна'));const user=userEvent.setup();mount();
  await user.click(screen.getByRole('button',{name:'Рассчитать два варианта'}));expect(await screen.findByRole('alert')).toHaveTextContent('Сеть недоступна');
  await user.click(screen.getByRole('button',{name:'Рассчитать два варианта'}));expect(vi.mocked(api.start).mock.calls[0][2]).toBe(vi.mocked(api.start).mock.calls[1][2]);
});
async function completed(user:ReturnType<typeof userEvent.setup>,mayEdit=true,onSaved=vi.fn()){
  vi.mocked(api.list).mockResolvedValue({items:[run()],total:1});mount(mayEdit,onSaved);
  await user.click(await screen.findByRole('button',{name:/версия 1 · Завершён/}));return screen.findByRole('region',{name:'Вариант с балансировкой'});
}
it('compares honest metrics and applies only after a reason and explicit command',async()=>{
  const user=userEvent.setup(),saved=vi.fn(),panel=await completed(user,true,saved);
  expect(panel).toHaveTextContent('Оптимальность не доказана');expect(panel).toHaveTextContent('50.0%');expect(api.apply).not.toHaveBeenCalled();
  await user.type(within(panel).getByLabelText('Причина применения варианта'),'Проверено инженером');await user.click(within(panel).getByRole('button',{name:'Применить в новую версию'}));
  await waitFor(()=>expect(saved).toHaveBeenCalledWith(expect.objectContaining({revision:2})));
});
it('preserves the reason after a stale snapshot conflict',async()=>{
  vi.mocked(api.apply).mockRejectedValue(new Error('Доступность изменилась'));const user=userEvent.setup(),panel=await completed(user);
  await user.type(within(panel).getByLabelText('Причина применения варианта'),'Моя причина');await user.click(within(panel).getByRole('button',{name:'Применить в новую версию'}));
  expect(await within(panel).findByRole('alert')).toHaveTextContent('Доступность изменилась');expect(within(panel).getByLabelText('Причина применения варианта')).toHaveValue('Моя причина');
});
it('pauses status polling while hidden and resumes without duplicate requests',async()=>{
  let hidden=true;vi.spyOn(document,'hidden','get').mockImplementation(()=>hidden);
  const user=userEvent.setup();mount();await user.click(screen.getByRole('button',{name:'Рассчитать два варианта'}));
  await new Promise(resolve=>setTimeout(resolve,850));expect(api.get).not.toHaveBeenCalled();
  hidden=false;fireEvent(document,new Event('visibilitychange'));
  await waitFor(()=>expect(api.get).toHaveBeenCalledTimes(1));await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('Завершён'));
});
