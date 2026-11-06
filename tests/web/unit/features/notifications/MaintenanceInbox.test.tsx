import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MaintenanceInbox } from "@/features/notifications/MaintenanceInbox";
import { request } from "@/shared/api/request";

vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false, request: vi.fn() }));
let role = "engineer";
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { userId: "u1", role, timezone: "Asia/Yekaterinburg" } }) }));
const messages = [
  { id: "1", message: "Фотоотчёт ожидает приёмки", taskId: "task-1", createdAt: "2026-11-05T12:00:00Z", readAt: null },
  { id: "2", message: "Просрочено ТО", taskId: "task-2", createdAt: "2026-11-05T11:00:00Z", readAt: null },
  { id: "3", message: "Работа принята", taskId: null, createdAt: "2026-11-04T11:00:00Z", readAt: "2026-11-05T12:00:00Z" },
];
const api = vi.mocked(request);
function setup() { return render(<MemoryRouter initialEntries={["/quality"]}><MaintenanceInbox/><Routes><Route path="/tasks/:id" element={<p>Карточка задания</p>}/><Route path="/executor/tasks/:id" element={<p>Задание исполнителя</p>}/></Routes></MemoryRouter>); }
beforeEach(() => { role = "engineer"; api.mockReset(); api.mockResolvedValue(messages); });
afterEach(() => { vi.useRealTimers(); });

describe("notifications", () => {
  it("groups unread and read events, formats time and closes with Escape", async () => {
    const user = userEvent.setup(); setup();
    const trigger = await screen.findByRole("button", { name: "Уведомления, непрочитанных: 2" });
    await user.click(trigger);
    const panel = screen.getByRole("dialog", { name: "Уведомления" });
    expect(within(panel).getByRole("heading", { name: "Новые 2" })).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: "Прочитанные 1" })).toBeInTheDocument();
    expect(within(panel).getByText("Фотоотчёт ожидает приёмки")).toBeInTheDocument();
    expect(panel.querySelector("time")).toHaveTextContent("17:00");
    await user.keyboard("{Escape}"); expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(trigger).toHaveFocus();
  });
  it("keeps the bell visible for an empty list and closes on outside click", async () => {
    api.mockResolvedValue([]);const user = userEvent.setup();setup();
    await user.click(await screen.findByRole("button", { name: "Уведомления, непрочитанных: 0" }));
    expect(screen.getByText("Пока всё спокойно")).toBeInTheDocument();fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("surfaces loading errors and retries", async () => {
    api.mockRejectedValueOnce(new Error("network"));const user=userEvent.setup();setup();
    await user.click(await screen.findByRole("button",{name:/Уведомления/}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось загрузить");
    api.mockResolvedValueOnce(messages);await user.click(screen.getByRole("button",{name:"Повторить"}));
    expect(await screen.findByText("Фотоотчёт ожидает приёмки")).toBeInTheDocument();expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("marks only acknowledged events and reports a partial failure", async () => {
    const user=userEvent.setup();setup();await user.click(await screen.findByRole("button",{name:"Уведомления, непрочитанных: 2"}));
    api.mockResolvedValueOnce({read:true}).mockRejectedValueOnce(new Error("network"));
    await user.click(screen.getByRole("button",{name:"Прочитать показанные"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось отметить");
    expect(screen.getByRole("button",{name:"Уведомления, непрочитанных: 1"})).toBeInTheDocument();
    expect(within(screen.getByRole("region",{name:"Новые"})).getByText("Просрочено ТО")).toBeInTheDocument();
    expect(api).toHaveBeenCalledWith("/api/v1/maintenance/notifications/1/read",expect.objectContaining({method:"POST"}));
    expect(api).toHaveBeenCalledWith("/api/v1/maintenance/notifications/2/read",expect.objectContaining({method:"POST"}));
  });
  it("does not mark a notification read without a positive server acknowledgement", async () => {
    const user=userEvent.setup();setup();await user.click(await screen.findByRole("button",{name:"Уведомления, непрочитанных: 2"}));
    api.mockResolvedValueOnce({read:false});await user.click(screen.getAllByRole("button",{name:"Отметить прочитанным"})[0]);
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось отметить");
    expect(screen.getByRole("button",{name:"Уведомления, непрочитанных: 2"})).toBeInTheDocument();
  });
  it("does not let an older refresh restore an already read notification", async () => {
    vi.useFakeTimers();let resolveOld!: (value: unknown) => void;
    api.mockResolvedValueOnce(messages).mockReturnValueOnce(new Promise(resolve=>{resolveOld=resolve;})).mockResolvedValueOnce({read:true});
    setup();await act(async()=>{await Promise.resolve();});fireEvent.click(screen.getByRole("button",{name:"Уведомления, непрочитанных: 2"}));
    await act(async()=>{await vi.advanceTimersByTimeAsync(30_000);});
    await act(async()=>{fireEvent.click(screen.getAllByRole("button",{name:"Отметить прочитанным"})[0]);await Promise.resolve();});
    await act(async()=>{resolveOld(messages);await Promise.resolve();});
    expect(screen.getByRole("button",{name:"Уведомления, непрочитанных: 1"})).toBeInTheDocument();
  });
  it("opens the assigned task through the executor route and marks it read", async () => {
    role="executor";const user=userEvent.setup();setup();await user.click(await screen.findByRole("button",{name:"Уведомления, непрочитанных: 2"}));
    api.mockResolvedValueOnce({read:true});await user.click(screen.getAllByRole("link",{name:/Открыть задание/})[0]);
    expect(await screen.findByText("Задание исполнителя")).toBeInTheDocument();
    await waitFor(()=>expect(screen.getByRole("button",{name:"Уведомления, непрочитанных: 1"})).toBeInTheDocument());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
