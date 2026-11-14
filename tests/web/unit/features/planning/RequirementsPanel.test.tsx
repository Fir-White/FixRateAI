import { beforeEach,expect,it,vi } from 'vitest';
import { fireEvent,render,screen,waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import RequirementsPanel from '@/features/planning/RequirementsPanel';
import { requirementsApi,type RequirementsPreview } from '@/shared/api/requirements';
import { portfolioPlansApi } from '@/shared/api/portfolioPlans';

const result:RequirementsPreview={method_version:'requirements-v1',starts_on:'2027-01-01',ends_on:'2027-12-31',timezone:'UTC',calculated_at:'2026-11-14T00:00:00Z',source_sha256:'a'.repeat(64),summary:{total:1,known_person_hours:'3',total_person_hours:'3',new_person_hours:'3',unknown_hours_count:0,state_counts:{new:1},source_counts:{regulation:1},binding_count:1,selected_catalog_rows:0,unselected_catalog_rows:0,complete:true},months:[{month:'2027-01',known_person_hours:'3',requirements:1,unknown_hours_count:0}],items:[{requirement_id:'requirement',source_kind:'regulation',binding_id:'binding',rule_id:'rule',regulation_id:'regulation',source_revision:1,import_id:null,source_row:null,source_ref:'TEST ONLY real source reference',equipment_ids:['asset'],equipment_labels:['Насос № 1'],operation_code:'ТО-1',title:'Проверка насоса',maintenance_type:'ТО2',source_date:'2027-01-10',source_slot:'whole_day',earliest_date:'2027-01-01',due_date:'2027-01-10',person_hours:'3',crew_size:1,qualification_ids:[],state:'new',task_ids:[],explanation:'Проверенное календарное правило',issues:[],synthetic:false}],total:1,issues:[],total_issues:0,ready_for_real_plan:false};
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(requirementsApi,'preview').mockResolvedValue(result);});
function mount(props:Partial<Parameters<typeof RequirementsPanel>[0]>={}){return render(<MemoryRouter><RequirementsPanel timezone="UTC" catalogId="" initialStart="2027-01-01" initialEnd="2027-12-31" mayConfigure onCatalog={vi.fn()} onCalculate={vi.fn()} onPrepare={vi.fn()} {...props}/></MemoryRouter>);}

it('only calculates on command and distinguishes the known volume from the new workload',async()=>{
  const user=userEvent.setup();mount();expect(requirementsApi.preview).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Рассчитать состав обязательств'}));
  expect(await screen.findByRole('heading',{name:'ТО-1 · Проверка насоса'})).toBeVisible();
  expect(requirementsApi.preview).toHaveBeenCalledWith(expect.objectContaining({starts_on:'2027-01-01',ends_on:'2027-12-31',include_regulations:true,catalog:null}));
  await user.click(screen.getByText('Источник, сроки и объяснение'));
  expect(screen.getByText('TEST ONLY real source reference')).toBeVisible();
  expect(screen.getByRole('region',{name:'Состав обязательств'})).toHaveTextContent('Новый объём для планирования');
});

it('keeps unknown hours explicit, shows diagnostics and links only permitted existing tasks',async()=>{
  vi.mocked(requirementsApi.preview).mockResolvedValue({...result,summary:{...result.summary,total_person_hours:null,new_person_hours:null,unknown_hours_count:1,complete:false},items:[{...result.items[0],person_hours:null,state:'existing',task_ids:['task']}],issues:[{source_kind:'regulation',code:'NORM_VALUE_MISSING',message:'Подтвердите норму',binding_id:'binding',import_id:null,source_row:null}],total_issues:1});
  const user=userEvent.setup();mount({mayConfigure:false,mayViewTasks:false});
  await user.click(screen.getByRole('button',{name:'Рассчитать состав обязательств'}));
  expect(await screen.findByText(/Трудоёмкость не подтверждена/)).toBeVisible();
  expect(screen.getByRole('region',{name:'Что нужно уточнить для расчёта'})).toHaveTextContent('Подтвердите норму');
  expect(screen.queryByRole('link',{name:'Проверить регламенты оборудования'})).not.toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'Открыть задание 1'})).not.toBeInTheDocument();
});

it('keeps the search input and focus while the next page of results is loading',async()=>{
  const user=userEvent.setup();mount();await user.click(screen.getByRole('button',{name:'Рассчитать состав обязательств'}));
  await screen.findByRole('heading',{name:'ТО-1 · Проверка насоса'});
  let release!:(value:RequirementsPreview)=>void;
  vi.mocked(requirementsApi.preview).mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
  const search=screen.getByLabelText('Поиск обязательных работ');await user.type(search,'Насос');
  expect(screen.getByLabelText('Поиск обязательных работ')).toBe(search);expect(search).toHaveFocus();
  await waitFor(()=>expect(requirementsApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({q:'Насос'})));
  release(result);await screen.findByRole('heading',{name:'ТО-1 · Проверка насоса'});
});

it('retains source input after failure and never silently replaces the previous calculation',async()=>{
  vi.mocked(requirementsApi.preview).mockRejectedValueOnce(new Error('Источник недоступен'));
  const user=userEvent.setup();mount();await user.click(screen.getByRole('button',{name:'Рассчитать состав обязательств'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Источник недоступен');
  await user.click(screen.getByRole('button',{name:'Повторить расчёт обязательств'}));
  await screen.findByRole('heading',{name:'ТО-1 · Проверка насоса'});
  const field=screen.getByRole('button',{name:'Конец периода обязательств'}).closest('[data-calendar-input]')!.querySelector('input')!;
  fireEvent.change(field,{target:{value:'2027-06-30'}});
  expect(screen.getByText(/Параметры изменены/)).toBeVisible();
  expect(requirementsApi.preview).toHaveBeenCalledTimes(2);
});

it('keeps a single result and an unchanged save form while searching the reviewed scope',async()=>{
  vi.spyOn(portfolioPlansApi,'list').mockResolvedValue({items:[],total:0});
  vi.spyOn(portfolioPlansApi,'preview').mockResolvedValue({input_sha256:'a'.repeat(64),generator_version:'portfolio-occurrences-v1',total_occurrences:1,total_segments:1,total_person_hours:'3',selected_rows:0,unselected_rows:0,can_save:true,total_issues:0,issues:[],items:[],ready_for_real_plan:false,excluded_occurrences:0,requirements_sha256:'b'.repeat(64)});
  const user=userEvent.setup();mount({mayEdit:true,workspace:{catalogId:'',stage:'plan',draftId:'',draftRevision:null,planView:'work',selectCatalog:vi.fn(),selectStage:vi.fn(),selectDraft:vi.fn(),selectPlanView:vi.fn()}});
  await user.click(screen.getByRole('button',{name:'Рассчитать состав обязательств'}));
  await screen.findByRole('heading',{name:'ТО-1 · Проверка насоса'});
  await user.click(screen.getByRole('button',{name:'Проверить общий черновик'}));
  await user.type(await screen.findByLabelText('Основание общего плана'),'Проверен весь состав');
  await user.type(screen.getByLabelText('Поиск обязательных работ'),'Насос');
  await waitFor(()=>expect(requirementsApi.preview).toHaveBeenLastCalledWith(expect.objectContaining({q:'Насос'})));
  await screen.findByRole('heading',{name:'ТО-1 · Проверка насоса'});
  expect(screen.getAllByLabelText('Поиск обязательных работ')).toHaveLength(1);
  expect(screen.getByLabelText('Основание общего плана')).toHaveValue('Проверен весь состав');
});
