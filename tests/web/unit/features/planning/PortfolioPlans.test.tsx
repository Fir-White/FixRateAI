import { beforeEach,expect,it,vi } from 'vitest';
import { render,screen,waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SavePortfolio } from '@/features/planning/PortfolioPlans';
import { portfolioPlansApi as api,type PortfolioPreview } from '@/shared/api/portfolioPlans';
import type { RequirementsRequest } from '@/shared/api/requirements';
import type { DraftRecord } from '@/shared/api/draftPlans';

const requirements:RequirementsRequest={starts_on:'2027-01-01',ends_on:'2027-12-31',include_regulations:true,catalog:null};
const preview:PortfolioPreview={input_sha256:'a'.repeat(64),generator_version:'portfolio-occurrences-v1',total_occurrences:2,total_segments:2,total_person_hours:'5',selected_rows:1,unselected_rows:216,can_save:true,total_issues:0,issues:[],items:[],ready_for_real_plan:false,excluded_occurrences:3,requirements_sha256:'b'.repeat(64)};
const record:DraftRecord={draft_id:'portfolio',revision:1,parent_revision:null,import_id:null,source_kind:'portfolio',title:'Общий план ТО',starts_on:requirements.starts_on,ends_on:requirements.ends_on,created_at:'2026-11-14T00:00:00Z',created_by:'chief',author_name:'Инженер',reason:'Проверенный состав',input_sha256:'a'.repeat(64),occurrence_count:2,segment_count:2,total_person_hours:'5',status:'draft',ready_for_real_plan:false};
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(api,'preview').mockResolvedValue(preview);vi.spyOn(api,'create').mockResolvedValue(record);});

it('saves the full reviewed scope only after an explicit check and a reason',async()=>{
  const user=userEvent.setup(),saved=vi.fn();render(<SavePortfolio requirements={requirements} timezone="UTC" onSaved={saved}/>);
  expect(api.preview).not.toHaveBeenCalled();expect(api.create).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Проверить общий черновик'}));
  expect(await screen.findByText(/Уже выдано или принято: 3/)).toBeVisible();
  expect(screen.getByRole('button',{name:'Сохранить общий план'})).toBeDisabled();
  await user.type(screen.getByLabelText('Основание общего плана'),'Проверенный состав');
  await user.click(screen.getByRole('button',{name:'Сохранить общий план'}));
  await waitFor(()=>expect(saved).toHaveBeenCalledWith(record));
  expect(api.create).toHaveBeenCalledWith(expect.objectContaining({kind:'portfolio',requirements,policy:expect.objectContaining({capacity_status:'unknown',capacity_hours_per_24h:null,access_status:'unknown'})}),'a'.repeat(64),expect.any(String),'Общий план ТО','Проверенный состав');
});

it('keeps the entered fields and retry key after a failed save',async()=>{
  vi.mocked(api.create).mockRejectedValueOnce(new Error('Состав изменился — повторите проверку'));
  const user=userEvent.setup();render(<SavePortfolio requirements={requirements} timezone="UTC" onSaved={vi.fn()}/>);
  await user.click(screen.getByRole('button',{name:'Проверить общий черновик'}));
  await user.type(await screen.findByLabelText('Основание общего плана'),'Согласованный период');
  await user.click(screen.getByRole('button',{name:'Сохранить общий план'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Состав изменился');
  expect(screen.getByLabelText('Основание общего плана')).toHaveValue('Согласованный период');
  await user.click(screen.getByRole('button',{name:'Сохранить общий план'}));
  expect(vi.mocked(api.create).mock.calls[1][2]).toBe(vi.mocked(api.create).mock.calls[0][2]);
});

it('keeps a reviewed unknown or overlapping source blocked',async()=>{
  vi.mocked(api.preview).mockResolvedValue({...preview,can_save:false,total_issues:1,issues:[{code:'REQUIREMENTS_REVIEW',message:'Проверьте одинаковые работы из двух источников',row_number:null,occurrence_id:null,segment_id:null,date:null}]});
  const user=userEvent.setup();render(<SavePortfolio requirements={requirements} timezone="UTC" onSaved={vi.fn()}/>);
  await user.click(screen.getByRole('button',{name:'Проверить общий черновик'}));
  expect(await screen.findByText('Проверьте одинаковые работы из двух источников')).toBeVisible();
  await user.type(screen.getByLabelText('Основание общего плана'),'Причина');
  expect(screen.getByRole('button',{name:'Сохранить общий план'})).toBeDisabled();expect(api.create).not.toHaveBeenCalled();
});
