import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { LoginPage } from "@/pages/LoginPage";
import { AuthLayout } from "@/pages/AuthLayout";
import { RegistrationPage } from "@/pages/RegistrationPage";
import { ApiError } from "@/shared/api/request";
import userEvent from "@testing-library/user-event";

const { signIn, renderScene } = vi.hoisted(() => ({ signIn: vi.fn(), renderScene: vi.fn((_props: { onReducedMotionChange?: (reduced: boolean) => void }) => null) }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: null, loading: false, signIn }) }));
vi.mock("@/features/auth/AuroraScene", () => ({ AuroraScene: renderScene }));
vi.mock("@/shared/api/request", async importOriginal => ({ ...await importOriginal<typeof import("@/shared/api/request")>(), DEMO_MODE: false }));
beforeEach(() => { signIn.mockReset(); });
function Location() { const location = useLocation(); return <output>{location.pathname + location.search + location.hash}</output>; }
it.each([
  ["/login","Не получается войти?","Обратитесь к администратору вашего объекта для восстановления доступа."],
  ["/register","Нужна помощь с регистрацией?","Обратитесь к администратору вашего объекта."],
])("shows static help on %s without a help dialog or a user animation switch", (path,title,description) => {
  const view=render(<MemoryRouter initialEntries={[path]}><Routes><Route element={<AuthLayout />}><Route path="/login" element={<LoginPage />} /><Route path="/register" element={<RegistrationPage />} /></Route></Routes></MemoryRouter>);
  const footer=within(view.container.querySelector(".auth-footer")!);
  expect(footer.getByText(title)).toBeVisible();expect(footer.getByText(description)).toBeVisible();
  expect(footer.queryByRole("button")).toBeNull();expect(footer.queryByRole("link")).toBeNull();
  expect(screen.queryByRole("dialog")).toBeNull();expect(screen.queryByRole("checkbox")).toBeNull();
  expect(renderScene.mock.calls.at(-1)?.[0]).not.toHaveProperty("animationEnabled");
  expect(renderScene.mock.calls.at(-1)?.[0]).toMatchObject({onReducedMotionChange:expect.any(Function)});
});
it("enters the role workspace with only email and password", async () => {
  signIn.mockResolvedValueOnce({ role: "dispatcher" });
  render(<MemoryRouter initialEntries={["/login"]}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/dispatcher" element={<p>Рабочее пространство</p>} />
  </Routes></MemoryRouter>);
  expect(screen.queryByLabelText("ID объекта")).toBeNull();
  expect(screen.queryByLabelText("Здание")).toBeNull();
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "person@example.test" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "password" } });
  fireEvent.submit(screen.getByRole("form"));
  expect(await screen.findByText("Рабочее пространство")).toBeVisible();
  expect(signIn).toHaveBeenCalledExactlyOnceWith("person@example.test", "password");
});

it("shows all empty login errors after submit and focuses email without sending a request", () => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("form")).toHaveAttribute("novalidate");
  fireEvent.submit(screen.getByRole("form"));
  expect(signIn).not.toHaveBeenCalled();
  expect(screen.getAllByRole("alert")).toHaveLength(2);
  expect(screen.getByLabelText("Email")).toHaveFocus();
  expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Введите email");
  expect(screen.getByLabelText("Пароль")).toHaveAccessibleDescription("Введите пароль");
});

it('keeps unexplored and cleared fields neutral until submit, then checks required values on blur',async()=>{
  const user=userEvent.setup();render(<MemoryRouter><LoginPage/></MemoryRouter>);
  const email=screen.getByLabelText('Email'),password=screen.getByLabelText('Пароль');
  await user.click(email);await user.click(password);await user.click(screen.getByRole('heading'));
  expect(screen.queryByRole('alert')).toBeNull();
  expect(email).not.toHaveAttribute('data-validation');expect(password).not.toHaveAttribute('data-validation');
  await user.type(email,'incomplete');await user.clear(email);await user.click(password);
  expect(email).not.toHaveAttribute('aria-invalid');
  await user.click(screen.getByRole('button',{name:'Войти'}));
  expect(screen.getAllByRole('alert')).toHaveLength(2);expect(signIn).not.toHaveBeenCalled();
  await user.type(email,'a');
  expect(email).not.toHaveAttribute('aria-invalid');expect(email).not.toHaveAttribute('data-validation');
  await user.clear(email);await user.click(password);
  expect(email).toHaveAccessibleDescription('Введите email');
});

it('waits for completion of an edit before showing its error or success again',()=>{
  render(<MemoryRouter><LoginPage/></MemoryRouter>);
  const email=screen.getByLabelText('Email');
  fireEvent.change(email,{target:{value:'not-an-email'}});fireEvent.blur(email);
  expect(email).toHaveAttribute('aria-invalid','true');
  fireEvent.change(email,{target:{value:'still-not-an-email'}});
  expect(email).not.toHaveAttribute('aria-invalid');expect(email).not.toHaveAttribute('data-validation');
  fireEvent.blur(email);expect(email).toHaveAccessibleDescription('Введите корректный email');
  fireEvent.change(email,{target:{value:'person@example.test'}});
  expect(email).not.toHaveAttribute('data-validation');
  fireEvent.blur(email);expect(email).toHaveAttribute('data-validation','valid');
});

