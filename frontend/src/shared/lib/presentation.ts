import type { TaskState } from "@/shared/types/domain";

/** Presentation only: never infer completion, deadlines or units from other fields. */
export function unitLabel(unit: string | null | undefined): string {
  return unit === "person_hour" ? "чел.-ч" : unit === "elapsed_hour" ? "часы бригады" : unit === "unconfirmed" ? "Единица не подтверждена" : unit || "Единица не указана";
}

export const viewLabel = (value: string) => value === "front" ? "Спереди" : value || "Не указан";

export function attemptStateSummary(state: TaskState): string {
  switch (state) {
    case "submitted": return "Отчёт отправлен. Ожидается решение инженера.";
    case "accepted": return "Работа принята. Результат сохранён в истории.";
    case "rework_required": return "Работа возвращена на доработку. Прошлая попытка сохранена.";
    case "in_progress": return "Работа выполняется. Заполните результат текущей попытки.";
    case "assigned": return "Задание назначено. Начните работу, чтобы заполнить отчёт.";
    case "cancelled": return "Задание отменено. Сохранённые материалы доступны для просмотра.";
    case "draft": return "Черновик задания.";
    default: return "Состояние задания неизвестно.";
  }
}

export function answerLabel(value: string | null | undefined): string {
  if (value === "done") return "Выполнено";
  if (value === "not_done") return "Не выполнено";
  if (value === "not_applicable") return "Не применимо";
  return value === null || value === undefined || value === "" ? "Ответ не указан" : value;
}
