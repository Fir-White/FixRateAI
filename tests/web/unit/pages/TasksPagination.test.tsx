import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { TasksPage } from "@/pages/TasksPage";
import type { MaintenanceTask } from "@/shared/types/domain";

const tasks: MaintenanceTask[] = Array.from({length: 51}, (_, index) => ({
  id: String(index).padStart(3, "0"), code: `job-${index}`, title: `Работа ${index}`,
  equipmentId: "equipment", equipmentName: "Насос", operationCode: "1.1", maintenanceType: "ТО1",
  state: "draft", isOverdue: false, deadlineBreached: false, mandatoryDueDate: "2026-11-06",
  scheduledStart: null, scheduledEnd: null, crewSize: 1, assignees: [], activeExecutionId: null,
  revision: 1, dataOrigin: "synthetic_demo", summary: "",
}));
vi.mock("@/shared/api/maintenance", () => ({maintenanceApi:{listTasks: async () => tasks}}));
vi.mock("@/shared/session/SessionContext", () => ({useSession: () => ({profile:{role:"director",timezone:"Asia/Yekaterinburg"}})}));
vi.mock("@/shared/lib/workspaceState", () => ({useWorkspaceState: () => ["all",vi.fn()]}));

it("reaches every page and searches the full dataset while resetting the page", async () => {
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={["/tasks?page=3"]}><TasksPage/></MemoryRouter>);
  expect(await screen.findByRole("link", {name:"Работа 50"})).toBeVisible();
  expect(screen.queryByRole("link", {name:"Работа 0"})).not.toBeInTheDocument();
  expect(screen.getByRole("button", {name:"Следующая"})).toBeDisabled();
  await user.type(screen.getByRole("textbox", {name:"Поиск нарядов"}), "Работа 0");
  expect(await screen.findByRole("link", {name:"Работа 0"})).toBeVisible();
  expect(screen.queryByRole("link", {name:"Работа 50"})).not.toBeInTheDocument();
  expect(screen.getByText(/Показаны 1–1 из 1/)).toBeVisible();
  expect(screen.queryByText(/Назначайте бригады/)).not.toBeInTheDocument();
});
