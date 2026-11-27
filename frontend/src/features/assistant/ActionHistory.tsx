import { useState } from "react";
import { Link } from "react-router-dom";
import { assistantApi, type ActionHistoryItem } from "@/shared/api/assistant";
import { dateTimeFormatter } from "@/shared/lib/dateTimeFormatter";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { Button } from "@/shared/ui/Button";
import { ErrorState, LoadingState } from "@/shared/ui/States";

const statusLabels: Record<ActionHistoryItem["status"], string> = {
  proposed: "Ожидает подтверждения",
  expired: "Срок подтверждения истёк",
  rejected: "Отклонено",
  executing: "Подтверждено · выполняется",
  succeeded: "Выполнено",
  failed: "Ошибка выполнения",
  uncertain: "Исход неизвестен",
  stale: "Данные изменились",
};

const verificationLabels = {
  confirmed: "Результат проверен",
  failed: "Проверка результата обнаружила расхождение",
  unverified: "Результат требует проверки",
};

const failureLabels: Record<number, string> = {
  403: "Действие недоступно с текущими правами",
  404: "Запись недоступна",
  409: "Данные изменились перед выполнением",
  422: "Сервер отклонил параметры действия",
};

export function ActionHistory({ timezone }: { timezone: string }) {
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const query = useApiQuery(
    () => assistantApi.actionHistory(offset),
    [offset, refresh],
    page => page.items.some(item => item.status === "executing"),
  );
  const date = dateTimeFormatter("ru-RU", {
    timeZone: timezone, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
  const renderTime = (value: string) => <time dateTime={value}>{date.format(new Date(value))}</time>;

  return (
    <section className="assistant-records" aria-labelledby="assistant-action-heading">
      <header className="assistant-records-heading">
        <h2 id="assistant-action-heading">История действий</h2>
        {query.status === "success" && <Button variant="ghost" onClick={() => setRefresh(value => value + 1)}>Обновить</Button>}
      </header>
      {query.status === "loading" && <LoadingState label="Загрузка истории действий" />}
      {query.status === "error" && (
        <ErrorState description={query.error} action={<Button onClick={() => setRefresh(value => value + 1)}>Повторить</Button>} />
      )}
      {query.status === "success" && <>
        {query.data.total === 0 && <p className="assistant-records-empty">Предложений и действий пока нет.</p>}
        {query.data.items.length > 0 && (
          <ul className="assistant-record-list" aria-label="Действия помощника">
            {query.data.items.map(item => (
              <li key={item.action_id}>
                <div className="assistant-record-main">
                  <h3>{item.title}</h3>
                  <Link to={`/assistant?chat=${encodeURIComponent(item.conversation_id)}`}>{item.conversation_title}</Link>
                  {item.target_id && <small>ID записи {item.target_id}</small>}
                </div>
                <div className="assistant-record-state">
                  <strong data-status={item.status}>{statusLabels[item.status]}</strong>
                  {item.verification && <small>{verificationLabels[item.verification]}</small>}
                  {item.failure_code !== null && <small>{failureLabels[item.failure_code] ?? "Сервер вернул ошибку"}</small>}
                </div>
                <div className="assistant-record-time">
                  {renderTime(item.finished_at ?? item.confirmed_at ?? item.created_at)}
                  <small>{query.data.actor}</small>
                </div>
              </li>
            ))}
          </ul>
        )}
        {query.data.total > query.data.limit || offset > 0 ? (
          <div className="assistant-record-pages">
            <Button variant="ghost" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - query.data.limit))}>Назад</Button>
            <span>{query.data.items.length ? `${offset + 1}–${offset + query.data.items.length} из ${query.data.total}` : "Записей на странице нет"}</span>
            <Button variant="ghost" disabled={offset + query.data.limit >= query.data.total} onClick={() => setOffset(offset + query.data.limit)}>Далее</Button>
          </div>
        ) : null}
      </>}
    </section>
  );
}
