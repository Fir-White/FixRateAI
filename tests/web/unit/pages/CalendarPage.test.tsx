import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CalendarPage } from "@/pages/CalendarPage";
import type { CalendarPreview, Role } from "@/shared/types/domain";

const mocks = vi.hoisted(() => ({role: "dispatcher" as Role, list: vi.fn(), preview: vi.fn(), tasks: vi.fn()}));
vi.mock("@/shared/api/request", () => ({DEMO_MODE: false,request:vi.fn(async (url:string)=>url.includes("/schedule-matrix")?{rows:[],diagnostics:[]}:[])}));
vi.mock("@/shared/session/SessionContext", () => ({useSession: () => ({profile: {role: mocks.role, timezone: "Asia/Yekaterinburg"}})}));
vi.mock("@/shared/api/maintenance", () => ({maintenanceApi: {listCalendar: mocks.list, previewCalendar: mocks.preview, listTasks: mocks.tasks}}));

function preview(year: number, month: number): CalendarPreview {
  const day = `${year}-${String(month).padStart(2, "0")}-15`;
  return {year, month, timezone: "Asia/Yekaterinburg", calculatedAt: "2026-10-31T12:00:00Z",
    items: [{id: "new-date", occurrenceDate: day, equipmentId: "equipment", equipmentName: "Учебный узел",
      operationCode: "1.4", operationTitle: "Очистка", maintenanceType: "ТО2", status: "draft", isOverdue: false,
      requiresInput: false, taskId: null, explanation: "Дата задана явным годовым правилом.", earliestDate: day,
      mandatoryDueDate: day, deadlinePassed: false, crewSize: 2, rawNormValue: "60.000", normUnit: "unconfirmed",
      planningDurationMinutes: null, requiredPersonHours: null, dataOrigin: "synthetic_demo", isAssumption: true}],
    diagnostics: [{bindingId: "binding", equipmentName: "Учебный узел", operationCode: "1.4", operationTitle: "Очистка",
      dataOrigin: "synthetic_demo", status: "ok", code: null, explanation: "Указана одна из пяти дат года.",
      warnings: [], isAssumption: true, occurrencesCount: 1, totalPersonHours: null,
      totalPlanningPersonMinutes: null, nextDueDate: null},
      {bindingId: "missing", equipmentName: "Другой узел", operationCode: "1.5", operationTitle: "Проверка приборов",
      dataOrigin: "customer", status: "needs_input", code: "RULE_UNCONFIRMED", explanation: "Не задана опорная дата.",
      warnings: [], isAssumption: false, occurrencesCount: 0, totalPersonHours: null,
      totalPlanningPersonMinutes: null, nextDueDate: null}]};
}

function mount() { return render(<MemoryRouter><CalendarPage /></MemoryRouter>); }

beforeEach(() => {
  mocks.role = "dispatcher";
  mocks.list.mockReset().mockResolvedValue([]);
  mocks.tasks.mockReset().mockResolvedValue([]);
  mocks.preview.mockReset().mockImplementation(async (year, month) => preview(year, month));
});

describe("calendar generator integration", () => {
  it("requests a server preview, shows explanations and never presents it as an assigned task", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", {name: "Рассчитать график"}));
    expect(await screen.findByRole("heading", {name: "Результат по оборудованию и операциям"})).toBeInTheDocument();
    expect(mocks.preview).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Не задана опорная дата.")).toBeInTheDocument();
    expect(screen.getByText("Нужны данные")).toBeInTheDocument();
    expect(screen.getByText("DEMO / допущение")).toBeInTheDocument();
    const grid = screen.getByRole("region", {name: "Сетка календаря"});
    await user.click(within(grid).getByRole("button", {name: /15 .* Очистка/}));
    const details = screen.getByRole("dialog", {name: "Очистка"});
    expect(within(details).getByText("2 чел.")).toBeVisible();
    expect(within(details).getByText(/Единица не подтверждена/)).toBeVisible();
    expect(within(details).queryByRole("link", {name: /Открыть наряд/})).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", {name: "Сохранённый график"}));
    await waitFor(() => expect(screen.queryByRole("heading", {name: "Результат по оборудованию и операциям"})).not.toBeInTheDocument());
    expect(mocks.list).toHaveBeenCalledTimes(2);
  });

  it("recalculates for the new month and hides the old result while waiting", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", {name: "Рассчитать график"}));
    await screen.findByRole("heading", {name: "Результат по оборудованию и операциям"});
    const [year, month] = mocks.preview.mock.calls[0] as [number, number];
    let resolve!: (value: CalendarPreview) => void;
    mocks.preview.mockImplementationOnce(() => new Promise<CalendarPreview>(done => {resolve = done;}));
    await user.click(screen.getByRole("button", {name: "Следующий месяц"}));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Не задана опорная дата.")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Расчёт графика");
    const next = month === 12 ? [year + 1, 1] : [year, month + 1];
    resolve(preview(next[0], next[1]));
    await screen.findByText("Не задана опорная дата.");
    expect(mocks.preview).toHaveBeenLastCalledWith(next[0], next[1]);
  });

  it("shows API errors and allows another attempt", async () => {
    mocks.preview.mockRejectedValueOnce(new Error("База данных недоступна"));
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", {name: "Рассчитать график"}));
    await screen.findByText("База данных недоступна");
    await user.click(screen.getByRole("button", {name: "Пересчитать график"}));
    await screen.findByRole("heading", {name: "Результат по оборудованию и операциям"});
  });

  it("keeps generation unavailable to the executor", async () => {
    mocks.role = "executor";
    mount();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", {name: "Рассчитать график"})).not.toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it("opens an executor task from the saved calendar drawer", async () => {
    mocks.role = "executor";
    mocks.list.mockResolvedValue([{...preview(2026, 11).items[0], taskId: "assigned-task", status: "planned"}]);
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/calendar?date=2026-11-15"]}><CalendarPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", {name: /15 ноября.*Очистка/}));
    const details = screen.getByRole("dialog", {name: "Очистка"});
    expect(within(details).getByRole("link", {name: /Открыть наряд/})).toHaveAttribute("href", "/executor/tasks/assigned-task");
    expect(within(details).getByRole("link", {name: "Оборудование"})).toHaveAttribute("href", "/equipment/equipment");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
  });

});
