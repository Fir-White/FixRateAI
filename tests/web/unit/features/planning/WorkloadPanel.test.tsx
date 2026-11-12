import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { WorkloadPanel } from "@/features/planning/WorkloadPanel";
import { planningApi } from "@/shared/api/planning";
import type { WorkloadResponse } from "@/shared/types/planning";

vi.mock("@/shared/api/planning", () => ({ planningApi: {workload: vi.fn()} }));

function fixture(): WorkloadResponse {
  return {method_version: "workload-lower-bound-v1", site_id: "site", year: 2027, month: 1,
    timezone: "Asia/Yekaterinburg", calculated_at: "2027-01-01T00:00:00Z", capacity_hours_per_24h: "24",
    policy_status: "provisional", snapshot_sha256: "a".repeat(64), source_incomplete: false,
    total_occurrences: 1, unassigned_occurrences: 1, deficit_days: 1, incomplete_days: 0, diagnostics: [],
    days: [{date: "2027-01-05", total_person_hours: "40", known_person_hours: "40", unassigned_person_hours: "40",
      required_workers_lower_bound: 2, free_workers: 1, assigned_workers: 0, free_person_hours: "24",
      known_free_person_hours: "24", deficit_person_hours: "16", unknown_norms: 0, unknown_workers: 0,
      status: "hours_deficit", occurrences: [{occurrence_id: "occurrence", date: "2027-01-05", equipment_name: "Насос №1",
        operation_title: "Квартальное ТО", data_origin: "synthetic_demo", person_hours: "40", crew_size: 2,
        state: "unassigned", assigned_worker_ids: []}]}]};
}

beforeEach(() => {vi.mocked(planningApi.workload).mockReset().mockResolvedValue(fixture());});

it("shows backend hours and staffing lower bounds with work-level explanations", async () => {
  const user = userEvent.setup();
  render(<WorkloadPanel year={2027} month={1}/>);
  expect(await screen.findByText("Не хватает часов")).toBeVisible();
  expect(planningApi.workload).toHaveBeenCalledWith(2027, 1, "24");
  expect(screen.getByText("16 чел.-ч")).toBeVisible();
  expect(screen.getByText(/Количество людей — нижняя оценка/)).toBeVisible();
  await user.click(screen.getByText("Работы и основания расчёта (1)"));
  expect(screen.getByText("Квартальное ТО")).toBeVisible();
});

it("recalculates only after submission and hides the old numbers while waiting", async () => {
  const user = userEvent.setup();
  render(<WorkloadPanel year={2027} month={1}/>);
  await screen.findByText("Не хватает часов");
  const input = screen.getByLabelText("Полезные часы за 24 часа присутствия");
  await user.clear(input); await user.type(input, "12");
  expect(planningApi.workload).toHaveBeenCalledTimes(1);
  let resolve!: (value: WorkloadResponse) => void;
  vi.mocked(planningApi.workload).mockImplementationOnce(() => new Promise(done => {resolve = done;}));
  await user.click(screen.getByRole("button", {name: "Пересчитать нагрузку"}));
  await waitFor(() => expect(planningApi.workload).toHaveBeenLastCalledWith(2027, 1, "12"));
  expect(screen.queryByText("16 чел.-ч")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Расчёт нагрузки");
  resolve(fixture()); await screen.findByText("Не хватает часов");
});

it("preserves unknown values and displays incomplete source diagnostics", async () => {
  const data = fixture(); data.source_incomplete = true; data.incomplete_days = 1;
  Object.assign(data.days[0], {status: "incomplete", total_person_hours: null, unassigned_person_hours: null,
    required_workers_lower_bound: null, free_person_hours: null, deficit_person_hours: null,
    unknown_norms: 1, unknown_workers: 1});
  vi.mocked(planningApi.workload).mockResolvedValue(data);
  render(<WorkloadPanel year={2027} month={1}/>);
  expect(await screen.findByText("Нужны данные")).toBeVisible();
  expect(screen.getByText(/Часть регламентов не рассчитана/)).toBeVisible();
  expect(screen.getAllByText("Неизвестно")).toHaveLength(5);
});

it("supports retry after an error and reloads for a different month", async () => {
  vi.mocked(planningApi.workload).mockRejectedValueOnce(new Error("Расчёт временно недоступен"));
  const user = userEvent.setup();
  const view = render(<WorkloadPanel year={2027} month={1}/>);
  await screen.findByText("Расчёт временно недоступен");
  await user.click(screen.getByRole("button", {name: "Пересчитать нагрузку"}));
  await screen.findByText("Не хватает часов");
  view.rerender(<WorkloadPanel year={2027} month={2}/>);
  await waitFor(() => expect(planningApi.workload).toHaveBeenLastCalledWith(2027, 2, "24"));
});
