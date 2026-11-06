import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { WorkforceSettingsPage } from "@/pages/WorkforceSettingsPage";
import { managementApi } from "@/shared/api/management";
import type { Workforce, ShiftRule } from "@/shared/types/management";

vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false, request: vi.fn() }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { role: "engineer", timezone: "Asia/Yekaterinburg" } }) }));

let fixture: Workforce;
beforeEach(() => {
  vi.restoreAllMocks();
  fixture = { timezone: "Asia/Yekaterinburg", crews: [], skills: [], applications: [], staff: [{
    user_id: "worker", full_name: "Тестовый исполнитель", email: "fixture@example.test", role: "executor", is_active: true, revision: 1,
    employed_from: "2026-01-01", employed_until: null, qualifications: [], exceptions: [], shifts: [{
      shift_rule_id: "existing", revision: 7, label: "Сохранённая смена", valid_from: "2026-01-01", valid_until: "2027-01-01",
      starts_local: "22:00", ends_local: "06:00", is_active: true, status: "available",
      pattern: { frequency: "week", anchor_date: "2026-01-01", excluded_dates: ["2026-11-10"] } as ShiftRule["pattern"],
    }],
  }] };
  vi.spyOn(managementApi, "workforce").mockImplementation(async () => structuredClone(fixture));
  vi.spyOn(managementApi, "workerCalendar").mockResolvedValue({ intervals: [], diagnostics: [] });
});

async function openExisting() {
  const user = userEvent.setup();
  render(<MemoryRouter><WorkforceSettingsPage /></MemoryRouter>);
  await user.selectOptions(await screen.findByLabelText("Сотрудник"), "worker");
  await user.click(screen.getByRole("button", { name: "Изменить смену" }));
  return user;
}

it("opens, edits and reopens a sparse existing shift, preserving ID, revision, exclusions and overnight hours", async () => {
  const save = vi.spyOn(managementApi, "saveShift").mockImplementation(async (_, body) => {
    fixture.staff[0].shifts[0] = { ...body, revision: 8 };
  });
  const user = await openExisting();
  expect(save).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Пн")).not.toBeChecked();
  expect(screen.getByLabelText("Начало смены")).toHaveValue("22:00");
  expect(screen.getByLabelText("Роль сотрудника")).toBeDisabled();
  await user.clear(screen.getByLabelText("Название смены"));
  await user.type(screen.getByLabelText("Название смены"), "Обновлённая смена");
  await user.click(screen.getByRole("button", { name: "Сохранить смену" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith("worker", expect.objectContaining({ shift_rule_id: "existing", expected_revision: 7,
    starts_local: "22:00", ends_local: "06:00", valid_until: "2027-01-01", pattern: expect.objectContaining({ weekdays: [], excluded_dates: ["2026-11-10"] }) })));
  await user.click(await screen.findByRole("button", { name: "Изменить смену" }));
  expect(screen.getByLabelText("Название смены")).toHaveValue("Обновлённая смена");
  await user.click(screen.getByText(/Ограничения и исключения · исключённых дат/));
  expect(screen.getByRole("button", { name: "Убрать 2026-11-10" })).toBeInTheDocument();
});

it("preserves an unfinished shift while switching independent workforce sections", async () => {
  const user = await openExisting();
  await user.type(screen.getByLabelText("Название смены"), " черновик");
  await user.click(screen.getByRole("button", { name: "Бригады" }));
  expect(screen.queryByRole("button", { name: "Сохранить смену" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Сотрудники" }));
  expect(screen.getByLabelText("Название смены")).toHaveValue("Сохранённая смена черновик");
});

it("keeps malformed saved shifts readable as an error without a destructive Save action", async () => {
  fixture.staff[0].shifts[0].pattern = { frequency: "day", anchor_date: "2026-01-01", version: 99 } as unknown as ShiftRule["pattern"];
  const save = vi.spyOn(managementApi, "saveShift");
  await openExisting();
  expect(screen.getByRole("alert")).toHaveTextContent("Не удалось прочитать сохранённое правило смены");
  expect(screen.queryByRole("button", { name: "Сохранить смену" })).not.toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
});

it("retains entered values when saving fails", async () => {
  vi.spyOn(managementApi, "saveShift").mockRejectedValue(new Error("Конфликт версии"));
  const user = await openExisting();
  await user.type(screen.getByLabelText("Название смены"), " изменено");
  await user.click(screen.getByRole("button", { name: "Сохранить смену" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Конфликт версии");
  expect(screen.getByLabelText("Название смены")).toHaveValue("Сохранённая смена изменено");
});
