import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

const { signIn, renderScene } = vi.hoisted(() => ({ signIn: vi.fn(), renderScene: vi.fn((_props: { animationEnabled: boolean }) => null) }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: null, loading: false, signIn }) }));
vi.mock("@/features/auth/AuroraScene", () => ({ AuroraScene: renderScene }));
vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false }));
beforeEach(() => { signIn.mockReset(); });
function Location() { const location = useLocation(); return <output>{location.pathname + location.search + location.hash}</output>; }
it("keeps the background setting in Help rather than on the scene and forwards its state", () => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
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
  fireEvent.change(site, { target: { value: " site-id " } });
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(signIn).toHaveBeenLastCalledWith("person@example.test", "password", "site-id"));
});

it.each(["/equipment?source=login#list", "//external.test", "/login?retry=1"])("preserves the existing safe redirect rule for %s", async from => {
  signIn.mockResolvedValueOnce({ role: "dispatcher" });
  render(<MemoryRouter initialEntries={[{ pathname: "/login", state: { from } }]}><LoginPage /><Location /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "person@example.test" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "password" } });
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(from === "/equipment?source=login#list" ? from : "/dispatcher"));
});
