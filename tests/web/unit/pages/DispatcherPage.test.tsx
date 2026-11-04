import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DispatcherPage } from "@/pages/DispatcherPage";
import { maintenanceApi } from "@/shared/api/maintenance";
import type { MaintenanceTask, Role } from "@/shared/types/domain";

const session = vi.hoisted(() => ({ role: "dispatcher" as Role }));
vi.mock("@/shared/session/SessionContext", () => ({
  useSession: () => ({ profile: { role: session.role, siteName: "Тестовый объект", timezone: "Asia/Yekaterinburg" } }),
}));

function task(id: string, overrides: Partial<MaintenanceTask> = {}): MaintenanceTask {
  return {
    id, code: id, title: "Проверка оборудования", equipmentId: "eq-1", equipmentName: "Насос",
    operationCode: "1.1", maintenanceType: "ТО1", state: "draft", isOverdue: false,
    deadlineBreached: false, mandatoryDueDate: "2026-11-02", scheduledStart: null,
    scheduledEnd: null, crewSize: 1, assignees: [], activeExecutionId: null, revision: 1,
    dataOrigin: "synthetic_demo", summary: "", ...overrides,
  };
}

describe("dispatcher overview", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); session.role = "dispatcher"; });

  it("shows the selected day's tasks and links to the same date in the queue", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-30T09:00:00Z"));
    vi.spyOn(maintenanceApi, "listTasks").mockResolvedValue([
      task("task-1", { mandatoryDueDate: "2026-10-30" }), task("task-2", { state: "assigned", mandatoryDueDate: "2026-10-30" }),
      task("cancelled", { state: "cancelled" }), task("next-week", { mandatoryDueDate: "2026-11-10" }),
    ]);
    vi.spyOn(maintenanceApi, "listComparisons").mockResolvedValue([]);
    render(<MemoryRouter><DispatcherPage /></MemoryRouter>);

    await screen.findByRole("heading", { name: "Панель диспетчера" });
    const day = screen.getByRole("region", { name: "30 октября пятница" });
    expect(within(day).getByText("Нарядов на выбранный день: 2")).toBeInTheDocument();
    expect(within(day).getByRole("link", {name: /task-1/})).toHaveAttribute("href", "/tasks/task-1");
    expect(within(day).getByRole("link", {name: /task-2/})).toHaveAttribute("href", "/tasks/task-2");
    expect(within(day).queryByText("next-week")).not.toBeInTheDocument();
    expect(screen.getByText("Пока нет результатов")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть график" })).toHaveAttribute("href", "/calendar?date=2026-10-30");
    expect(within(day).getByRole("link", {name: "Наряды дня →"})).toHaveAttribute("href", "/tasks?date=2026-10-30");
    await userEvent.setup().click(screen.getByRole("button", {name: "31 октября, нарядов: 0"}));
    expect(screen.getByText("На этот день работ нет")).toBeInTheDocument();
  });

  it("keeps restricted task, calendar and forecast links unavailable to an administrator", async () => {
    session.role = "admin";
    vi.spyOn(maintenanceApi, "listTasks").mockResolvedValue([task("task-1")]);
    vi.spyOn(maintenanceApi, "listComparisons").mockResolvedValue([]);
    render(<MemoryRouter><DispatcherPage /></MemoryRouter>);
    await screen.findByRole("heading", { name: "Панель диспетчера" });
    expect(screen.queryByRole("link", { name: /очередь заданий/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /открыть полный календарь/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /открыть сравнение/i })).not.toBeInTheDocument();
  });
});
