import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PhotoEvidenceUpload } from "@/entities/execution/PhotoEvidenceUpload";
import { photoRequirementProgress } from "@/shared/lib/evidence";
import type { ChecklistItem, EvidencePhoto } from "@/shared/types/domain";

vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: { timezone: "Asia/Yekaterinburg" } }) }));
const checklist: ChecklistItem[] = [
  { id: "reading", text: "Показание счётчика", answerKind: "number", unit: "м³", required: true, visualVerifiability: "partial", photoRequired: false, answer: null },
  { id: "surface", text: "Поверхность очищена", answerKind: "boolean", unit: null, required: true, visualVerifiability: "visible", photoRequired: true, answer: null },
  { id: "label", text: "Маркировка читается", answerKind: "boolean", unit: null, required: false, visualVerifiability: "visible", photoRequired: true, answer: null },
];
const photo = (phase: "before" | "after", itemId = "surface", viewKey = "front"): EvidencePhoto => ({ id: `${itemId}-${phase}-${viewKey}`, phase, checklistItemId: itemId, viewKey, label: "Подлинное вложение", capturedAt: null, uploadedAt: "2026-11-07T10:00:00Z", status: "uploaded" });
const file = (name: string) => new File(["actual image bytes validated by server"], name, { type: "image/png" });
beforeEach(() => {
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = vi.fn(() => "blob:preview");
    static revokeObjectURL = vi.fn();
  });
});
afterEach(() => { vi.unstubAllGlobals(); });

it("derives required slots from the attempt checklist flags, including optional-answer items that still require photos", () => {
  render(<PhotoEvidenceUpload checklist={checklist} photos={[]} disabled={false} onUpload={vi.fn()} />);
  expect(screen.getByText(/минимум 4 фото/)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Фотографии: Поверхность очищена" })).toBeVisible();
  expect(screen.getByRole("region", { name: "Фотографии: Маркировка читается" })).toBeVisible();
  expect(screen.getByRole("region", { name: "Фотографии: Показание счётчика" }).closest("details")).not.toHaveAttribute("open");
});

it("accepts multiple dropped files and serializes both phases without assigning another checklist item or view", async () => {
  let finish!: () => void;
  const upload = vi.fn().mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; })).mockResolvedValue(undefined);
  render(<PhotoEvidenceUpload checklist={checklist} photos={[]} disabled={false} onUpload={upload} />);
  const item = within(screen.getByRole("region", { name: "Фотографии: Поверхность очищена" }));
  const before = item.getByRole("button", { name: /^Прикрепить фото до:/ }).parentElement!;
  fireEvent.drop(before, { dataTransfer: { files: [file("before-1.png"), file("before-2.png")] } });
  fireEvent.change(item.getByLabelText(/^Фото после:/), { target: { files: [file("after.png")] } });
  expect(upload).toHaveBeenCalledTimes(1);
  expect(item.getByText("after.png")).toBeInTheDocument();
  await act(async () => { finish(); });
  await waitFor(() => expect(upload).toHaveBeenCalledTimes(3));
  expect(upload.mock.calls.map(([request]) => [request.file.name, request.itemId, request.phase, request.viewKey])).toEqual([
    ["before-1.png", "surface", "before", "front"], ["before-2.png", "surface", "before", "front"], ["after.png", "surface", "after", "front"],
  ]);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Загружено: after.png"));
});

it("stops on an API failure, keeps pending files, and retries only the failed file before resuming", async () => {
  const upload = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error("Сервер недоступен")).mockResolvedValue(undefined);
  render(<PhotoEvidenceUpload checklist={checklist} photos={[]} disabled={false} onUpload={upload} />);
  fireEvent.change(screen.getByLabelText("Фото до: Поверхность очищена"), { target: { files: [file("saved.png"), file("retry.png"), file("waiting.png")] } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Сервер недоступен");
  expect(upload).toHaveBeenCalledTimes(2);
  expect(screen.getByText("waiting.png")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
  await waitFor(() => expect(upload).toHaveBeenCalledTimes(4));
  expect(upload.mock.calls.map(([request]) => request.file.name)).toEqual(["saved.png", "retry.png", "retry.png", "waiting.png"]);
});

it("rejects invalid or oversized files before transport and ignores drops while externally disabled", async () => {
  const upload = vi.fn().mockResolvedValue(undefined);
  const props = { checklist, photos: [], onUpload: upload };
  const { rerender } = render(<PhotoEvidenceUpload {...props} disabled={false} />);
  const huge = file("huge.png"); Object.defineProperty(huge, "size", { value: 10_485_761 });
  fireEvent.change(screen.getByLabelText("Фото до: Поверхность очищена"), { target: { files: [new File(["text"], "bad.txt", { type: "text/plain" }), huge] } });
  expect(screen.getByRole("alert")).toHaveTextContent("JPEG, PNG или WebP");
  expect(screen.getByRole("alert")).toHaveTextContent("не больше 10 МБ");
  expect(upload).not.toHaveBeenCalled();
  rerender(<PhotoEvidenceUpload {...props} disabled />);
  const button = screen.getByRole("button", { name: "Прикрепить фото до: Поверхность очищена" });
  expect(button).toBeDisabled();
  fireEvent.drop(button.parentElement!, { dataTransfer: { files: [file("blocked.png")] } });
  expect(upload).not.toHaveBeenCalled();
});

it("never counts different views or checklist items as a complete mandatory pair", () => {
  const photos = [photo("before"), photo("after", "surface", "side"), photo("after", "label")];
  expect(photoRequirementProgress(checklist, photos)).toMatchObject({ minimum: 4, covered: 2, ready: false });
  expect(photoRequirementProgress(checklist, [...photos, photo("after"), photo("before", "label")])).toMatchObject({ covered: 4, ready: true });
});

it("continues an existing non-default view instead of silently creating an incompatible pair", async () => {
  const upload = vi.fn().mockResolvedValue(undefined);
  render(<PhotoEvidenceUpload checklist={checklist} photos={[photo("before", "surface", "сбоку")]} disabled={false} onUpload={upload} />);
  fireEvent.change(screen.getByLabelText("Фото после: Поверхность очищена · сбоку"), { target: { files: [file("side-after.png")] } });
  await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.objectContaining({ itemId: "surface", phase: "after", viewKey: "сбоку" })));
});
