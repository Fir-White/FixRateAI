import { useState } from 'react';
import { beforeEach,expect,it,vi } from 'vitest';
import { fireEvent,render,screen,waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PlanPolicyPanel from '@/features/planning/PlanPolicyPanel';
import { PolicyFields,newPolicy } from '@/features/planning/PolicyFields';
import { draftPlansApi as api,type DraftRecord,type DraftPolicy } from '@/shared/api/draftPlans';

const record={draft_id:'draft',revision:3} as DraftRecord;
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(api,'policy').mockResolvedValue({record,policy:newPolicy()});vi.spyOn(api,'changePolicy').mockResolvedValue({...record,revision:4});});
function Fields(){const [value,setValue]=useState<DraftPolicy>(newPolicy());return <><PolicyFields value={value} onChange={setValue} timezone="Asia/Yekaterinburg"/><output data-testid="policy">{JSON.stringify(value)}</output></>;}
it('requires explicit sources and reconfirmation after changing capacity or access',async()=>{
  const user=userEvent.setup();render(<Fields/>);
  expect(screen.getByLabelText('Статус полезной ёмкости').querySelector('option[value="confirmed"]')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Полезная ёмкость сотрудника за 24 часа присутствия'),{target:{value:'8'}});
  await user.type(screen.getByLabelText('Источник политики ёмкости'),'TEST ONLY approved capacity');
  await user.selectOptions(screen.getByLabelText('Статус полезной ёмкости'),'confirmed');
  expect(screen.getByTestId('policy')).toHaveTextContent('"capacity_confirmed":true');
  fireEvent.change(screen.getByLabelText('Полезная ёмкость сотрудника за 24 часа присутствия'),{target:{value:'10'}});
  expect(screen.getByLabelText('Статус полезной ёмкости')).toHaveValue('provisional');
  await user.selectOptions(screen.getByLabelText('Режим доступа к объекту'),'weekly');
  await user.click(screen.getByLabelText('Окончание на следующий день, окно 1'));
  expect(screen.getByTestId('policy')).toHaveTextContent('"end_minute":2460');
  await user.type(screen.getByLabelText('Основание режима доступа'),'TEST ONLY overnight window');
  await user.selectOptions(screen.getByLabelText('Статус доступа к объекту'),'confirmed');
  await user.selectOptions(screen.getByLabelText('День недели, окно 1'),'7');
  expect(screen.getByLabelText('Статус доступа к объекту')).toHaveValue('provisional');
});
it('retains edits after a conflict, reuses the retry key and returns the new version after success',async()=>{
  vi.mocked(api.changePolicy).mockRejectedValueOnce(new Error('Версия плана изменилась'));
  const onSaved=vi.fn(),user=userEvent.setup();render(<PlanPolicyPanel record={record} mayEdit timezone="UTC" onSaved={onSaved}/>);
  await user.click(await screen.findByRole('button',{name:'Изменить условия расчёта'}));
  await user.type(screen.getByLabelText('Причина изменения условий'),'TEST ONLY reviewed access');
  await user.selectOptions(screen.getByLabelText('Режим доступа к объекту'),'unrestricted');
  await user.click(screen.getByRole('button',{name:'Сохранить условия новой версией'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Версия плана изменилась');
  expect(screen.getByLabelText('Причина изменения условий')).toHaveValue('TEST ONLY reviewed access');
  expect(screen.getByLabelText('Режим доступа к объекту')).toHaveValue('unrestricted');
  await user.click(screen.getByRole('button',{name:'Сохранить условия новой версией'}));
  await waitFor(()=>expect(onSaved).toHaveBeenCalledWith({...record,revision:4}));
  const calls=vi.mocked(api.changePolicy).mock.calls;
  expect(calls[0][1]).toEqual(calls[1][1]);expect(calls[0][1].expected_revision).toBe(3);
});
it('keeps unsaved values when collapsed and exposes historical versions without mutations',async()=>{
  const user=userEvent.setup(),{rerender}=render(<PlanPolicyPanel record={record} mayEdit timezone="UTC" onSaved={vi.fn()}/>);
  await user.click(await screen.findByRole('button',{name:'Изменить условия расчёта'}));
  await user.type(screen.getByLabelText('Причина изменения условий'),'My draft');
  await user.click(screen.getByRole('button',{name:'Свернуть параметры'}));
  expect(screen.queryByRole('textbox',{name:'Причина изменения условий'})).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Изменить условия расчёта'}));
  expect(screen.getByLabelText('Причина изменения условий')).toHaveValue('My draft');
  rerender(<PlanPolicyPanel record={record} mayEdit={false} timezone="UTC" onSaved={vi.fn()}/>);
  expect(screen.queryByRole('button',{name:'Изменить условия расчёта'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Сохранить условия новой версией'})).not.toBeInTheDocument();expect(api.changePolicy).not.toHaveBeenCalled();
});
