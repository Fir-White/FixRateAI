import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CrewSelectionPanel } from "@/features/assignment/CrewSelectionPanel";
import type { AssignmentContext, CrewSelection } from "@/shared/types/domain";

const mocks = vi.hoisted(() => ({context: vi.fn(), preview: vi.fn(), assign: vi.fn()}));
vi.mock("@/shared/api/maintenance", () => ({maintenanceApi: {assignmentContext: mocks.context, previewAssignment: mocks.preview, assignCrew: mocks.assign}}));

const context: AssignmentContext = {
  taskId: "task", expectedRevision: 3, timezone: "Asia/Yekaterinburg", status: "ready", code: null, explanation: "",
  crewSize: 2, durationMinutes: 60, durationBasis: "Подтверждено", rawNormValue: "60.000",
  earliestAt: "2026-11-01T00:00:00+05:00", deadlineAt: "2026-11-02T00:00:00+05:00",
  requiredQualifications: ["Допуск к узлу"], dataOrigin: "synthetic_demo",
  defaultStartLocal: "2026-11-01T09:00", defaultEndLocal: "2026-11-01T17:00",
  crewChoices: [{id: "crew", name: "Бригада 1"}],
};
const selected = ["Анна", "Борис"].map((name, index) => ({executorId: `worker-${index}`, name,
  status: "selected" as const, reasons: [], explanation: "Выбран по загрузке", loadMinutes: 0, earliestStart: "2026-11-01T09:00:00+05:00"}));
const result: CrewSelection = {
  context, status: "ok", code: null, explanation: "Есть общий свободный интервал", startAt: "2026-11-01T09:00:00+05:00",
  endAt: "2026-11-01T10:00:00+05:00", crewId: "crew", crewName: "Бригада 1", planningPersonMinutes: 120,
  selectedWorkers: selected, workers: [...selected, {executorId: "excluded", name: "Вера", status: "excluded",
    reasons: ["QUALIFICATION_MISMATCH"], explanation: "Нет требуемой квалификации.", loadMinutes: 180, earliestStart: null}],
  crews: [{id: "crew", name: "Бригада 1", available: true, explanation: "Есть полный состав"}],
  command: {schema_version: "maintenance-0.1", expected_revision: 3, executor_ids: ["worker-0", "worker-1"],
    start_at: "2026-11-01T09:00:00+05:00", end_at: "2026-11-01T10:00:00+05:00", reason: "Подбор"},
};

beforeEach(() => {
  mocks.context.mockReset().mockResolvedValue(context);
  mocks.preview.mockReset().mockResolvedValue(result);
  mocks.assign.mockReset().mockResolvedValue({task: {id: "task", state: "assigned", revision: 4}});
});

function mount() { return render(<CrewSelectionPanel taskId="task" onClose={vi.fn()} />); }

