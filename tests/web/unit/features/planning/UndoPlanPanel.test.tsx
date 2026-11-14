import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UndoPlanPanel from '@/features/planning/UndoPlanPanel';
import {draftPlansApi as api,type DraftRecord} from '@/shared/api/draftPlans';

const record={draft_id:'draft',revision:2} as DraftRecord;
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(api,'undoView').mockResolvedValue({record,restores_revision:1,restores_author_name:'Инженер',can_undo:true,blocker:null,explanation:'История сохраняется; будет создана новая версия',requires_unlock:false});vi.spyOn(api,'undo').mockResolvedValue({...record,revision:3,change_kind:'undo',undone_revision:2,restored_revision:1});});

it('requires reason and explicit consent before appending an undo version',async()=>{
  const user=userEvent.setup(),saved=vi.fn();render(<UndoPlanPanel record={record} onSaved={saved}/>);
  const button=await screen.findByRole('button',{name:'Отменить изменение новой версией'});expect(button).toBeDisabled();expect(api.undo).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText('Причина отмены изменения'),'Перенос был ошибочным');
  expect(button).toBeDisabled();await user.click(screen.getByRole('checkbox',{name:'Подтверждаю восстановление предыдущего состояния новой версией'}));
  await user.click(button);await waitFor(()=>expect(saved).toHaveBeenCalledWith(expect.objectContaining({revision:3,restored_revision:1})));
  expect(api.undo).toHaveBeenCalledWith('draft',expect.objectContaining({expected_revision:2,reason:'Перенос был ошибочным',unlock:false,idempotency_key:expect.any(String)}));
});

it('requires explicit lock release and retains reason/retry key on failure',async()=>{
  vi.mocked(api.undoView).mockResolvedValue({record,restores_revision:1,restores_author_name:'Инженер',can_undo:true,blocker:null,explanation:'Будет отменено закрепление',requires_unlock:true});
  vi.mocked(api.undo).mockRejectedValueOnce(new Error('Версия изменилась'));
  const user=userEvent.setup();render(<UndoPlanPanel record={record} onSaved={vi.fn()}/>);
  await user.type(await screen.findByLabelText('Причина отмены изменения'),'Проверенная причина');
  await user.click(screen.getByRole('checkbox',{name:'Подтверждаю восстановление предыдущего состояния новой версией'}));
  const button=screen.getByRole('button',{name:'Отменить изменение новой версией'});expect(button).toBeDisabled();
  await user.click(screen.getByRole('checkbox',{name:'Разрешаю отменить изменённые закрепления сегментов'}));
  await user.click(button);expect(await screen.findByRole('alert')).toHaveTextContent('Версия изменилась');
  expect(screen.getByLabelText('Причина отмены изменения')).toHaveValue('Проверенная причина');
  await user.click(button);expect(vi.mocked(api.undo).mock.calls[0][1].idempotency_key).toBe(vi.mocked(api.undo).mock.calls[1][1].idempotency_key);
});

it('shows the server publication/author restriction without a write control',async()=>{
  vi.mocked(api.undoView).mockResolvedValue({record,restores_revision:1,restores_author_name:'Другой инженер',can_undo:false,blocker:'PUBLISHED_PLAN',explanation:'План уже выпускался. Требуется согласованное перепланирование.',requires_unlock:false});
  render(<UndoPlanPanel record={record} onSaved={vi.fn()}/>);
  expect(await screen.findByText(/План уже выпускался/)).toBeVisible();expect(screen.queryByRole('button',{name:'Отменить изменение новой версией'})).not.toBeInTheDocument();
});
