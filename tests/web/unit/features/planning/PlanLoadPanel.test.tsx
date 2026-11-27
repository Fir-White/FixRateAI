import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PlanLoadPanel from '@/features/planning/PlanLoadPanel';
import {planLoadApi as api,type PlanLoadPreview} from '@/shared/api/planLoad';
import type {DraftRecord} from '@/shared/api/draftPlans';

const record={draft_id:'draft',revision:2,title:'Общий план'} as DraftRecord;
const data:PlanLoadPreview={record,timezone:'UTC',checked_at:'2026-11-14T00:00:00Z',resource_sha256:'a',source_state:'current',validation_status:'incomplete',total_issues:0,issues:[],unknown_workers:0,published_tasks:0,totals:{total_person_hours:'5',placed_person_hours:'3',unplaced_person_hours:'2',available_person_hours:'24',deficit_person_hours:'0',due_outside_view_person_hours:'0',unplaced_outside_view_person_hours:'0'},months:[{month:'2027-01',due_person_hours:'5',planned_person_hours:'3',reserved_person_hours:'3',unplaced_due_person_hours:'2',available_person_hours:'24',deficit_person_hours:'0',required_people_peak:1,selected_people_peak:1}],days:Array.from({length:31},(_,i)=>({date:`2027-01-${String(i+1).padStart(2,'0')}`,planned_person_hours:i===0?'3':'0',reserved_person_hours:i===0?'3':'0',unplaced_due_person_hours:i===30?'2':'0',available_person_hours:'24',deficit_person_hours:'0',required_people_peak:i===0?1:0,selected_people_peak:i===0?1:0,available_people_peak:1}))};
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(api,'preview').mockResolvedValue(data);});

it('bounds the daily DOM and changes period locally without a new calculation',async()=>{
  const user=userEvent.setup(),onMonth=vi.fn();render(<PlanLoadPanel record={record} timezone="UTC" onMonth={onMonth}/>);
  const list=await screen.findByRole('list',{name:'Подневная нагрузка'});expect(within(list).getAllByRole('listitem')).toHaveLength(25);
  expect(screen.getByText(/Альтернативные планы не суммируются/)).toBeVisible();
  await user.click(screen.getByRole('button',{name:/2027-01 · размещено/}));expect(onMonth).toHaveBeenCalledWith('2027-01');
  expect(api.preview).toHaveBeenCalledTimes(1);expect(screen.getByText(/Неразмещённые часы показаны отдельно/)).toBeVisible();
});

it('keeps unknown resource capacity explicit and distinguishes approved reservations',async()=>{
  vi.mocked(api.preview).mockResolvedValue({...data,source_state:'published_snapshot',unknown_workers:1,published_tasks:1,totals:{...data.totals,available_person_hours:null,deficit_person_hours:null},days:[{...data.days[0],available_people_peak:null,available_person_hours:null,deficit_person_hours:null}]});
  render(<PlanLoadPanel record={record} timezone="UTC"/>);
  expect(await screen.findByText(/Собственные назначения учтены один раз/)).toBeVisible();
  expect(screen.getByRole('list',{name:'Подневная нагрузка'})).toHaveTextContent('Неизвестно');
  expect(screen.getByText(/Доступность не заменяется нулём/)).toBeVisible();
});

it('offers retry after error and always requests the chosen immutable revision',async()=>{
  vi.mocked(api.preview).mockRejectedValueOnce(new Error('Источник недоступен'));const user=userEvent.setup();render(<PlanLoadPanel record={record} timezone="UTC"/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Источник недоступен');
  await user.click(screen.getByRole('button',{name:'Повторить расчёт нагрузки'}));await screen.findByRole('list',{name:'Подневная нагрузка'});
  await waitFor(()=>expect(api.preview).toHaveBeenLastCalledWith('draft',2));
});