describe("crew selection", () => {
  it("requires validation after a dispatcher changes the proposed workers",async()=>{
    const user=userEvent.setup();mount();
    await user.click(await screen.findByRole('button',{name:'Найти бригаду'}));
    const checkbox=await screen.findByRole('checkbox',{name:'Выбрать: Анна'});
    await user.click(checkbox);
    expect(screen.getByRole('button',{name:'Подтвердить назначение'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'Проверить выбранный состав'})).toBeDisabled();
    await user.click(checkbox);
    expect(screen.getByRole('button',{name:'Подтвердить назначение'})).toBeDisabled();
    await user.click(screen.getByRole('button',{name:'Проверить выбранный состав'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Подтвердить назначение'})).toBeEnabled());
    expect(mocks.preview).toHaveBeenLastCalledWith('task',3,'2026-11-01T09:00','2026-11-01T17:00',null,['worker-1','worker-0'],false);
    expect(mocks.assign).not.toHaveBeenCalled();
  });
  it("uses server conditions, shows the complete team, daily load and exclusion reasons", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText(/Нужно 2 чел. на 60 мин./);
    expect(screen.getByText(/Asia\/Yekaterinburg/)).toBeVisible();
    expect(screen.getByText(/Исходная норма: 60.000/)).toBeVisible();
    expect(screen.getByText(/Предложение ещё не сохранено/)).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Состав"), "crew");
    await user.click(screen.getByRole("button", {name: "Найти бригаду"}));
    await screen.findByText("Полный состав найден");
    expect(mocks.preview).toHaveBeenCalledWith("task", 3, "2026-11-01T09:00", "2026-11-01T17:00", "crew");
    const team = screen.getAllByRole("list")[0];
    expect(within(team).getAllByRole("listitem")).toHaveLength(2);
    expect(within(team).getByText("Анна")).toBeVisible();
    expect(screen.getByText("Плановая загрузка: 120 чел.-мин.")).toBeVisible();
    expect(screen.getByText("Нет требуемой квалификации.")).toBeVisible();
    expect(screen.getByText("180 мин.")).toBeVisible();
  });

  it("explains unconfirmed inputs and does not offer a search", async () => {
    mocks.context.mockResolvedValue({...context, status: "needs_input", code: "DURATION_UNCONFIRMED", explanation: "Подтвердите длительность работы"});
    mount();
    await screen.findByText("Подтвердите длительность работы");
    expect(screen.queryByRole("button", {name: "Найти бригаду"})).not.toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it("renders an unavailable result without a partial selected team", async () => {
    mocks.preview.mockResolvedValue({...result, status: "unavailable", selectedWorkers: [], explanation: "Нет общего интервала", planningPersonMinutes: null});
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    await screen.findByText("Бригада не подобрана");
    expect(screen.getByText("Нет общего интервала")).toBeVisible();
    expect(screen.queryByText(/Плановая загрузка:/)).not.toBeInTheDocument();
  });

  it("shows API errors and permits another attempt", async () => {
    mocks.preview.mockRejectedValueOnce(new Error("REVISION_CONFLICT: обновите данные"));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("REVISION_CONFLICT");
    await user.click(screen.getByRole("button", {name: "Найти бригаду"}));
    await screen.findByText("Полный состав найден");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("discards an old response when the requested window changes", async () => {
    let resolve!: (value: CrewSelection) => void;
    mocks.preview.mockImplementationOnce(() => new Promise<CrewSelection>(done => {resolve = done;}));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledTimes(1));
    await user.click(screen.getByLabelText("Конец окна поиска"));
    fireEvent.change(screen.getByLabelText("Дата", {exact:true}), {target:{value:"02112026"}});
    await user.click(screen.getByRole("button", {name:"Применить"}));
    await act(async () => {resolve(result);});
    expect(screen.queryByText("Полный состав найден")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("rejects a reversed local window before calling the server", async () => {
    mocks.context.mockResolvedValue({...context, defaultEndLocal: "2026-11-01T08:00"});
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    await screen.findByText("Конец окна должен быть позже начала.");
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it("saves only the displayed complete proposal and reports success", async () => {
    const user = userEvent.setup();
    const onAssigned = vi.fn();
    render(<CrewSelectionPanel taskId="task" onClose={vi.fn()} onAssigned={onAssigned} />);
    expect(screen.queryByRole("button", {name: "Подтвердить назначение"})).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    await user.click(await screen.findByRole("button", {name: "Подтвердить назначение"}));
    expect(await screen.findByText("Бригада назначена")).toBeVisible();
    expect(mocks.assign).toHaveBeenCalledWith("task", result.command, "crew");
    expect(onAssigned).toHaveBeenCalledWith(expect.objectContaining({task: expect.objectContaining({revision: 4})}));
    expect(screen.queryByRole("button", {name: "Подтвердить назначение"})).not.toBeInTheDocument();
  });

  it("prevents double saves and changes while a save is pending", async () => {
    let resolve!: (value: unknown) => void;
    mocks.assign.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    await user.dblClick(await screen.findByRole("button", {name: "Подтвердить назначение"}));
    expect(mocks.assign).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", {name: "Сохранение…"})).toBeDisabled();
    expect(screen.getByRole("button", {name: "Закрыть подбор"})).toBeDisabled();
    expect(screen.getByLabelText("Состав")).toBeDisabled();
    expect(screen.getByLabelText("Начало окна поиска")).toBeDisabled();
    await act(async () => {resolve({task: {revision: 4}});});
    await screen.findByText("Бригада назначена");
  });

  it("discards a conflicted proposal, reloads context and requires a new search", async () => {
    mocks.assign.mockRejectedValueOnce(new Error("INSUFFICIENT_CAPACITY: повторите подбор"));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    await user.click(await screen.findByRole("button", {name: "Подтвердить назначение"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("INSUFFICIENT_CAPACITY");
    await waitFor(() => expect(mocks.context).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("button", {name: "Подтвердить назначение"})).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", {name: "Найти бригаду"}));
    await screen.findByRole("button", {name: "Подтвердить назначение"});
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("preserves the search window after a network failure and requires a fresh proposal", async () => {
    mocks.assign.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const user = userEvent.setup();
    mount();
    const start = await screen.findByLabelText("Начало окна поиска");
    await user.click(start);
    fireEvent.change(screen.getByLabelText("Дата", {exact:true}), {target:{value:"01112026"}});
    fireEvent.change(screen.getByLabelText("Часы"), {target:{value:"10"}});
    fireEvent.change(screen.getByLabelText("Минуты"), {target:{value:"00"}});
    await user.click(screen.getByRole("button", {name:"Применить"}));
    await user.click(screen.getByRole("button", {name: "Найти бригаду"}));
    await user.click(await screen.findByRole("button", {name: "Подтвердить назначение"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Сохранение не подтверждено");
    expect(screen.getByLabelText("Начало окна поиска")).toHaveTextContent("1 ноября 2026");
    expect(screen.getByLabelText("Начало окна поиска")).toHaveTextContent("10:00");
    expect(mocks.context).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", {name: "Подтвердить назначение"})).not.toBeInTheDocument();
    expect(screen.queryByText("Бригада назначена")).not.toBeInTheDocument();
  });
});
