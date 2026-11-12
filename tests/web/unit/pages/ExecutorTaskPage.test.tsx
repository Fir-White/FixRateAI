import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { ExecutorTaskPage } from "@/pages/ExecutorTaskPage";
import { maintenanceApi, type TaskBundle } from "@/shared/api/maintenance";
import { request } from "@/shared/api/request";
import { demoTasks } from "@/shared/mocks/data";

vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false, request: vi.fn().mockResolvedValue([]) }));
vi.mock("@/shared/api/maintenance", () => ({ maintenanceApi: { getExecutorTask: vi.fn(), saveReport: vi.fn(), upload: vi.fn() } }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { userId: "executor", role: "executor", timezone: "Asia/Yekaterinburg" } }) }));
afterEach(() => { vi.unstubAllGlobals(); });

it("keeps the draft and latest photo revision available to document uploads without remounting the editor", async () => {
  vi.stubGlobal("URL", class extends URL { static createObjectURL = () => "blob:preview"; static revokeObjectURL = () => {}; });
  const task = { ...demoTasks[0], id: "task", revision: 2, state: "in_progress" as const, requiredActs: ["Акт проверки"], assignees: [{ executorId: "executor", name: "Исполнитель", qualifications: [] }] };
  const bundle: TaskBundle = { task, execution: { id: "attempt", taskId: "task", attemptNumber: 1, state: "draft", narrative: "", submittedAt: null, checklist: [{ id: "item", text: "Поверхность очищена", answerKind: "boolean", answer: "done", unit: null, required: true, visualVerifiability: "visible", photoRequired: true }], photos: [] }, review: null, decision: null, allowedActions: ["edit_report", "upload_photo", "submit"] };
  vi.mocked(maintenanceApi.getExecutorTask).mockResolvedValue(bundle);
  vi.mocked(maintenanceApi.saveReport).mockResolvedValue({ ...bundle, task: { ...task, revision: 3 } });
  let finish!: (value: TaskBundle) => void;
  vi.mocked(maintenanceApi.upload).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<MemoryRouter initialEntries={["/executor/tasks/task"]}><Routes><Route path="/executor/tasks/:taskId" element={<ExecutorTaskPage />} /></Routes></MemoryRouter>);
  fireEvent.change(await screen.findByLabelText("Что выполнено и какие замечания остались"), { target: { value: "Сохранённый комментарий" } });
  fireEvent.change(screen.getByLabelText("Фото до: Поверхность очищена"), { target: { files: [new File(["photo"], "before.png", { type: "image/png" })] } });
  await waitFor(() => expect(maintenanceApi.upload).toHaveBeenCalled());
  expect(maintenanceApi.saveReport).toHaveBeenCalledWith("task", 2, "Сохранённый комментарий", { item: "done" }, expect.anything());
  expect(maintenanceApi.upload).toHaveBeenCalledWith("task", 3, "item", "before", "front", expect.any(File));
  expect(screen.getByRole("button", { name: "Загрузить скан" })).toBeDisabled();
  finish({ ...bundle, task: { ...task, revision: 4 } });
  await waitFor(() => expect(screen.queryByText("Загружаем…")).not.toBeInTheDocument());
  expect(screen.getByLabelText("Что выполнено и какие замечания остались")).toHaveValue("Сохранённый комментарий");
  const scan = screen.getByRole("button", { name: "Загрузить скан" }).closest("fieldset")!.querySelector('input[type="file"]')!;
  fireEvent.change(scan, { target: { files: [new File(["scan"], "act.png", { type: "image/png" })] } });
  fireEvent.click(screen.getByRole("button", { name: "Загрузить скан" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("/api/v1/maintenance/tasks/task/acts", expect.objectContaining({ method: "POST", body: expect.any(FormData) })));
  const call = vi.mocked(request).mock.calls.find(([url]) => url.endsWith("/acts"))!;
  expect((call[1]!.body as FormData).get("expected_revision")).toBe("4");
});
