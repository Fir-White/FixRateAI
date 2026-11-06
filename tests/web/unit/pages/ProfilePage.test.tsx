import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ProfilePage } from "@/pages/ProfilePage";
const mocks=vi.hoisted(()=>({updateEmail:vi.fn(),logout:vi.fn(),request:vi.fn()}));
vi.mock("@/shared/session/SessionContext",()=>({useSession:()=>({profile:{userId:"1",name:"Андрей Смирнов",email:"user@example.test",role:"executive",siteName:"Объект",timezone:"Asia/Yekaterinburg"},updateEmail:mocks.updateEmail,logout:mocks.logout})}));
vi.mock("@/shared/api/request",()=>({DEMO_MODE:false,request:mocks.request}));
beforeEach(()=>{mocks.updateEmail.mockReset();mocks.logout.mockReset();mocks.request.mockReset();});
it("keeps the name read-only and changes email with the current password",async()=>{
  mocks.updateEmail.mockResolvedValueOnce(undefined);render(<MemoryRouter><ProfilePage/></MemoryRouter>);
  expect(screen.queryByRole("textbox",{name:"Имя и фамилия"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Изменить"}));
  const form=screen.getByRole("form",{name:"Изменить email"});
  fireEvent.change(within(form).getByLabelText("Email"),{target:{value:"new@example.test"}});
  fireEvent.change(within(form).getByLabelText("Текущий пароль"),{target:{value:"old pass"}});
  fireEvent.submit(form);await waitFor(()=>expect(mocks.updateEmail).toHaveBeenCalledWith("new@example.test","old pass"));
  expect(await screen.findByRole("status")).toHaveTextContent("Email изменён");
});
it("validates password confirmation before sending and submits matching values",async()=>{
  mocks.request.mockResolvedValueOnce({updated:true});render(<MemoryRouter><ProfilePage/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"Изменить пароль"}));
  const form=screen.getByRole("form",{name:"Изменить пароль"});
  fireEvent.change(within(form).getByLabelText("Старый пароль"),{target:{value:"old pass"}});
  fireEvent.change(within(form).getByLabelText("Новый пароль"),{target:{value:"long-password-123"}});
  fireEvent.change(within(form).getByLabelText("Подтвердите новый пароль"),{target:{value:"different-pass"}});
  fireEvent.submit(form);expect(mocks.request).not.toHaveBeenCalled();expect(within(form).getByText("Пароли не совпадают")).toBeInTheDocument();
  fireEvent.change(within(form).getByLabelText("Подтвердите новый пароль"),{target:{value:"long-password-123"}});
  fireEvent.submit(form);await waitFor(()=>expect(mocks.request).toHaveBeenCalledOnce());
  expect(await screen.findByRole("status")).toHaveTextContent("Пароль изменён");
  expect(screen.queryByLabelText("Новый пароль")).not.toBeInTheDocument();
});
it("reports a server error without claiming a password change",async()=>{
  mocks.request.mockRejectedValueOnce(new Error("Неверный текущий пароль"));render(<MemoryRouter><ProfilePage/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"Изменить пароль"}));
  const form=screen.getByRole("form",{name:"Изменить пароль"});
  fireEvent.change(within(form).getByLabelText("Старый пароль"),{target:{value:"wrong"}});
  fireEvent.change(within(form).getByLabelText("Новый пароль"),{target:{value:"long-password-123"}});
  fireEvent.change(within(form).getByLabelText("Подтвердите новый пароль"),{target:{value:"long-password-123"}});
  fireEvent.submit(form);expect(await within(form).findByRole("alert")).toHaveTextContent("Неверный текущий пароль");
});

it("clears sensitive fields when cancelling",()=>{
  render(<MemoryRouter><ProfilePage/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"Изменить пароль"}));
  fireEvent.change(screen.getByLabelText("Старый пароль"),{target:{value:"secret"}});
  fireEvent.change(screen.getByLabelText("Новый пароль"),{target:{value:"long-password-123"}});
  fireEvent.click(screen.getByRole("button",{name:"Отмена"}));
  fireEvent.click(screen.getByRole("button",{name:"Изменить пароль"}));
  expect(screen.getByLabelText("Старый пароль")).toHaveValue("");
  expect(screen.getByLabelText("Новый пароль")).toHaveValue("");
});
it("prevents repeated submission while an email update is pending",async()=>{
  let finish!:()=>void;
  mocks.updateEmail.mockReturnValueOnce(new Promise<void>(resolve=>{finish=resolve;}));
  render(<MemoryRouter><ProfilePage/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"Изменить"}));
  fireEvent.change(screen.getByLabelText("Email"),{target:{value:"new@example.test"}});
  fireEvent.change(screen.getByLabelText("Текущий пароль"),{target:{value:"secret"}});
  const form=screen.getByRole("form",{name:"Изменить email"});
  fireEvent.submit(form);fireEvent.submit(form);
  expect(mocks.updateEmail).toHaveBeenCalledTimes(1);
  finish();await screen.findByRole("status");
});

it("shows the password length requirement and limits both new password fields",()=>{
  render(<MemoryRouter><ProfilePage/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"Изменить пароль"}));
  expect(screen.getByText("От 12 до 64 символов")).toBeInTheDocument();
  expect(screen.getByLabelText("Новый пароль")).toHaveAttribute("maxLength", "64");
  expect(screen.getByLabelText("Подтвердите новый пароль")).toHaveAttribute("maxLength", "64");
});
