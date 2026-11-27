import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PhotoReviewCard } from "@/entities/execution/PhotoReviewCard";
import type { PhotoReview, VisualAssessment } from "@/shared/types/domain";

const visual: VisualAssessment = {
  subject_matches_task: "yes",
  same_subject: "yes",
  comparable: "yes",
  before_description: "На корпусе до работы виден налёт.",
  after_description: "После работы поверхность корпуса чистая.",
  visible_changes: ["На видимом участке налёт удалён."],
  concerns: ["Обратная сторона не показана."],
  recommended_actions: ["Приложить фото обратной стороны."],
  cannot_confirm: ["Герметичность по фото не проверяется."],
  conclusion: "visible_improvement",
  summary: "На показанном участке корпуса после работы отсутствует прежний налёт.",
};

const review: PhotoReview = {
  id: "review",
  executionId: "attempt",
  status: "completed",
  modelRef: "aitunnel:qwen3.7-flash",
  promptSetVersion: "maintenance-aitunnel-vision-v4",
  createdAt: "2026-11-04T12:00:00Z",
  items: [
    {
      id: "check",
      label: "Поверхность очищена",
      verdict: "visible_change",
      note: visual.summary,
      assessment: visual,
    },
  ],
  limitations: ["Проверьте фотографии самостоятельно."],
};

describe("photo assessment", () => {
  it.each([
    ["manual_review", "Нужна ручная проверка"],
    ["rejected", "Фото не подходят"],
  ] as const)("shows %s as photo evidence, not as a decision on the work", (classification, label) => {
    render(<PhotoReviewCard review={{ ...review, classification }} formatDateTime={(value) => value} />);
    const result = screen.getByRole("group", { name: "Оценка фотодоказательств" });
    expect(result).toHaveTextContent(label);
    expect(result).toHaveTextContent(classification);
    expect(result).toHaveTextContent("Работу принимает инженер");
    expect(screen.getByText(visual.summary, { exact: false })).toBeVisible();
  });
  it("shows concise Russian observations and only one reminder without internal codes", () => {
    render(<PhotoReviewCard review={review} formatDateTime={(value) => value} />);
    expect(screen.getByText(/На показанном участке корпуса после работы отсутствует прежний налёт/)).toBeVisible();
    expect(screen.getAllByText("Проверьте фотографии самостоятельно.")).toHaveLength(1);
    expect(screen.queryByText(/qwen3\.7-flash/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/maintenance-aitunnel-vision/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/visible_improvement/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Работа принята")).not.toBeInTheDocument();
  });

  it("marks legacy saved CLIP results honestly without showing delta scores", () => {
    render(
      <PhotoReviewCard
        review={{
          ...review,
          modelRef: "openai/clip-vit-base-patch32@fixture",
          items: [{ id: "check", label: "Поверхность очищена", verdict: "no_visible_change", note: "delta -0.02" }],
        }}
        formatDateTime={(value) => value}
      />
    );
    expect(screen.getByText(/Прежний тип проверки/)).toBeVisible();
    expect(screen.getByText(/Сохранена прежняя проверка без текстового описания снимков/)).toBeVisible();
    expect(screen.queryByText("delta -0.02")).not.toBeInTheDocument();
    expect(screen.getByText("Проверьте фотографии самостоятельно.")).toBeVisible();
  });

  it("never invents observations or leaks system error codes on unavailability", () => {
    render(
      <PhotoReviewCard
        review={{ ...review, classification: "manual_review", status: "unavailable", modelRef: null, errorCode: "AITUNNEL_AUTH_FAILED", items: [] }}
        formatDateTime={(value) => value}
      />
    );
    expect(screen.getByText(/Анализ фотографий не настроен на сервере/)).toBeVisible();
    expect(screen.queryByText("AITUNNEL_AUTH_FAILED")).not.toBeInTheDocument();
    expect(screen.queryByText(visual.summary)).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Оценка фотодоказательств" })).not.toBeInTheDocument();
  });

  it("shows timeout message without leaking TIMEOUT error code", () => {
    render(
      <PhotoReviewCard
        review={{ ...review, status: "failed", modelRef: null, errorCode: "AITUNNEL_TIMEOUT", items: [] }}
        formatDateTime={(value) => value}
      />
    );
    expect(screen.getByText(/Анализ не успел завершиться вовремя/)).toBeVisible();
    expect(screen.queryByText("AITUNNEL_TIMEOUT")).not.toBeInTheDocument();
  });

  it("displays the analysis duration in the report results", () => {
    render(<PhotoReviewCard review={{ ...review, elapsedMs: 1450 }} formatDateTime={(value) => value} />);
    expect(screen.getByText(/Время анализа: 1\.5 сек/)).toBeVisible();
  });
});
