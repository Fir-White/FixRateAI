import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ActsPanel, ExecutionProtocol } from "@/features/analyst/AnalystPanels";
import { demoTasks } from "@/shared/mocks/data";
import type { ExecutionReport, Role } from "@/shared/types/domain";
import { ContentTheme } from "@/shared/ui/ContentTheme";

const session = vi.hoisted(() => ({ role: "executor" as Role }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { role: session.role, timezone: "Asia/Yekaterinburg" } }) }));
const task = { ...demoTasks[0], state: "submitted" as const, requiredActs: ["Протокол измерений"] };
const execution: ExecutionReport = { id: "attempt-1", taskId: task.id, attemptNumber: 1, state: "submitted", narrative: "", checklist: [], photos: [], submittedAt: "2026-11-06T12:00:00Z", acts: [{ id: "act-1", kind: "Протокол измерений", verified: false, url: "/media/act-1" }] };
beforeEach(() => { session.role = "executor"; });

it("keeps an uploaded document accessible even when the task has no required acts", () => {
  render(<ActsPanel task={{ ...task, requiredActs: [] }} execution={execution} editable={false} onSaved={vi.fn()} />);
  expect(screen.getByRole("link", { name: /Открыть скан/ })).toHaveAttribute("href", "/media/act-1");
  expect(screen.queryByText(/не заданы регламентом/)).not.toBeInTheDocument();
});

it.each(["executor", "director"] as const)("%s can open a document but cannot edit the engineer's verification", role => {
  session.role = role;
  render(<ActsPanel task={task} execution={execution} editable={false} onSaved={vi.fn()} />);
  expect(screen.getByRole("link", { name: /Открыть скан/ })).toHaveAttribute("href", "/media/act-1");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Подтвердить проверку/ })).not.toBeInTheDocument();
});

it("shows immutable actual values without disabled inputs or invented missing readings", () => {
  render(<ExecutionProtocol task={task} execution={execution} value={{ actual: { started_at: "2026-11-05T23:30:00Z", performed_at: "2026-11-06T00:30:00Z", person_hours: "0" }, readings: [] }} onChange={vi.fn()} disabled readOnly />);
  expect(screen.getByText("0 чел.-ч")).toBeVisible();
  expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.getByText(/04:30/)).toBeVisible();
});

it("converts an explicitly selected device-local time to the existing UTC actual contract", async () => {
  const changed = vi.fn();
  const user = userEvent.setup();
  render(<ContentTheme><ExecutionProtocol task={task} execution={null} value={{ actual: null, readings: [] }} onChange={changed} disabled={false} /></ContentTheme>);
  await user.click(screen.getByRole("button", { name: "Фактическое начало" }));
  fireEvent.change(screen.getByLabelText("Дата", { exact: true }), { target: { value: "05112026" } });
  fireEvent.change(screen.getByLabelText("Часы"), { target: { value: "23" } });
  fireEvent.change(screen.getByLabelText("Минуты"), { target: { value: "55" } });
  expect(changed).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Применить" }));
  const payload = changed.mock.calls[0][0];
  const actual = new Date(payload.actual.started_at);
  expect(payload.actual.started_at).toMatch(/Z$/);
  expect([actual.getFullYear(), actual.getMonth() + 1, actual.getDate(), actual.getHours(), actual.getMinutes()]).toEqual([2026, 11, 5, 23, 55]);
  expect(payload.actual.performed_at).toBe("");
  expect(payload.actual.person_hours).toBe("");
  expect(payload.readings).toEqual([]);
});
