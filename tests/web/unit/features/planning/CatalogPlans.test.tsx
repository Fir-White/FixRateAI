import { beforeEach,expect,it,vi } from 'vitest';
import { fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CatalogPlans } from '@/features/planning/CatalogPlans';
import { draftPlansApi as api,type DraftRecord,type WorkOccurrence,type WorkSegment,type PlanValidation } from '@/shared/api/draftPlans';
import { catalogImportsApi } from '@/shared/api/catalogImports';
import { splitPersonHours } from '@/features/planning/segmentHours';
import { optimizationApi } from '@/shared/api/optimization';
import { publicationApi } from '@/shared/api/publication';

const record=(revision=1):DraftRecord=>({draft_id:'draft',revision,parent_revision:revision>1?revision-1:null,import_id:'source',title:'План СВиК',starts_on:'2027-01-01',ends_on:'2027-12-31',created_at:'2026-11-13T12:00:00Z',created_by:'chief',author_name:'Главный инженер',reason:'Проверенный источник',input_sha256:'a'.repeat(64),occurrence_count:1,segment_count:revision===1?1:3,total_person_hours:'3.000',status:'draft',ready_for_real_plan:false});
const root:WorkOccurrence={occurrence_id:'root',site_id:'site',import_id:'source',source_sha256:'a'.repeat(64),parser_version:'test',source_row:8,decision_revision:1,source_cells:['B8','H8'],source_date:'2027-01-10',source_slot:'whole_day',title:'Обслуживание фильтра',operation_code:'1.4',maintenance_type:'ТО2',interpretation:'ALLOWED_WINDOW',equipment_ids:['asset'],earliest_date:'2027-01-01',latest_date:'2027-01-10',allowed_intervals:[{start_at:'2027-01-01T00:00:00+05:00',end_at:'2027-01-11T00:00:00+05:00'}],total_person_hours:'3.000',crew_size:1,splittable:true,min_segment_minutes:60,qualification_ids:[],qualifications_confirmed:true,included_rows:[],norm_ref:'Проверенная методика',norm_scope:'per_asset',policy_note:'Делимость разрешена'};
const segment:WorkSegment={segment_id:'segment',occurrence_id:'root',equipment_ids:['asset'],person_hours:'3.000',start_at:null,end_at:null,worker_ids:[],locked:false,depends_on_segment_ids:[]};
const validation:PlanValidation={validator_version:'test',status:'incomplete',checked_at:'2026-11-13T12:00:00Z',input_sha256:'a'.repeat(64),resource_sha256:'b'.repeat(64),total_issues:1,issue_counts:{UNPLACED:1},issues:[{code:'UNPLACED',message:'Сегмент ещё не размещён',row_number:8,occurrence_id:'root',segment_id:'segment',date:null}],total_person_hours:'3.000',placed_person_hours:'0',unplaced_segments:1,days:[],ready_for_real_plan:false};
function calendarField(label:string){return screen.getByRole('button',{name:label}).closest('[data-calendar-input]')!.querySelector('input')!;}
beforeEach(()=>{
  vi.restoreAllMocks();
  vi.spyOn(optimizationApi,'list').mockResolvedValue({items:[],total:0});
  vi.spyOn(publicationApi,'list').mockResolvedValue({items:[],total:0});
  vi.spyOn(api,'list').mockResolvedValue({items:[record()],total:1});
  vi.spyOn(api,'sources').mockResolvedValue({items:[{row_number:8,code:'1.4',title:'Обслуживание фильтра',maintenance_type:'ТО2'}],total:1});
  vi.spyOn(catalogImportsApi,'preparation').mockResolvedValue({total:217,prepared_count:1,confirmed_count:1,blocker_counts:{},items:[{row_number:8,revision:1,confirmed:true,prepared:true,blockers:[]}],ready_for_real_plan:false});
  vi.spyOn(api,'preview').mockResolvedValue({input_sha256:'a'.repeat(64),generator_version:'test',total_occurrences:1,total_segments:1,total_person_hours:'3.000',selected_rows:1,unselected_rows:216,can_save:true,total_issues:0,issues:[],items:[root],ready_for_real_plan:false});
  vi.spyOn(api,'create').mockResolvedValue(record());
  vi.spyOn(api,'overview').mockImplementation(async(_id,revision)=>({record:record(revision),months:[{month:'2027-01',due_person_hours:'3.000',planned_person_hours:'0'}],validation}));
  vi.spyOn(api,'occurrences').mockResolvedValue({items:[root],total:1});
  vi.spyOn(api,'segments').mockResolvedValue({occurrence:root,items:[segment],total:1,worker_labels:{}});
  vi.spyOn(api,'choices').mockResolvedValue({items:[{id:'worker',label:'Техник Иванов'}],total:1});
  vi.spyOn(api,'edit').mockResolvedValue(record(2));
  vi.spyOn(api,'place').mockResolvedValue(record(2));
  vi.spyOn(api,'versions').mockResolvedValue({items:[record(2),record()],total:2});
  vi.spyOn(api,'validate').mockResolvedValue(validation);
});

