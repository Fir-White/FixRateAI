import { describe, expect, it } from "vitest";
import { readCalendarPattern } from "@/shared/lib/calendarPattern";

describe("stored calendar patterns", () => {
  it("reads the sparse presentation seed without replacing its meaning with new-shift defaults", () => {
    const raw = { frequency: "day", anchor_date: "2026-11-06", interval: 1, weekend_policy: "none" };
    const result = readCalendarPattern(raw);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value.excluded_dates).toEqual([]);
    expect(Object.keys(raw)).toHaveLength(4);
    const weekly = readCalendarPattern({ frequency: "week", anchor_date: "2026-11-06" });
    expect(weekly.ok && weekly.value.weekdays).toEqual([]);
  });

  it.each(["day", "week", "month", "quarter", "year", "yearly_count", "dates"])("round-trips %s including exclusions and policies", frequency => {
    const raw = { frequency, anchor_date: "2024-02-29", excluded_dates: ["2026-11-06"],
      ...(frequency === "yearly_count" ? { count_per_year: 5, annual_policy: "from_anchor", weekdays: [2, 5] } : {}),
      ...(frequency === "dates" ? { dates: ["2026-11-07", "2026-11-09"] } : {}),
      ...(frequency === "quarter" ? { quarter_policy: "rolling_months", month_days: [-1] } : {}),
    };
    const first = readCalendarPattern(raw);
    expect(first.ok).toBe(true);
    if (!first.ok) return;
    expect(readCalendarPattern(JSON.parse(JSON.stringify(first.value)))).toEqual(first);
    expect(first.value).toMatchObject(raw);
  });

  it.each([
    null, {}, { frequency: "fortnight", anchor_date: "2026-11-06" },
    { frequency: "day", anchor_date: "2026-02-30" },
    { frequency: "day", anchor_date: "2026-11-06", excluded_dates: null },
    { frequency: "day", anchor_date: "2026-11-06", version: 2 },
    { frequency: "week", anchor_date: "2026-11-06", weekdays: [1, 1] },
    { frequency: "week", anchor_date: "2026-11-06", weekdays: [8] },
    { frequency: "day", anchor_date: "2026-11-06", interval: "1" },
    { frequency: "yearly_count", anchor_date: "2026-11-06" },
    { frequency: "dates", anchor_date: "2026-11-06", dates: [] },
  ])("refuses unsupported or damaged input %# without a fabricated empty rule", raw => {
    expect(readCalendarPattern(raw).ok).toBe(false);
  });
});
