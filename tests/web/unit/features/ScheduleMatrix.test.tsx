import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ScheduleMatrix, PlanApproval } from "@/features/analyst/AnalystPanels";
import { request } from "@/shared/api/request";

vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false, request: vi.fn() }));
vi.mock("@/shared/lib/useMediaQuery", () => ({ useMediaQuery: () => true }));
const session = vi.hoisted(() => ({ role: "director" }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { role: session.role } }) }));
beforeEach(() => { vi.mocked(request).mockReset(); session.role = "director"; });

it("keeps two source obligations transferred to the same date distinct in mobile and matrix", async () => {
  vi.mocked(request).mockResolvedValue({ rows: [{ bindingId: "binding", system: "ИТП", complex: null, equipment: "Насос", equipmentId: "eq", code: "1.1", title: "Проверка", frequency: "Ежедневно", crewSize: 1, normValue: "0.5", normUnit: "person_hour", published: true,
    dates: ["2026-11-07", "2026-11-08"], transfers: { "2026-11-07": "2026-11-09", "2026-11-08": "2026-11-09" } }] });
  const user = userEvent.setup();
  render(<MemoryRouter><ScheduleMatrix year={2026} month={11} /></MemoryRouter>);
  const summary = await screen.findByText("1.1 · Проверка", { selector: "summary" });
  await user.click(summary);
  expect(screen.getAllByText(/перенос на 09 нояб\. 2026 г\./)).toHaveLength(2);
  await user.click(screen.getByRole("button", { name: "Открыть полную матрицу" }));
  expect(screen.getByRole("region", { name: "Месячная матрица операций" })).toHaveAttribute("tabindex", "0");
  expect(screen.getByLabelText("Обязательство 07 нояб. 2026 г., перенос 09 нояб. 2026 г.")).toBeInTheDocument();
  expect(screen.getByLabelText("Обязательство 08 нояб. 2026 г., перенос 09 нояб. 2026 г.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Даты правее" })).toBeEnabled();
});

it("does not expose plan mutation or its reason to a read-only director", async () => {
  vi.mocked(request).mockResolvedValue([{ id: "plan", revision: 2, status: "draft" }]);
  render(<PlanApproval year={2026} month={11} onSaved={vi.fn()} />);
  expect(request).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Утвердить" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Основание утверждения")).not.toBeInTheDocument();
});

it.each([{ plans: [] }, { plans: [{ id: "plan", revision: 2, status: "approved" }] }])("does not show a passive plan panel when there is nothing to approve: %j", async ({ plans }) => {
  session.role = "chief_engineer";
  vi.mocked(request).mockResolvedValue(plans);
  const { container } = render(<PlanApproval year={2026} month={11} onSaved={vi.fn()} />);
  await waitFor(() => expect(request).toHaveBeenCalledOnce());
  expect(container).toBeEmptyDOMElement();
});

it("requires a reason, preserves the approval contract and removes the approved draft", async () => {
  session.role = "chief_engineer";
  vi.mocked(request).mockResolvedValueOnce([{ id: "plan", revision: 2, status: "draft" }]).mockResolvedValueOnce({}).mockResolvedValueOnce([{ id: "plan", revision: 3, status: "approved" }]);
  const saved = vi.fn(), user = userEvent.setup();
  render(<PlanApproval year={2026} month={11} onSaved={saved} />);
  const approve = await screen.findByRole("button", { name: "Утвердить" });
  expect(approve).toBeDisabled();
  await user.type(screen.getByLabelText("Основание утверждения"), "Состав и сроки проверены");
  await user.click(approve);
  expect(request).toHaveBeenCalledWith("/api/v1/maintenance/plans/plan/approve", { method: "POST", body: JSON.stringify({ expected_revision: 2, reason: "Состав и сроки проверены" }) });
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Утверждение плана" })).not.toBeInTheDocument());
  expect(saved).toHaveBeenCalledOnce();
  expect(request).toHaveBeenCalledTimes(3);
});

it("keeps the entered approval reason and shows a server failure", async () => {
  session.role = "chief_engineer";
  vi.mocked(request).mockResolvedValueOnce([{ id: "plan", revision: 2, status: "draft" }]).mockRejectedValueOnce(new Error("Версия плана изменилась"));
  const saved = vi.fn(), user = userEvent.setup();
  render(<PlanApproval year={2026} month={11} onSaved={saved} />);
  await user.type(await screen.findByLabelText("Основание утверждения"), "Проверено");
  await user.click(screen.getByRole("button", { name: "Утвердить" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Версия плана изменилась");
  expect(screen.getByLabelText("Основание утверждения")).toHaveValue("Проверено");
  expect(saved).not.toHaveBeenCalled();
});
