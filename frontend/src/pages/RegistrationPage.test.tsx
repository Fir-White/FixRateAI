import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {expect,it,vi} from 'vitest';
import {RegistrationPage} from './RegistrationPage';

const register=vi.hoisted(()=>vi.fn());
vi.mock('@/shared/api/management',()=>({managementApi:{register}}));

it('submits registration without letting the employee choose a role or signing them in',async()=>{
  register.mockResolvedValue({message:'Заявка ожидает выдачи роли'});
  const user=userEvent.setup();render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  await user.type(screen.getByLabelText('Имя и фамилия'),'Тестовый сотрудник');
  await user.type(screen.getByLabelText('Email'),'staff@example.test');
  await user.type(screen.getByLabelText('Пароль'),'Fixture-password-1234');
  await user.type(screen.getByLabelText('Код компании'),'0123456789abcdef0123456789abcdef');
  await user.click(screen.getByRole('button',{name:'Зарегистрироваться'}));
  expect(await screen.findByText('Заявка ожидает выдачи роли')).toBeVisible();
  expect(register).toHaveBeenCalledTimes(1);
  expect(register.mock.calls[0][0]).toMatchObject({full_name:'Тестовый сотрудник',email:'staff@example.test'});
  expect(register.mock.calls[0][0]).not.toHaveProperty('role');
  expect(screen.queryByLabelText('Пароль')).not.toBeInTheDocument();
});
