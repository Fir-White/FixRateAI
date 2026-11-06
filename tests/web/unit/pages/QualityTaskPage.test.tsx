import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { QualityTaskPage } from "@/pages/QualityTaskPage";
import { maintenanceApi, type TaskBundle } from "@/shared/api/maintenance";
import { saveStoredAiSettings } from "@/features/ai/aiSettings";
import { clearAiKey } from "@/shared/lib/aiCredentials";
import { demoTasks } from "@/shared/mocks/data";
import type { PhotoReview } from "@/shared/types/domain";

vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false, request: vi.fn().mockResolvedValue([]) }));
vi.mock("@/shared/api/maintenance", () => ({ maintenanceApi: { getQualityBundle: vi.fn(), getAiModels: vi.fn(), photoReview: vi.fn(), review: vi.fn() } }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { userId: "engineer", role: "engineer", timezone: "Asia/Yekaterinburg" } }) }));

const failedReview: PhotoReview = {
  id: "analysis", executionId: "attempt", status: "failed", modelRef: null,
  promptSetVersion: "v1", createdAt: "2026-11-07T00:00:00Z", items: [], limitations: [],
};

function bundle(actions: NonNullable<TaskBundle["allowedActions"]>, review: PhotoReview | null = null): TaskBundle {
  const task = { ...demoTasks[0], id: "task", revision: 7, state: "submitted" as const, requiredActs: [] };
  return {
    task, execution: { id: "attempt", taskId: task.id, attemptNumber: 1, state: "submitted", narrative: "Работа выполнена", checklist: [], photos: [], submittedAt: "2026-11-07T00:00:00Z" },
    review, decision: null, allowedActions: actions, photoAnalysisStatus: review ? "failed" : "not_requested",
  };
}

function setup(data: TaskBundle) {
  vi.mocked(maintenanceApi.getQualityBundle).mockResolvedValue(data);
  return render(<MemoryRouter initialEntries={["/quality/task"]}><Routes><Route path="/quality/:taskId" element={<QualityTaskPage />} /></Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  clearAiKey();
  saveStoredAiSettings({ provider: "clip", model: "", apiKey: "" });
  vi.mocked(maintenanceApi.getAiModels).mockResolvedValue({ current_provider: "clip", providers: [
    { id: "clip", name: "CLIP", description: "Локальная модель", available: true, models: [] },
    { id: "aitunnel", name: "AI Tunnel", description: "Облачная модель", available: true, has_server_key: false, models: [
      { id: "qwen3.7-flash", name: "Qwen3.7 Flash" }, { id: "qwen2.5-vl-72b-instruct", name: "Qwen2.5-VL" },
    ] },
  ] });
});

it("shows a photo-analysis error when the engineer may analyze but cannot review their own work", async () => {
  const user = userEvent.setup();
  vi.mocked(maintenanceApi.photoReview).mockRejectedValue(new Error("Сервис анализа недоступен"));
  setup(bundle(["photo_review"]));
  await user.click(await screen.findByRole("button", { name: "Анализировать фото" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Сервис анализа недоступен");
  expect(screen.queryByRole("button", { name: "Принять работу" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Вернуть на доработку" })).not.toBeInTheDocument();
  expect(maintenanceApi.review).not.toHaveBeenCalled();
});

it("passes the provider, model and session key selected by the engineer to retry", async () => {
  const user = userEvent.setup();
  vi.mocked(maintenanceApi.photoReview).mockResolvedValue({ ...failedReview, status: "completed", elapsedMs: 1430 });
  setup(bundle(["photo_review", "review"], failedReview));
  await user.click(await screen.findByRole("button", { name: /AI Tunnel \(Облако\)/ }));
  await user.selectOptions(await screen.findByLabelText("Облачная модель"), "qwen2.5-vl-72b-instruct");
  await user.type(screen.getByLabelText("Персональный API-ключ"), "test-session-key");
  await user.click(screen.getByRole("button", { name: "Повторить анализ" }));
  await waitFor(() => expect(maintenanceApi.photoReview).toHaveBeenCalledWith("task", 7, false, {
    provider: "aitunnel", model: "qwen2.5-vl-72b-instruct", api_key: "test-session-key",
  }));
  expect(window.localStorage.getItem("fixrate_ai_settings")).not.toContain("test-session-key");
});

it("does not attach a retry duration to an older review returned by a stale read", async () => {
  const user = userEvent.setup();
  vi.mocked(maintenanceApi.photoReview).mockResolvedValue({ ...failedReview, id: "new-analysis", status: "completed", elapsedMs: 1430 });
  setup(bundle(["photo_review"], failedReview));
  await user.click(await screen.findByRole("button", { name: "Повторить анализ" }));
  await waitFor(() => expect(maintenanceApi.getQualityBundle).toHaveBeenCalledTimes(2));
  await screen.findByText("Не удалось выполнить фотоанализ");
  expect(screen.queryByText("Время анализа: 1.4 сек")).not.toBeInTheDocument();
});

it.each([
  { label: "Принять работу", confirm: "Подтвердить приёмку", verdict: "accepted" },
  { label: "Вернуть на доработку", confirm: "Вернуть на доработку", verdict: "rejected" },
] as const)("requires the engineer's reason before $label", async ({ label, confirm, verdict }) => {
  const user = userEvent.setup();
  const data = bundle(["review"]);
  vi.mocked(maintenanceApi.review).mockResolvedValue(data);
  setup(data);
  const accept = await screen.findByRole("button", { name: "Принять работу" });
  const reject = screen.getByRole("button", { name: "Вернуть на доработку" });
  expect(accept).toBeDisabled();
  expect(reject).toBeDisabled();
  const reason = screen.getByLabelText(/Причина решения/);
  await user.type(reason, "   ");
  expect(accept).toBeDisabled();
  expect(reject).toBeDisabled();
  await user.clear(reason);
  await user.type(reason, "Проверены фотографии и показания");
  await user.click(screen.getByRole("button", { name: label }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("Проверены фотографии и показания")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: confirm }));
  await waitFor(() => expect(maintenanceApi.review).toHaveBeenCalledWith("task", 7, "attempt", verdict,
    "Проверены фотографии и показания", { reviewed_ai_result_id: undefined, additional_evidence_refs: [] }));
});
