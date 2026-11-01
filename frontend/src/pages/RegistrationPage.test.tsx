import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,it,vi} from 'vitest';
import {RegistrationPage} from './RegistrationPage';

const register=vi.hoisted(()=>vi.fn());
vi.mock('@/shared/api/management',()=>({managementApi:{register}}));
beforeEach(()=>register.mockReset());

it('submits registration without letting the employee choose a role or signing them in',async()=>{
  register.mockResolvedValue({message:'Заявка ожидает выдачи роли'});
  const user=userEvent.setup();render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  await user.type(screen.getByLabelText('Имя и фамилия'),'Тестовый сотрудник');
  await user.type(screen.getByLabelText('Email'),'staff@example.test');
  await user.type(screen.getByLabelText('Пароль'),'Fixture-password-1234');
  await user.type(screen.getByLabelText('Подтвердите пароль'),'Fixture-password-1234');
  await user.type(screen.getByLabelText('Код компании'),'0123456789abcdef0123456789abcdef');
  await user.click(screen.getByRole('button',{name:'Зарегистрироваться'}));
  expect(await screen.findByText('Заявка ожидает выдачи роли')).toBeVisible();
  expect(register).toHaveBeenCalledTimes(1);
  expect(register.mock.calls[0][0]).toEqual({full_name:'Тестовый сотрудник',email:'staff@example.test',password:'Fixture-password-1234',company_code:'0123456789abcdef0123456789abcdef'});
  expect(register.mock.calls[0][0]).not.toHaveProperty('role');
  expect(screen.queryByLabelText('Пароль')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Подтвердите пароль')).not.toBeInTheDocument();
});


it('disables the form during the request and preserves entered data when registration fails',async()=>{
  let rejectRequest!: (error: Error) => void;
  register.mockReset();
  register.mockReturnValueOnce(new Promise((_,reject)=>{ rejectRequest=reject; }));
  const user=userEvent.setup();render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  await user.type(screen.getByLabelText('Имя и фамилия'),'Тестовый сотрудник');
  await user.type(screen.getByLabelText('Email'),'staff@example.test');
  await user.type(screen.getByLabelText('Пароль'),'Fixture-password-1234');
  await user.type(screen.getByLabelText('Подтвердите пароль'),'Fixture-password-1234');
  await user.type(screen.getByLabelText('Код компании'),'0123456789abcdef');
  await user.click(screen.getByRole('button',{name:'Зарегистрироваться'}));
  expect(screen.getByRole('form',{name:'Регистрация сотрудника'})).toHaveAttribute('aria-busy','true');
  expect(screen.getByLabelText('Имя и фамилия')).toBeDisabled();
  expect(screen.getByLabelText('Подтвердите пароль')).toBeDisabled();
  expect(screen.getByRole('button',{name:'Показать пароль'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Показать подтверждение пароля'})).toBeDisabled();
  expect(register).toHaveBeenCalledWith({full_name:'Тестовый сотрудник',email:'staff@example.test',password:'Fixture-password-1234',company_code:'0123456789abcdef'});
  rejectRequest(new Error('Недействительный код компании'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Недействительный код компании');
  await waitFor(()=>expect(screen.getByLabelText('Имя и фамилия')).toBeEnabled());
  expect(screen.getByLabelText('Код компании')).toHaveValue('0123456789abcdef');
  expect(screen.getByLabelText('Пароль')).toHaveValue('Fixture-password-1234');
  expect(screen.getByLabelText('Подтвердите пароль')).toHaveValue('Fixture-password-1234');
  expect(screen.getByRole('form',{name:'Регистрация сотрудника'})).toHaveAttribute('aria-busy','false');
});

it('blocks mismatched passwords, focuses an accessible error and recovers when the original password is corrected',async()=>{
  register.mockResolvedValue({message:'Заявка ожидает выдачи роли'});
  const user=userEvent.setup();render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  await user.type(screen.getByLabelText('Имя и фамилия'),'Тестовый сотрудник');
  await user.type(screen.getByLabelText('Email'),'staff@example.test');
  await user.type(screen.getByLabelText('Пароль'),'Fixture-password-1234');
  await user.type(screen.getByLabelText('Подтвердите пароль'),'Fixture-password-12345');
  await user.type(screen.getByLabelText('Код компании'),'0123456789abcdef');
  await user.click(screen.getByRole('button',{name:'Зарегистрироваться'}));
  const confirmation=screen.getByLabelText('Подтвердите пароль');
  expect(register).not.toHaveBeenCalled();
  expect(screen.getByRole('alert')).toHaveTextContent('Пароли не совпадают');
  expect(confirmation).toHaveFocus();
  expect(confirmation).toHaveAttribute('aria-invalid','true');
  expect(confirmation).toHaveAccessibleDescription('Пароли не совпадают');
  await user.type(screen.getByLabelText('Пароль'),'5');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(confirmation).not.toHaveAttribute('aria-invalid');
  await user.click(screen.getByRole('button',{name:'Зарегистрироваться'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Заявка ожидает выдачи роли');
  expect(register).toHaveBeenCalledOnce();
  expect(register.mock.calls[0][0].password).toBe('Fixture-password-12345');
});

it('shows and hides each password independently without submitting or changing its value',async()=>{
  const user=userEvent.setup();render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  const password=screen.getByLabelText('Пароль');
  const confirmation=screen.getByLabelText('Подтвердите пароль');
  await user.type(password,'Fixture-password-1234');
  await user.type(confirmation,'Fixture-password-1234');
  expect(password).toHaveAccessibleDescription('От 12 символов');
  expect(password).toHaveAttribute('type','password');
  expect(confirmation).toHaveAttribute('type','password');
  const showPassword=screen.getByRole('button',{name:'Показать пароль'});
  showPassword.focus();
  await user.keyboard(' ');
  expect(password).toHaveAttribute('type','text');
  expect(confirmation).toHaveAttribute('type','password');
  expect(screen.getByRole('button',{name:'Скрыть пароль'})).toHaveAttribute('aria-pressed','true');
  await user.click(screen.getByRole('button',{name:'Показать подтверждение пароля'}));
  expect(confirmation).toHaveAttribute('type','text');
  await user.click(screen.getByRole('button',{name:'Скрыть пароль'}));
  expect(password).toHaveAttribute('type','password');
  expect(confirmation).toHaveAttribute('type','text');
  await user.click(screen.getByRole('button',{name:'Скрыть подтверждение пароля'}));
  expect(confirmation).toHaveAttribute('type','password');
  expect(password).toHaveValue('Fixture-password-1234');
  expect(confirmation).toHaveValue('Fixture-password-1234');
  expect(register).not.toHaveBeenCalled();
});

it('requires confirmation before sending a registration request',async()=>{
  const user=userEvent.setup();render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  await user.type(screen.getByLabelText('Имя и фамилия'),'Тестовый сотрудник');
  await user.type(screen.getByLabelText('Email'),'staff@example.test');
  await user.type(screen.getByLabelText('Пароль'),'Fixture-password-1234');
  await user.type(screen.getByLabelText('Код компании'),'0123456789abcdef');
  await user.click(screen.getByRole('button',{name:'Зарегистрироваться'}));
  expect(register).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Подтвердите пароль')).toBeInvalid();
  expect(screen.getByLabelText('Подтвердите пароль')).toHaveAccessibleDescription('Повторите пароль');
  expect(screen.getByLabelText('Подтвердите пароль')).toHaveFocus();
});

it('shows all registration errors with the first field focused and no request or native validation',()=>{
  render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByRole('form')).toHaveAttribute('novalidate');
  fireEvent.submit(screen.getByRole('form'));
  expect(register).not.toHaveBeenCalled();
  expect(screen.getAllByRole('alert')).toHaveLength(5);
  expect(screen.getByLabelText('Имя и фамилия')).toHaveFocus();
  expect(screen.getByLabelText('Имя и фамилия')).toHaveAccessibleDescription('Введите имя и фамилию');
  expect(screen.getByLabelText('Код компании')).toHaveAccessibleDescription('Введите код компании');
});

it('revalidates blurred whitespace names and invalid email without marking untouched fields',()=>{
  render(<MemoryRouter><RegistrationPage/></MemoryRouter>);
  const name=screen.getByLabelText('Имя и фамилия');
  fireEvent.change(name,{target:{value:'   '}});fireEvent.blur(name);
  expect(name).toHaveAttribute('aria-invalid','true');
  expect(screen.getByLabelText('Пароль')).not.toHaveAttribute('aria-invalid');
  fireEvent.change(name,{target:{value:'Иван Иванов'}});
  expect(name).not.toHaveAttribute('aria-invalid');
  const email=screen.getByLabelText('Email');
  fireEvent.change(email,{target:{value:'person@company'}});fireEvent.blur(email);
  expect(email).toHaveAccessibleDescription('Введите корректный email');
  fireEvent.change(email,{target:{value:'person@company.ru'}});
  expect(email).not.toHaveAttribute('aria-invalid');
});
