import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {ActionCard} from '@/features/assistant/ActionCard';
import {assistantApi as api,type ChatAction} from '@/shared/api/assistant';
const record:ChatAction={action_id:'action',conversation_id:'chat',turn_id:'turn',tool_name:'equipment_edit',arguments:{path:{equipment_id:'equipment'},body:{expected_revision:2,name:'Новый насос',reason:'Проверено инженером'}},payload_sha256:'a'.repeat(64),before_snapshot:{sha256:'b'.repeat(64),preview:{name:'Старый насос'}},explanation:'Изменить название по просьбе инженера',status:'proposed',result:null,expires_at:'2099-01-01T00:00:00Z',created_at:'2026-11-14T00:00:00Z'};
beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(api,'confirm').mockResolvedValue({...record,status:'succeeded'});vi.spyOn(api,'reject').mockResolvedValue({...record,status:'rejected'});});
function show(action=record){const changed=vi.fn();render(<MemoryRouter><ActionCard action={action} title="Изменить оборудование" onChanged={changed}/></MemoryRouter>);return changed;}
it('distinguishes an acknowledged write from a verified postcondition',()=>{
  show({...record,status:'succeeded',result:{data:{revision:3},verification:{status:'unverified',summary:'Нужна проверка состояния данных.'}}});
  expect(screen.getByRole('status')).toHaveTextContent('Запись выполнена; результат требует проверки');
  expect(screen.queryByText('Выполнено и проверено')).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Подтвердить и выполнить'})).not.toBeInTheDocument();
});
it('shows exact parameters and requires human consent before confirming the stored hash',async()=>{
  const user=userEvent.setup(),changed=show();expect(screen.getByText('Новый насос')).toBeVisible();
  const button=screen.getByRole('button',{name:'Подтвердить и выполнить'});expect(button).toBeDisabled();expect(api.confirm).not.toHaveBeenCalled();
  await user.click(screen.getByRole('checkbox'));await user.click(button);
  expect(api.confirm).toHaveBeenCalledExactlyOnceWith(record);expect(changed).toHaveBeenCalledOnce();
});
it('rejects without approving and preserves the immutable proposal after an error',async()=>{
  const user=userEvent.setup();vi.mocked(api.confirm).mockRejectedValue(new Error('Данные изменились'));
  show();await user.click(screen.getByRole('checkbox'));await user.click(screen.getByRole('button',{name:'Подтвердить и выполнить'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Данные изменились');
  await user.click(screen.getByRole('button',{name:'Отклонить'}));expect(api.reject).toHaveBeenCalledWith('action');
});
it('never offers another execution for completed, uncertain or expired proposals',()=>{
  show({...record,status:'uncertain'});expect(screen.queryByRole('button',{name:'Подтвердить и выполнить'})).not.toBeInTheDocument();
  expect(screen.getByText(/Повторное подтверждение не запустит/)).toBeVisible();
});
it('renders injected HTML as text',()=>{
  show({...record,explanation:'<img src=x onerror=alert(1)>'});
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();expect(document.querySelector('img')).toBeNull();
});
it('collects a protected input only in confirmation and keeps the stored proposal unchanged',async()=>{
  const user=userEvent.setup();const action={...record,tool_name:'profile_email',secret_fields:['current_password'],arguments:{body:{email:'test@example.test',current_password:'__human_secret__'}}};
  show(action);const input=screen.getByLabelText(/Текущий пароль/);expect(input).toHaveAttribute('type','password');
  await user.click(screen.getByRole('checkbox'));expect(screen.getByRole('button',{name:'Подтвердить и выполнить'})).toBeDisabled();
  await user.type(input,'TEST-ONLY-PROTECTED');await user.click(screen.getByRole('button',{name:'Подтвердить и выполнить'}));
  expect(api.confirm).toHaveBeenCalledWith(action,{current_password:'TEST-ONLY-PROTECTED'});
  expect(action.arguments.body.current_password).toBe('__human_secret__');
});
