import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CatalogDecisionEditor } from '@/features/equipment/CatalogDecisionEditor';
import { catalogImportsApi as api, type CatalogDecisionRecord } from '@/shared/api/catalogImports';

const record=():CatalogDecisionRecord=>({row_number:8,revision:0,created_by:null,created_at:null,confirmed:false,reason:'',equipment:[],blockers:['NEEDS_DURATION'],prepared:false,total_person_hours:null,elapsed_hours:null,ready_for_real_plan:false,
  decision:{interpretation:'ALLOWED_WINDOW',calendar_year:2027,mark_slots:'one_per_mark',semantics_note:'Synthetic allowed window',frequency_kind:'month',frequency_interval:1,included_in_row:null,equipment_ids:[],norm_value:null,norm_unit:'person_hour',norm_scope:'per_asset',crew_size:1,norm_ref:'Synthetic methodology',splittable:false,min_segment_minutes:null,policy_note:'Synthetic continuous job'}});
beforeEach(()=>{
  vi.restoreAllMocks();
  vi.spyOn(api,'decision').mockResolvedValue(record());
  vi.spyOn(api,'bindingOptions').mockResolvedValue({total:1,items:[{equipment_id:'asset',asset_code:'HVAC-001',name:'Synthetic HVAC asset',status:'active',revision:1}]});
  vi.spyOn(api,'saveDecision').mockImplementation(async(_id,_row,body)=>({...record(),revision:1,confirmed:body.confirm,prepared:body.confirm,decision:body.decision,blockers:[],total_person_hours:'3.000',elapsed_hours:'3.000'}));
  vi.spyOn(api,'history').mockResolvedValue({items:[],total:0});
});

it('binds real inventory, saves explicit norm and confirmation as a new revision',async()=>{
  const user=userEvent.setup(),saved=vi.fn();
  render(<CatalogDecisionEditor id="catalog" row={8} mayEdit mayConfirm onSaved={saved}/>);
  await user.click(await screen.findByRole('button',{name:'Выбрать оборудование'}));
  await user.click(await screen.findByRole('button',{name:'HVAC-001 · Synthetic HVAC asset'}));
  await user.type(screen.getByLabelText('Норма времени'),'3');
  await user.type(screen.getByLabelText('Причина новой версии'),'Проверено инженером');
  await user.click(screen.getByRole('button',{name:'Подтвердить решение строки'}));
  await waitFor(()=>expect(api.saveDecision).toHaveBeenCalledWith('catalog',8,expect.objectContaining({expected_revision:0,confirm:true,reason:'Проверено инженером',decision:expect.objectContaining({norm_value:'3',crew_size:1,equipment_ids:['asset']})})));
  expect(await screen.findByLabelText('Расчёт трудозатрат')).toHaveTextContent('3.000 чел.-ч');
  expect(screen.getByText(/версия 1/)).toBeVisible();expect(saved).toHaveBeenCalledTimes(1);
});

it('keeps local inputs after revision conflict and only reloads on explicit action',async()=>{
  vi.mocked(api.saveDecision).mockRejectedValue(new Error('REVISION_CONFLICT: строка изменена'));
  const user=userEvent.setup();render(<CatalogDecisionEditor id="catalog" row={8} mayEdit mayConfirm onSaved={vi.fn()}/>);
  await user.type(await screen.findByLabelText('Норма времени'),'7');
  await user.type(screen.getByLabelText('Причина новой версии'),'Мои изменения');
  await user.click(screen.getByRole('button',{name:'Сохранить решение-черновик'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('REVISION_CONFLICT');
  expect(screen.getByLabelText('Норма времени')).toHaveValue(7);
  expect(screen.getByLabelText('Причина новой версии')).toHaveValue('Мои изменения');
  expect(api.decision).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button',{name:'Загрузить актуальную версию'}));
  await waitFor(()=>expect(api.decision).toHaveBeenCalledTimes(2));
  expect(await screen.findByLabelText('Норма времени')).toHaveValue(null);
});

it('renders read only decisions without mutation or inventory commands',async()=>{
  const user=userEvent.setup();render(<CatalogDecisionEditor id="catalog" row={8} mayEdit={false} mayConfirm={false} onSaved={vi.fn()}/>);
  expect(await screen.findByLabelText('Норма времени')).toBeDisabled();
  expect(screen.queryByRole('button',{name:'Выбрать оборудование'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Сохранить решение-черновик'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Подтвердить решение строки'})).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'История решений строки'}));
  expect(await screen.findByText('Сохранённых решений пока нет.')).toBeVisible();
  expect(api.bindingOptions).not.toHaveBeenCalled();expect(api.saveDecision).not.toHaveBeenCalled();
});
