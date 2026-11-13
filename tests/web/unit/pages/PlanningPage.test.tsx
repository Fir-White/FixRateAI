import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { PlanningPage } from '@/pages/PlanningPage';
import { catalogImportsApi as catalogs, type CatalogSummary } from '@/shared/api/catalogImports';
import { draftPlansApi as plans, type DraftRecord, type PlanValidation } from '@/shared/api/draftPlans';
import { optimizationApi } from '@/shared/api/optimization';
import { publicationApi } from '@/shared/api/publication';
import { newPolicy } from '@/features/planning/PolicyFields';

vi.mock('@/shared/api/request',async original=>({...await original<typeof import('@/shared/api/request')>(),DEMO_MODE:false}));
const session=vi.hoisted(()=>({role:'chief_engineer'}));
vi.mock('@/shared/session/SessionContext',()=>({useSession:()=>({profile:{role:session.role,siteId:'site',siteName:'Тестовый объект',timezone:'UTC'}})}));
const summary:CatalogSummary={operation_count:217,group_count:17,top_level_group_count:16,maintenance_types:{ТО2:217},empty_duration_count:217,mark_count:1275,readiness_counts:{},ready_count:0,ready_for_real_plan:false,issue_count:0};
const metadata={import_id:'source',filename:'TEST_HVAC.xlsx',source_sha256:'a'.repeat(64),parser_version:'test',status:'draft' as const,created_at:'2026-11-13T12:00:00Z',summary};
const record:DraftRecord={draft_id:'plan',revision:2,parent_revision:1,import_id:'source',title:'План кондиционера',starts_on:'2027-01-01',ends_on:'2027-12-31',created_at:'2026-11-13T12:00:00Z',created_by:'chief',author_name:'Инженер',reason:'Уточнение',input_sha256:'a',occurrence_count:1,segment_count:1,total_person_hours:'3',status:'draft',ready_for_real_plan:false};
const validation:PlanValidation={validator_version:'test',status:'incomplete',checked_at:'2026-11-13T12:00:00Z',input_sha256:'a',resource_sha256:'b',total_issues:1,issue_counts:{UNPLACED:1},issues:[],total_person_hours:'3',placed_person_hours:'0',unplaced_segments:1,days:[],ready_for_real_plan:false};
function Location(){const location=useLocation();return <output data-testid="location">{location.pathname+location.search}</output>;}
function mount(path='/planning'){return render(<MemoryRouter initialEntries={[path]}><PlanningPage/><Location/></MemoryRouter>);}
beforeEach(()=>{
  vi.restoreAllMocks();session.role='chief_engineer';
  vi.spyOn(plans,'policy').mockResolvedValue({record,policy:newPolicy()});
  vi.spyOn(catalogs,'list').mockResolvedValue({items:[metadata],total:1});
  vi.spyOn(catalogs,'detail').mockResolvedValue({...metadata,groups:[],issues:[],sheet2_diagnostic:[],header_context:[]});
  vi.spyOn(catalogs,'preparation').mockResolvedValue({total:217,prepared_count:1,confirmed_count:1,blocker_counts:{},items:[],ready_for_real_plan:false});
  vi.spyOn(catalogs,'operations').mockResolvedValue({items:[],total:0});
  vi.spyOn(plans,'list').mockResolvedValue({items:[record],total:1});
  vi.spyOn(plans,'versions').mockResolvedValue({items:[record],total:1});
  vi.spyOn(plans,'overview').mockResolvedValue({record,months:[],validation});
  vi.spyOn(plans,'occurrences').mockResolvedValue({items:[],total:0});
  vi.spyOn(optimizationApi,'list').mockResolvedValue({items:[],total:0});
  vi.spyOn(publicationApi,'list').mockResolvedValue({items:[],total:0});
  vi.spyOn(plans,'create');vi.spyOn(publicationApi,'prepare');
});

it('starts with saved files and follows one visible path while preserving the chosen plan in the URL',async()=>{
  const user=userEvent.setup();mount();
  expect(await screen.findByRole('button',{name:/TEST_HVAC.xlsx · 217/})).toBeVisible();
  expect(screen.queryByLabelText('Excel каталога СВиК')).not.toBeInTheDocument();
  expect(catalogs.operations).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:/TEST_HVAC.xlsx · 217/}));
  const search=await screen.findByRole('textbox',{name:'Поиск операций каталога'});await user.type(search,'Фильтр');
  await user.click(screen.getByRole('button',{name:'Перейти к плану →'}));
  await user.click(await screen.findByRole('button',{name:'План кондиционера · версия 2 · 3 чел.-ч'}));
  await screen.findByRole('region',{name:'Сохранённая версия плана'});
  expect(screen.getByTestId('location')).toHaveTextContent('catalog=source');expect(screen.getByTestId('location')).toHaveTextContent('draft=plan');expect(screen.getByTestId('location')).toHaveTextContent('revision=2');
  expect(optimizationApi.list).not.toHaveBeenCalled();expect(publicationApi.list).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Утверждение и выпуск'}));
  await user.click(await screen.findByRole('button',{name:'Подготовить предложение к публикации'}));
  // Leaving a step preserves the unsaved proposal, without implicitly preparing it.
  await user.type(screen.getByLabelText('Основание предложения'),'Моя проверка');
  await user.click(screen.getByRole('button',{name:'Состав работ'}));
  expect(screen.queryByRole('textbox',{name:'Основание предложения'})).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Утверждение и выпуск'}));
  expect(screen.getByLabelText('Основание предложения')).toHaveValue('Моя проверка');
  expect(publicationApi.prepare).not.toHaveBeenCalled();expect(plans.create).not.toHaveBeenCalled();
});

it('opens a saved plan from its address without loading the source table or resetting to the file list',async()=>{
  mount('/planning?catalog=source&stage=plan&draft=plan&revision=2&view=schedule');
  expect(await screen.findByRole('heading',{name:'План кондиционера · версия 2'})).toBeVisible();
  await screen.findByRole('region',{name:'Автоматическое размещение работ'});
  expect(catalogs.operations).not.toHaveBeenCalled();expect(publicationApi.list).not.toHaveBeenCalled();
});

it('rejects a plan belonging to another file and offers a return to the plan list',async()=>{
  vi.mocked(plans.versions).mockResolvedValue({items:[{...record,import_id:'another-source'}],total:1});
  mount('/planning?catalog=source&stage=plan&draft=plan&revision=2');
  expect(await screen.findByRole('alert')).toHaveTextContent('План не найден в выбранном файле');
  expect(screen.getByRole('button',{name:'← Все планы этого файла'})).toBeVisible();
  expect(plans.occurrences).not.toHaveBeenCalled();expect(plans.create).not.toHaveBeenCalled();
});

it('keeps planning readable for an engineer without exposing import or draft creation',async()=>{
  session.role='engineer';const user=userEvent.setup();mount('/planning?catalog=source&stage=plan');
  await screen.findByRole('button',{name:'План кондиционера · версия 2 · 3 чел.-ч'});
  expect(screen.queryByRole('button',{name:'Подготовить новый черновик'})).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'← Все файлы и планы'}));
  await waitFor(()=>expect(screen.getByTestId('location')).toHaveTextContent('/planning'));
  expect(screen.queryByRole('button',{name:'Загрузить Excel с регламентами'})).not.toBeInTheDocument();
});
