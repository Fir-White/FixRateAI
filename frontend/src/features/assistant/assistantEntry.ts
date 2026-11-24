import type { ApiQueryCache } from '@/shared/lib/apiQueryCache';
import type { ChatAttachment } from '@/shared/api/assistant';

// A file selected on the workday opens the same private chat with its draft.
// Scope the handoff to the authenticated workspace and keep it in memory.
const transfers = new WeakMap<ApiQueryCache, { id: string; draft: string; rect?: DOMRectReadOnly; attachments?: ChatAttachment[] }>();

export function transferAssistantDraft(cache: ApiQueryCache | null, id: string, draft: string, rect?: DOMRectReadOnly, attachments?: ChatAttachment[]) {
  if (cache) transfers.set(cache, {id, draft, rect, attachments});
}

export function assistantTransfer(cache: ApiQueryCache | null, id: string) {
  const transfer = cache && transfers.get(cache);
  return transfer?.id === id ? transfer : undefined;
}

export function clearAssistantTransfer(cache: ApiQueryCache | null) {
  if (cache) transfers.delete(cache);
}

export const DEFAULT_STARTERS = [
  {label: 'Разобрать просрочки', prompt: 'Какие работы просрочены и с чего лучше начать?'},
  {label: 'Проверить загрузку', prompt: 'Проверь загрузку работников и ближайшие назначения.'},
  {label: 'Найти оборудование', prompt: 'Помоги найти оборудование и посмотреть его регламент.'},
];

export const EXECUTOR_STARTERS = [
  {label: 'Инструкция по ТО', prompt: 'Найди ближайшее назначенное мне ТО и покажи утверждённую инструкцию и чек-лист.'},
  {label: 'Прикрепить фото', prompt: 'Помоги прикрепить фото к заданию. Уточни задание, пункт чек-листа и этап фото, если я их не указал.'},
  {label: 'Оценить качество', prompt: 'По прикреплённому фото оцени видимые признаки выполнения работы и укажи, что по фото проверить нельзя.'},
];
