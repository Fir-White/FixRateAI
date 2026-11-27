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

  it("links to the open queue and calendar from a compact workday", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-30T09:00:00Z"));
    vi.spyOn(maintenanceApi, "listTasks").mockResolvedValue([
      task("task-1", { mandatoryDueDate: "2026-10-30" }), task("task-2", { state: "assigned", mandatoryDueDate: "2026-10-30" }),
      task("cancelled", { state: "cancelled" }), task("next-week", { mandatoryDueDate: "2026-11-10" }),
    ]);
    const comparisons = vi.spyOn(maintenanceApi, "listComparisons").mockResolvedValue([]);
    render(<MemoryRouter><DispatcherPage /></MemoryRouter>);

    await screen.findByRole("heading", { name: "Рабочий день диспетчера" });
    const signals = screen.getByRole("group", { name: "Сроки и назначения" });
    expect(within(signals).getByRole("link", { name: /3 незавершённые работы/ })).toHaveAttribute("href", "/tasks?status=open");
    expect(screen.getByRole("heading", { name: "Ближайшие задания" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Открыть график" })).toHaveAttribute("href", "/calendar?date=2026-10-30");
    expect(screen.queryByLabelText("Выбор дня недели")).not.toBeInTheDocument();
    expect(comparisons).not.toHaveBeenCalled();
  });

  it("keeps restricted task, calendar and forecast links unavailable to an administrator", async () => {
    session.role = "admin";
    vi.spyOn(maintenanceApi, "listTasks").mockResolvedValue([task("task-1")]);
    vi.spyOn(maintenanceApi, "listComparisons").mockResolvedValue([]);
    render(<MemoryRouter><DispatcherPage /></MemoryRouter>);
    await screen.findByRole("heading", { name: "Рабочее пространство" });
    expect(screen.queryByRole("link", { name: /очередь заданий/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /открыть полный календарь/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /открыть сравнение/i })).not.toBeInTheDocument();
  });
});
