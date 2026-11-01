import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";
import { AuthLayout } from "./AuthLayout";
import { ApiError } from "@/shared/api/request";

const { signIn, renderScene } = vi.hoisted(() => ({ signIn: vi.fn(), renderScene: vi.fn((_props: { animationEnabled: boolean }) => null) }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: null, loading: false, signIn }) }));
vi.mock("@/features/auth/AuroraScene", () => ({ AuroraScene: renderScene }));
vi.mock("@/shared/api/request", async importOriginal => ({ ...await importOriginal<typeof import("@/shared/api/request")>(), DEMO_MODE: false }));
beforeEach(() => { signIn.mockReset(); });
function Location() { const location = useLocation(); return <output>{location.pathname + location.search + location.hash}</output>; }
it("keeps the background setting in Help rather than on the scene and forwards its state", () => {
  render(<MemoryRouter initialEntries={["/login"]}><Routes><Route element={<AuthLayout />}><Route path="/login" element={<LoginPage />} /></Route></Routes></MemoryRouter>);
  expect(screen.queryByRole("checkbox", { name: "Анимация фона" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Обратитесь к администратору/ }));
  const checkbox = screen.getByRole("checkbox", { name: "Анимация фона" });
  expect(checkbox).toBeChecked();
  fireEvent.click(checkbox);
  expect(checkbox).not.toBeChecked();
  expect(renderScene.mock.calls.at(-1)?.[0]).toEqual(expect.objectContaining({ animationEnabled: false }));
});
it("shows only credentials initially and requires the existing site payload after a server requirement", async () => {
  signIn.mockRejectedValueOnce(new Error("Укажите site_id: несколько объектов"));
  signIn.mockResolvedValueOnce({ role: "dispatcher" });
  const view = render(<MemoryRouter><LoginPage /></MemoryRouter>);
  expect(view.container.querySelector("details, summary")).toBeNull();
  expect(screen.queryByLabelText("ID объекта")).toBeNull();
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "person@example.test" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "password" } });
  fireEvent.submit(screen.getByRole("form"));
  const site = await screen.findByLabelText("ID объекта");
  expect(site).toBeRequired();
  expect(signIn).toHaveBeenLastCalledWith("person@example.test", "password", "");
  fireEvent.change(site, { target: { value: " 00000000-0000-4000-8000-000000000001 " } });
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(signIn).toHaveBeenLastCalledWith("person@example.test", "password", "00000000-0000-4000-8000-000000000001"));
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

it("validates on blur and corrects inline errors while preserving a short raw login password", async () => {
  signIn.mockRejectedValueOnce(new ApiError(401, "Неверный email или пароль"));
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  const email=screen.getByLabelText("Email");
  fireEvent.change(email,{target:{value:"not-an-email"}});
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.blur(email);
  expect(email).toHaveAccessibleDescription("Введите корректный email");
  fireEvent.change(email,{target:{value:" person@example.test "}});
  expect(email).not.toHaveAttribute("aria-invalid");
  fireEvent.change(screen.getByLabelText("Пароль"),{target:{value:" x "}});
  fireEvent.submit(screen.getByRole("form"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Неверный email или пароль");
  expect(signIn).toHaveBeenCalledWith("person@example.test"," x ","");
});

it("reveals a server-invalid site and focuses it after the fieldset becomes enabled", async () => {
  signIn.mockRejectedValueOnce(new ApiError(422,"Проверьте заполнение полей формы",[{field:"body.site_id",issue:"UUID parsing failed"}]));
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"),{target:{value:"person@example.test"}});
  fireEvent.change(screen.getByLabelText("Пароль"),{target:{value:"password"}});
  fireEvent.submit(screen.getByRole("form"));
  const site=await screen.findByLabelText("ID объекта");
  await waitFor(()=>expect(site).toHaveFocus());
  expect(site).toBeEnabled();
  expect(site).toHaveAttribute("aria-invalid","true");
  expect(site).toHaveAccessibleDescription("Введите ID объекта");
});

it.each(["/equipment?source=login#list", "//external.test", "/login?retry=1"])("preserves the existing safe redirect rule for %s", async from => {
  signIn.mockResolvedValueOnce({ role: "dispatcher" });
  render(<MemoryRouter initialEntries={[{ pathname: "/login", state: { from } }]}><LoginPage /><Location /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "person@example.test" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "password" } });
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(from === "/equipment?source=login#list" ? from : "/dispatcher"));
});
