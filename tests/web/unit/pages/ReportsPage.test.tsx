import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReportsPage, csvCell } from "@/pages/ReportsPage";
import { maintenanceApi } from "@/shared/api/maintenance";
import type { MaintenanceTask } from "@/shared/types/domain";

vi.mock("@/shared/session/SessionContext", () => ({
  useSession: () => ({ profile: { timezone: "UTC" } }),
}));

describe("reports", () => {
  afterEach(() => vi.restoreAllMocks());

  it("quotes CSV values and neutralizes spreadsheet formulas", () => {
    expect(csvCell('a;"b"')).toBe('"a;""b"""');
    expect(csvCell("  =1+1")).toBe('"\'  =1+1"');
    expect(csvCell("\t@SUM(A1)")).toBe('"\'\t@SUM(A1)"');
    expect(csvCell(null)).toBe('""');
  });

  it("summarizes actual task states and groups available tasks by operation", async () => {
    const base: MaintenanceTask = {
      id: "one", code: "A", title: "Проверка", operationCode: "1.1", state: "accepted",
      equipmentId: "eq-1", equipmentName: "Насос", maintenanceType: "ТО1", dataOrigin: "synthetic_demo",
      isOverdue: false, deadlineBreached: false, mandatoryDueDate: null, scheduledStart: null,
      scheduledEnd: null, crewSize: 1, assignees: [], activeExecutionId: null, revision: 1, summary: "",
    };
    const tasks: MaintenanceTask[] = [base, { ...base, id: "two", code: "B", state: "submitted" }];
    vi.spyOn(maintenanceApi, "listTasks").mockResolvedValue(tasks);
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    expect(await screen.findByText("1.1 · Проверка")).toBeInTheDocument();
    expect(screen.getByText("Количество доступных заданий, включая завершённые и отменённые.")).toBeInTheDocument();
    expect(screen.getByRole("button", {name:"Выгрузить задания CSV"})).toBeEnabled();
  });
});