it("validates on blur and corrects inline errors while preserving a short raw login password", async () => {
  signIn.mockRejectedValueOnce(new ApiError(401, "Неверный email или пароль"));
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  const email=screen.getByLabelText("Email");
  expect(email).not.toHaveAttribute("data-validation");
  fireEvent.change(email,{target:{value:"not-an-email"}});
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.blur(email);
  expect(email).toHaveAccessibleDescription("Введите корректный email");
  expect(email).toHaveAttribute("data-validation","invalid");
  fireEvent.change(email,{target:{value:" person@example.test "}});
  expect(email).not.toHaveAttribute("aria-invalid");
  expect(email).not.toHaveAttribute("data-validation");
  fireEvent.blur(email,{relatedTarget:screen.getByLabelText("Пароль")});
  expect(email).toHaveAttribute("data-validation","valid");
  fireEvent.change(screen.getByLabelText("Пароль"),{target:{value:" x "}});
  fireEvent.submit(screen.getByRole("form"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Неверный email или пароль");
  expect(signIn).toHaveBeenCalledWith("person@example.test"," x ");
});

it("focuses a server-invalid email after the fieldset becomes enabled", async () => {
  signIn.mockRejectedValueOnce(new ApiError(422,"Проверьте заполнение полей формы",[{field:"body.email",issue:"Value error"}]));
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  const email=screen.getByLabelText("Email");
  fireEvent.change(email,{target:{value:"person@example.test"}});
  fireEvent.change(screen.getByLabelText("Пароль"),{target:{value:"password"}});
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(()=>expect(email).toHaveFocus());
  expect(email).toBeEnabled();
  expect(email).toHaveAttribute("aria-invalid","true");
  expect(email).toHaveAccessibleDescription("Проверьте email");
});

it("keeps null-relatedTarget pointer and compatibility mouse blur from moving a registration action", () => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  const password=screen.getByLabelText("Пароль");
  const link=screen.getByRole("link",{name:"Регистрация"});
  fireEvent.pointerDown(link);
  fireEvent.pointerUp(link);
  fireEvent.mouseDown(link);
  fireEvent.blur(password,{relatedTarget:null});
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.mouseUp(link);fireEvent.click(link);
});

it.each(["cancel","release outside","keyboard"])("does not let a %s action suppress the next ordinary field blur", action => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"),{target:{value:"unfinished"}});
  const link=screen.getByRole("link",{name:"Регистрация"});
  fireEvent.pointerDown(link);
  if(action==="cancel") fireEvent.pointerCancel(link);
  else if(action==="release outside") fireEvent.pointerUp(document.body);
  else fireEvent.keyDown(document,{key:"Tab"});
  fireEvent.blur(screen.getByLabelText("Email"),{relatedTarget:screen.getByLabelText("Пароль")});
  expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Введите корректный email");
});

it("keeps password visibility and first submit usable while deferring action-target blur checks", async () => {
  const user=userEvent.setup();render(<MemoryRouter><LoginPage /></MemoryRouter>);
  await user.click(screen.getByLabelText("Пароль"));
  await user.click(screen.getByRole("button",{name:"Показать пароль"}));
  expect(screen.getByLabelText("Пароль")).toHaveAttribute("type","text");
  expect(screen.queryByRole("alert")).toBeNull();
  await user.click(screen.getByLabelText("Пароль"));
  await user.click(screen.getByRole("button",{name:"Войти"}));
  expect(screen.getAllByRole("alert")).toHaveLength(2);
  expect(screen.getByLabelText("Email")).toHaveFocus();
  expect(signIn).not.toHaveBeenCalled();
});

it("keeps an action usable when keyboard focus leaves an empty input", () => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  fireEvent.blur(screen.getByLabelText("Пароль"),{relatedTarget:screen.getByRole("link",{name:"Регистрация"})});
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.blur(screen.getByLabelText("Email"),{relatedTarget:screen.getByLabelText("Пароль")});
  expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-invalid");
});

it.each(["before press","before release"])("ignores inherited fieldset disablement %s instead of retaining a gesture until a missing click", timing => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"),{target:{value:"unfinished"}});
  const fieldset=document.querySelector("fieldset")!;
  const eye=screen.getByRole("button",{name:"Показать пароль"}) as HTMLButtonElement;
  if(timing==="before press") fieldset.disabled=true;
  expect(eye.disabled).toBe(false);
  fireEvent.pointerDown(eye);
  fieldset.disabled=true;
  fireEvent.pointerUp(eye);
  fieldset.disabled=false;
  fireEvent.blur(screen.getByLabelText("Email"),{relatedTarget:null});
  expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Введите корректный email");
});

it.each([
  ["executor", "/executor"], ["engineer", "/engineer"], ["chief_engineer", "/chief-engineer"],
  ["director", "/director"], ["dispatcher", "/dispatcher"], ["admin", "/admin"],
])("opens the %s home after login even if a previous user left a protected route", async (role, home) => {
  signIn.mockResolvedValueOnce({ role });
  render(<MemoryRouter initialEntries={[{ pathname: "/login", state: { from: "/tasks?previous=user#details" } }]}><LoginPage /><Location /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "person@example.test" } });
  fireEvent.change(screen.getByLabelText("\u041f\u0430\u0440\u043e\u043b\u044c"), { target: { value: "password" } });
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(home));
});
