import { describe, expect, it } from "vitest";
import { answerLabel, attemptStateSummary, unitLabel } from "@/shared/lib/presentation";
import { formatDate, formatDateTime } from "@/shared/lib/format";

describe("result presentation preserves meaning", () => {
  it("does not label returned or accepted work as waiting for review", () => {
    expect(attemptStateSummary("submitted")).toContain("Ожидается решение");
    expect(attemptStateSummary("rework_required")).toContain("возвращена");
    expect(attemptStateSummary("accepted")).toContain("принята");
  });
  it("preserves zero, unknown units and missing answers separately", () => {
    expect(answerLabel("0")).toBe("0");
    expect(answerLabel(null)).toBe("Ответ не указан");
    expect(unitLabel("person_hour")).toBe("чел.-ч");
    expect(unitLabel("kPa")).toBe("kPa");
  });
  it("keeps a calendar date while timestamps follow the site timezone", () => {
    expect(formatDate("2026-11-06")).toContain("06");
    expect(formatDateTime("2026-11-05T23:30:00Z", "Asia/Yekaterinburg")).toContain("06");
    expect(formatDateTime("2026-11-05T23:30:00Z", "America/Los_Angeles")).toContain("05");
  });
});
