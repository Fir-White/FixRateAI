import type { CalendarPattern } from "@/shared/types/management";

type PatternResult = { ok: true; value: CalendarPattern } | { ok: false; error: string };

// Stored shifts can omit fields defaulted by the server's CalendarPattern DTO.
// These are serialization defaults, not the UI defaults for creating a new shift.
const defaults = {
  interval: 1, weekdays: [], week_parity: "any", month_days: [], months: [],
  period_edge: "end", short_month: "last_day", quarter_policy: "calendar_edge",
  annual_policy: "calendar_year", weekend_policy: "none", count_per_year: null,
  dates: [], excluded_dates: [],
};
const keys = new Set(["frequency", "anchor_date", ...Object.keys(defaults)]);
const oneOf = (value: unknown, values: readonly unknown[]) => values.includes(value);
const integer = (value: unknown, min: number, max: number): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;
function dateOnly(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
const list = (value: unknown, valid: (item: unknown) => boolean): boolean =>
  Array.isArray(value) && value.every(valid) && new Set(value).size === value.length;

/** Read only supported stored patterns; never discard an unknown field/version. */
export function readCalendarPattern(raw: unknown): PatternResult {
  const failure: PatternResult = { ok: false, error: "Не удалось прочитать сохранённое правило смены: неподдерживаемый или повреждённый формат. Изменения не сохраняются. Обратитесь к администратору." };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return failure;
  const source = raw as Record<string, unknown>;
  if (Object.keys(source).some(key => !keys.has(key))) return failure;
  const p: Record<string, unknown> = { ...defaults, ...source };
  if (!oneOf(p.frequency, ["day", "week", "month", "quarter", "year", "yearly_count", "dates"])
    || !dateOnly(p.anchor_date) || !integer(p.interval, 1, 10000)
    || !list(p.weekdays, day => integer(day, 1, 7))
    || !list(p.month_days, day => day === -1 || integer(day, 1, 31))
    || !list(p.months, month => integer(month, 1, 12))
    || !list(p.dates, dateOnly) || !list(p.excluded_dates, dateOnly)
    || !oneOf(p.week_parity, ["any", "even", "odd"])
    || !oneOf(p.period_edge, ["start", "end"])
    || !oneOf(p.short_month, ["last_day", "skip"])
    || !oneOf(p.quarter_policy, ["calendar_edge", "rolling_months"])
    || !oneOf(p.annual_policy, ["calendar_year", "from_anchor"])
    || !oneOf(p.weekend_policy, ["none", "next_workday"])) return failure;
  const pattern = p as unknown as CalendarPattern;
  if (pattern.frequency === "yearly_count" ? !integer(pattern.count_per_year, 1, 366) : pattern.count_per_year !== null) return failure;
  if (pattern.frequency === "dates"
    ? !pattern.dates.length || pattern.interval !== 1 || pattern.weekdays.length > 0 || pattern.week_parity !== "any"
    : pattern.dates.length > 0) return failure;
  if (["day", "week", "dates"].includes(pattern.frequency) && (pattern.months.length || pattern.month_days.length)) return failure;
  if (!["year", "yearly_count"].includes(pattern.frequency) && pattern.months.length) return failure;
  return { ok: true, value: { ...pattern, weekdays: [...pattern.weekdays], month_days: [...pattern.month_days], months: [...pattern.months], dates: [...pattern.dates], excluded_dates: [...pattern.excluded_dates] } };
}
