import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ActsPanel, ExecutionProtocol } from "@/features/analyst/AnalystPanels";
import { demoTasks } from "@/shared/mocks/data";
import type { ExecutionReport, Role } from "@/shared/types/domain";

const session = vi.hoisted(() => ({ role: "executor" as Role }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { role: session.role, timezone: "Asia/Yekaterinburg" } }) }));
const task = { ...demoTasks[0], state: "submitted" as const, requiredActs: ["Протокол измерений"] };
const execution: ExecutionReport = { id: "attempt-1", taskId: task.id, attemptNumber: 1, state: "submitted", narrative: "", checklist: [], photos: [], submittedAt: "2026-11-06T12:00:00Z", acts: [{ id: "act-1", kind: "Протокол измерений", verified: false, url: "/media/act-1" }] };
beforeEach(() => { session.role = "executor"; });

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