it('previews an explicit source scope with unknown capacity and saves only on command',async()=>{
  const user=userEvent.setup();render(<CatalogPlans id="source" mayEdit timezone="Asia/Yekaterinburg"/>);
  await user.click(screen.getByRole('button',{name:'Подготовить новый черновик'}));
  await user.click(await screen.findByRole('checkbox',{name:/1.4 · Обслуживание фильтра/}));
  fireEvent.change(calendarField('Начало горизонта'),{target:{value:'2027-01-01'}});
  fireEvent.change(calendarField('Конец горизонта'),{target:{value:'2027-12-31'}});
  await user.click(screen.getByRole('button',{name:'Предпросмотр работ'}));
  const preview=await screen.findByLabelText('Предпросмотр работ');expect(preview).toHaveTextContent('1 корневых работ');
  expect(api.create).not.toHaveBeenCalled();
  expect(api.preview).toHaveBeenCalledWith(expect.objectContaining({starts_on:'2027-01-01',ends_on:'2027-12-31',row_numbers:[8],policy:expect.objectContaining({capacity_hours_per_24h:null,capacity_confirmed:false})}));
  await user.type(screen.getByLabelText('Основание создания'),'Проверка исходных данных');
  await user.click(screen.getByRole('button',{name:'Сохранить новую версию плана'}));
  expect(await screen.findByRole('region',{name:'Сохранённая версия плана'})).toHaveTextContent('версия 1');
  expect(api.create).toHaveBeenCalledTimes(1);
});

async function openSegment(user:ReturnType<typeof userEvent.setup>,mayEdit=true){
  render(<CatalogPlans id="source" mayEdit={mayEdit} timezone="Asia/Yekaterinburg"/>);
  await user.click(await screen.findByRole('button',{name:'План СВиК · версия 1 · 3.000 чел.-ч'}));
  await user.click(await screen.findByRole('button',{name:'1.4 · Обслуживание фильтра'}));
  await user.click(await screen.findByRole('button',{name:'Сегмент 1 · 3.000 чел.-ч · Без размещения'}));
  return screen.getByRole('region',{name:'Редактор сегмента'});
}
it('splits conserved effort in a new version and leaves the source occurrence untouched',async()=>{
  const user=userEvent.setup(),editor=await openSegment(user);
  await user.type(within(editor).getByLabelText('Причина изменения плана'),'Разделить по технологическим этапам');
  fireEvent.change(within(editor).getByLabelText('Число частей сегмента'),{target:{value:'3'}});
  await user.click(within(editor).getByRole('button',{name:'Разделить с сохранением общего объёма'}));
  await waitFor(()=>expect(api.edit).toHaveBeenCalledTimes(1));
  const command=vi.mocked(api.edit).mock.calls[0][1];
  expect(command.expected_revision).toBe(1);expect(command.replace_segment_ids).toEqual(['segment']);
  expect(command.segments.map(s=>s.person_hours)).toEqual(['1.000','1.000','1.000']);
  expect(command.segments[2].segment_id).toBe('segment');
  expect(await screen.findByRole('region',{name:'Сохранённая версия плана'})).toHaveTextContent('версия 2');
});

it('keeps local timestamps and reason after a version conflict',async()=>{
  vi.mocked(api.place).mockRejectedValue(new Error('Версия плана изменилась'));
  const user=userEvent.setup(),editor=await openSegment(user);
  fireEvent.change(calendarField('Начало сегмента по времени объекта'),{target:{value:'2027-01-01T09:00'}});
  fireEvent.change(calendarField('Конец сегмента по времени объекта'),{target:{value:'2027-01-01T12:00'}});
  await user.click(within(editor).getByRole('button',{name:'Добавить исполнителя'}));
  await user.click(await within(editor).findByRole('button',{name:'Техник Иванов'}));
  await user.type(within(editor).getByLabelText('Причина изменения плана'),'Моё размещение');
  await user.click(within(editor).getByRole('button',{name:'Сохранить размещение в новой версии'}));
  expect(await within(editor).findByRole('alert')).toHaveTextContent('Версия плана изменилась');
  expect(within(editor).getByLabelText('Причина изменения плана')).toHaveValue('Моё размещение');
  expect(calendarField('Начало сегмента по времени объекта')).toHaveValue('2027-01-01T09:00');
});

it('keeps the same version readable without exposing mutations',async()=>{
  const user=userEvent.setup(),editor=await openSegment(user,false);
  expect(within(editor).getByLabelText('Причина изменения плана')).toBeDisabled();
  expect(screen.queryByRole('button',{name:'Подготовить новый черновик'})).not.toBeInTheDocument();
  expect(within(editor).queryByRole('button',{name:'Сохранить размещение в новой версии'})).not.toBeInTheDocument();
  expect(within(editor).queryByRole('button',{name:'Разделить с сохранением общего объёма'})).not.toBeInTheDocument();
  expect(api.edit).not.toHaveBeenCalled();expect(api.place).not.toHaveBeenCalled();
});

it('keeps Decimal effort exact for uneven and large splits and never creates a zero part',()=>{
  expect(splitPersonHours('48.000',7)).toEqual(['6.857','6.857','6.857','6.857','6.857','6.857','6.858']);
  const parts=splitPersonHours('9999999999999.999',7);
  expect(parts.reduce((sum,value)=>sum+BigInt(value.replace('.','')),0n)).toBe(9999999999999999n);
  expect(splitPersonHours('1E+3',2)).toEqual(['500.000','500.000']);
  expect(()=>splitPersonHours('0.001',2)).toThrow();
});
