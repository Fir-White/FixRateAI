import { render, screen, within } from "@testing-library/react";
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

  it("shows real due dates and opens the task queue when a day contains multiple tasks", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-02T09:00:00Z"));
    vi.spyOn(maintenanceApi, "listTasks").mockResolvedValue([
      task("task-1"), task("task-2", { state: "assigned" }),
      task("cancelled", { state: "cancelled" }), task("next-week", { mandatoryDueDate: "2026-11-10" }),
    ]);
    vi.spyOn(maintenanceApi, "listComparisons").mockResolvedValue([]);
    render(<MemoryRouter><DispatcherPage /></MemoryRouter>);

    await screen.findByRole("heading", { name: "Панель диспетчера" });
    const week = screen.getByRole("region", { name: "График заданий на неделю" });
    const combined = within(week).getByRole("link", { name: /заданий — 2/ });
    expect(combined).toHaveAttribute("href", "/tasks");
    expect(combined).toHaveClass("is-multiple");
    expect(within(week).queryByText("next-week")).not.toBeInTheDocument();
    expect(screen.getByText("Нет сохранённых сравнений")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть полный календарь →" })).toHaveAttribute("href", "/calendar");
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
