import type { ForecastResult } from "@/shared/types/domain";
import { isDateKey } from "./operations";

/** Keep a source recommendation visible, but never present a late date as compliant. */
export function exceedsDeadline(date: string | null, deadline: string | null): boolean {
  return !!date && !!deadline && isDateKey(date) && isDateKey(deadline) && date > deadline;
}
export function forecastUnavailableLabel(result: ForecastResult): string {
  if (result.status === "needs_input") return "Недостаточно данных для прогноза";
  if (result.status === "failed") return "Расчёт завершился с ошибкой";
  if (result.status === "unavailable") return "Метод сейчас недоступен";
  return "Дата не передана источником";
}
