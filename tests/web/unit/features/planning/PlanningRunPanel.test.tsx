import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { PlanningRunPanel } from "@/features/planning/PlanningRunPanel";
import type { CalendarPreview, PlanningRun } from "@/shared/types/domain";

const mocks=vi.hoisted(() => ({generate:vi.fn()}));
vi.mock("@/shared/api/maintenance",() => ({maintenanceApi:{generateTasks:mocks.generate}}));
vi.mock("@/features/assignment/CrewSelectionPanel",() => ({CrewSelectionPanel:({onAssigned}:{onAssigned:()=>void}) =>
  <button onClick={() => onAssigned()}>Подтвердить состав</button>}));
const preview:CalendarPreview={year:2026,month:11,timezone:"Asia/Yekaterinburg",calculatedAt:"2026-11-01T08:00:00+05:00",
  generationToken:"token",items:[{id:"occ",occurrenceDate:"2026-11-02",equipmentId:"eq",equipmentName:"Узел",operationCode:"1.4",
    operationTitle:"Проверка",maintenanceType:"ТО2",status:"draft",isOverdue:false,requiresInput:false,taskId:null,
    explanation:"Правило",earliestDate:"2026-11-02",mandatoryDueDate:"2026-11-02",deadlinePassed:false,
    crewSize:2,rawNormValue:"2.000",normUnit:"person_hour",planningDurationMinutes:60,requiredPersonHours:"2.000",
    dataOrigin:"synthetic_demo",isAssumption:true}],diagnostics:[]};
const result:PlanningRun={runId:"run",year:2026,month:11,timezone:"Asia/Yekaterinburg",calculatedAt:preview.calculatedAt,
  replayed:false,createdCount:1,existingCount:0,warnings:[],diagnostics:[],items:[{occurrenceId:"occ",taskId:"task",
    equipmentName:"Узел",operationTitle:"Проверка",created:true,state:"draft",plannedDate:"2026-11-02",
    mandatoryDueDate:"2026-11-02",comparison:null,assignment:null}]};
beforeEach(() => {mocks.generate.mockReset().mockResolvedValue(result);});
function mount(value=preview,onRecalculate=vi.fn()) {
  return render(<MemoryRouter><PlanningRunPanel preview={value} onRecalculate={onRecalculate}/></MemoryRouter>);
}

it("saves the displayed month and offers existing assignment UI",async () => {
  const user=userEvent.setup(); mount();
  await user.click(screen.getByRole("button",{name:"Создать задания по расчёту"}));
  await screen.findByText("Результат создания заданий");
  expect(mocks.generate).toHaveBeenCalledWith(2026,11,"token",expect.any(String));
  expect(screen.getByRole("link",{name:"Открыть задание"})).toHaveAttribute("href","/tasks/task");
  expect(screen.getByText("Создан черновик задания")).toBeVisible();
  await user.click(screen.getByRole("button",{name:"Подобрать и назначить"}));
  await user.click(screen.getByRole("button",{name:"Подтвердить состав"}));
  expect(screen.getByText("Бригада назначена")).toBeVisible();
});

it("uses the same idempotency key when retrying an unknown network outcome",async () => {
  mocks.generate.mockRejectedValueOnce(new Error("Соединение прервано"));
  const user=userEvent.setup(); mount();
  await user.click(screen.getByRole("button",{name:"Создать задания по расчёту"}));
  await screen.findByRole("alert");
  await user.click(screen.getByRole("button",{name:"Создать задания по расчёту"}));
  await screen.findByText("Результат создания заданий");
  expect(mocks.generate.mock.calls[0]).toEqual(mocks.generate.mock.calls[1]);
});

it("prevents double submission while waiting",async () => {
  let resolve!:(value:PlanningRun)=>void;
  mocks.generate.mockImplementationOnce(() => new Promise<PlanningRun>(done => {resolve=done;}));
  const user=userEvent.setup(); mount();
  await user.dblClick(screen.getByRole("button",{name:"Создать задания по расчёту"}));
  expect(mocks.generate).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button",{name:"Создание заданий…"})).toBeDisabled();
  await act(async () => {resolve(result);});
  await screen.findByText("Результат создания заданий");
});

it("requires a fresh preview token and offers recalculation after a conflict",async () => {
  const user=userEvent.setup(); const refresh=vi.fn();
  mocks.generate.mockRejectedValueOnce(new Error("STALE_PREVIEW"));
  mount(preview,refresh);
  await user.click(screen.getByRole("button",{name:"Создать задания по расчёту"}));
  await screen.findByRole("alert");
  await user.click(screen.getByRole("button",{name:"Обновить расчёт"}));
  expect(refresh).toHaveBeenCalledTimes(1);
});
