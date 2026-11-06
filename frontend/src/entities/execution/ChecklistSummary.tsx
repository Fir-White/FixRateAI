import type { ChecklistItem } from "@/shared/types/domain";

export function formatChecklistAnswer(item: ChecklistItem): string {
  if (item.answer === null || item.answer === "") {
    return "—";
  }
  if (item.answer === "done") {
    return "Выполнено";
  }
  if (item.answer === "not_done") {
    return "Не выполнено";
  }
  if (item.answer === "not_applicable") {
    return "Не применимо";
  }
  return item.unit ? `${item.answer} ${item.unit}` : item.answer;
}

export function ChecklistSummary({
  items,
  mode = "task",
}: {
  items: ChecklistItem[];
  mode?: "task" | "quality";
}) {
  return (
    <div className="fr-checklist-result space-y-2">
      {items.map((item) => (
        <ChecklistRow key={item.id} item={item} mode={mode} />
      ))}
    </div>
  );
}

function ChecklistRow({
  item,
  mode,
}: {
  item: ChecklistItem;
  mode: "task" | "quality";
}) {
  const note =
    mode === "quality"
      ? item.visualVerifiability === "not_verifiable"
        ? "Не проверяется по фото"
        : item.photoRequired
          ? "Требуется фото"
          : "Без обязательного фото"
      : `${item.required ? "Обязательный" : "Необязательный"}${
          item.photoRequired ? " · нужен фотофиксатор" : ""
        }`;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2.5">
      <div>
        <p className="text-sm text-ink">{item.text}</p>
        <p className="mt-0.5 text-xs text-muted/70">{note}</p>
      </div>
      <span className="text-sm font-semibold text-ink-soft">
        {formatChecklistAnswer(item)}
      </span>
    </div>
  );
}
