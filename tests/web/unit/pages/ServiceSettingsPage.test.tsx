import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ServiceSettingsPage } from "@/pages/ServiceSettingsPage";
import { managementApi } from "@/shared/api/management";
import { maintenanceApi } from "@/shared/api/maintenance";
import { patternDefaults, type CalendarPattern, type EquipmentRecord, type ServiceConfiguration } from "@/shared/types/management";

vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false, request: vi.fn(async () => ({ profiles: [] })) }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { role: "chief_engineer", timezone: "Asia/Yekaterinburg" } }) }));
let service: ServiceConfiguration;
beforeEach(() => {
  vi.restoreAllMocks();
  service = { binding_id: "rule", revision: 3, rule_version: 2, code: "1.1", title: "Проверка", instructions: "Сверить показания", maintenance_type: "ТО1",
    pattern: patternDefaults("2026-11-06", "day"), basis: "fixed_calendar", valid_from: "2026-11-06", valid_until: null, crew_size: 2,
    norm_value: "0.5", norm_unit: "person_hour", duration_minutes: 15, qualification_ids: ["skill"], checklist: [{ text: "Показание", answer_kind: "number", unit: "бар", required: true, photo_required: true, visual_verifiability: "partial" }],
    allowed_lead_days: 0, enabled: false, methodology_ref: "Методика 1", measurement_requirements: [], required_acts: ["Протокол"],
  };
  vi.spyOn(managementApi, "catalog").mockResolvedValue({ systems: [], equipment_types: [], skills: [{ id: "skill", name: "Допуск", code: "A" }], operations: [] });
  vi.spyOn(maintenanceApi, "listEquipment").mockResolvedValue([]);
  vi.spyOn(managementApi, "getEquipment").mockResolvedValue({ equipment_id: "eq", system_id: "sys", name: "Насос", asset_code: "N1", status: "active", revision: 1, properties: {} } as EquipmentRecord);
  vi.spyOn(managementApi, "services").mockImplementation(async () => [structuredClone(service)]);
});
async function open() {
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={["/settings/equipment?equipment=eq"]}><ServiceSettingsPage /></MemoryRouter>);
  await user.click(await screen.findByRole("button", { name: "Настроить" }));
  return user;
}

it.each<CalendarPattern["frequency"]>(["day", "week", "month", "quarter", "year", "yearly_count", "dates"])("preserves the complete %s payload when saving one changed field", async frequency => {
  service.pattern = { ...patternDefaults("2026-11-06", frequency), excluded_dates: ["2026-11-15"], ...(frequency === "dates" ? { dates: ["2026-11-10"] } : {}) };
  const original = structuredClone(service);
  const save = vi.spyOn(managementApi, "saveService").mockResolvedValue(service);
  const user = await open();
  await user.clear(screen.getByLabelText("Название обслуживания"));
  await user.type(screen.getByLabelText("Название обслуживания"), "Изменённое название");
  await user.click(screen.getByRole("button", { name: "Сохранить обслуживание" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith("eq", { ...original, title: "Изменённое название", expected_revision: 3 }, "rule"));
});

it("reveals and focuses a required field in a closed section, preserving other values", async () => {
  service.instructions = "";
  const save = vi.spyOn(managementApi, "saveService");
  const user = await open();
  const field = screen.getByLabelText("Инструкция");
  expect(field.closest("details")).not.toHaveAttribute("open");
  await user.click(screen.getByRole("button", { name: "Сохранить обслуживание" }));
  expect(field.closest("details")).toHaveAttribute("open");
  expect(field).toHaveFocus();
  expect(screen.getByRole("alert")).toHaveTextContent("Инструкция");
  expect(screen.getByLabelText("Исходная норма труда")).toHaveValue(0.5);
  expect(save).not.toHaveBeenCalled();
  await user.type(field, "Уточнённая инструкция");
  expect(field.closest("details")).toHaveAttribute("open");
});

it("keeps after_accepted_completion and the distinct save operation", async () => {
  service.basis = "after_accepted_completion";
  service.pattern = patternDefaults("2026-11-06", "month");
  const save = vi.spyOn(managementApi, "saveService").mockResolvedValue(service);
  const equipment = vi.spyOn(managementApi, "saveEquipment");
  const user = await open();
  expect(screen.getByLabelText("Отсчёт обслуживания")).toHaveValue("after_accepted_completion");
  await user.click(screen.getByRole("button", { name: "Сохранить обслуживание" }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(equipment).not.toHaveBeenCalled();
});
