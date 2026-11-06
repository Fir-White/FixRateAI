import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { DEMO_MODE, request } from "@/shared/api/request";
import { taskPathForRole } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { Icon, type IconName } from "@/shared/ui/Icon";
import "./notifications.css";

interface Notification {
  id: string;
  message: string;
  taskId: string | null;
  createdAt: string;
  readAt: string | null;
}

const endpoint = "/api/v1/maintenance/notifications";

type Tone = "danger" | "warning" | "success" | "neutral";
function presentation(message: string): { label: string; icon: IconName; tone: Tone } {
  const text = message.toLocaleLowerCase("ru-RU");
  if (text.includes("просроч")) return { label: "Сроки", icon: "alert", tone: "danger" };
  if (text.includes("доработ")) return { label: "Доработка", icon: "alert", tone: "warning" };
  if (text.includes("приёмк") || text.includes("приемк")) return { label: "Контроль качества", icon: "quality", tone: "neutral" };
  if (text.includes("принят")) return { label: "Приёмка", icon: "check", tone: "success" };
  if (text.includes("назнач")) return { label: "Новое задание", icon: "tasks", tone: "neutral" };
  return { label: "Событие", icon: "bell", tone: "neutral" };
}

function notificationTime(value: string, timezone: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: timezone }).format(date).replace(" г.", "");
  } catch {
    return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date).replace(" г.", "");
  }
}

export function MaintenanceInbox() {
  const { profile } = useSession();
  const { pathname } = useLocation();
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const version = useRef(0);
  const mounted = useRef(false);
  const busyRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async (initial = false) => {
    if (!profile || busyRef.current) return;
    const current = ++version.current;
    if (initial) setLoading(true);
    try {
      const data = DEMO_MODE ? [] : await request<Notification[]>(endpoint);
      if (mounted.current && current === version.current) { setItems(data); setError(""); }
    } catch {
      if (mounted.current && current === version.current) setError("Не удалось загрузить уведомления. Проверьте соединение и попробуйте снова.");
    } finally {
      if (mounted.current && current === version.current) setLoading(false);
    }
  }, [profile?.userId]);

  useEffect(() => {
    mounted.current = true; setItems([]); setError(""); setOpen(false); busyRef.current = false; setBusy(null);
    void load(true);
    const timer = window.setInterval(() => void load(), 30_000);
    return () => { mounted.current = false; version.current++; window.clearInterval(timer); };
  }, [load]);
  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) { if (!root.current?.contains(event.target as Node)) setOpen(false); }
    function escape(event: KeyboardEvent) { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } }
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);

  const markRead = async (notifications: Notification[]) => {
    if (busyRef.current || !notifications.length) return;
    busyRef.current = true; const current = ++version.current;
    setBusy(notifications.length === 1 ? notifications[0].id : "all"); setError("");
    for (const item of notifications) {
      try {
        const result = await request<{ read: boolean }>(`${endpoint}/${encodeURIComponent(item.id)}/read`, { method: "POST", body: "{}" });
        if (result.read !== true) throw new Error("Read acknowledgement missing");
        if (!mounted.current || current !== version.current) return;
        setItems(previous => previous.map(n => n.id === item.id ? { ...n, readAt: new Date().toISOString() } : n));
      } catch {
        if (mounted.current && current === version.current) setError("Не удалось отметить уведомление прочитанным. Попробуйте ещё раз.");
        break;
      }
    }
    if (mounted.current && current === version.current) { busyRef.current = false; setBusy(null); setLoading(false); }
  };

  if (!profile) return null;
  const unread = items.filter(n => !n.readAt);
  const read = items.filter(n => n.readAt);
  const renderGroup = (title: string, group: Notification[]) => group.length > 0 && <section className="inbox-group" aria-label={title}>
    <h3 className="inbox-group-title">{title}<span>{group.length}</span></h3>
    <ul>{group.map(item => {
      const type = presentation(item.message);
      const path = item.taskId ? taskPathForRole(profile.role, item.taskId) : null;
      const displayTime = notificationTime(item.createdAt, profile.timezone);
      return <li key={item.id} className={`inbox-item ${item.readAt ? "is-read" : "is-unread"}`}>
        <span className={`inbox-item-icon is-${type.tone}`}><Icon name={type.icon} size={17}/></span>
        <div className="inbox-item-body">
          <div className="inbox-item-meta"><span>{type.label}</span>{displayTime && <time dateTime={item.createdAt}>{displayTime}</time>}</div>
          <p className="inbox-item-message">{item.message}</p>
          <div className="inbox-item-actions">
            {path && <Link to={path} onClick={() => { if (!item.readAt) void markRead([item]); setOpen(false); }}>Открыть задание <Icon name="chevron" size={14}/></Link>}
            {!item.readAt && <button type="button" disabled={!!busy} onClick={() => void markRead([item])}>{busy === item.id ? "Сохраняем…" : "Отметить прочитанным"}</button>}
          </div>
        </div>
        {!item.readAt && <span className="inbox-unread-dot" aria-label="Непрочитанное"/>}
      </li>;
    })}</ul>
  </section>;

  return <div className="inbox" ref={root}>
    <button ref={trigger} type="button" className={`inbox-trigger${open ? " is-open" : ""}`} aria-label={loading || (error && !items.length) ? "Уведомления" : `Уведомления, непрочитанных: ${unread.length}`} aria-haspopup="dialog" aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}>
      <Icon name="bell" size={20}/>{unread.length > 0 && <span className="inbox-count" aria-hidden="true">{unread.length > 99 ? "99+" : unread.length}</span>}
      {error && !unread.length && <span className="inbox-error-dot" aria-hidden="true"/>}
    </button>
    {open && <div id={id} className="inbox-panel" role="dialog" aria-label="Уведомления">
      <header className="inbox-header"><div><span className="inbox-eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</span><h2>Уведомления</h2><p>{loading ? "Загрузка…" : error && !items.length ? "Нет связи" : unread.length ? `Непрочитанных: ${unread.length}` : "Всё просмотрено"}</p></div><button type="button" className="inbox-close" aria-label="Закрыть уведомления" onClick={() => { setOpen(false); trigger.current?.focus(); }}><Icon name="close" size={18}/></button></header>
      {error && <div className="inbox-error" role="alert"><span>{error}</span><button type="button" disabled={!!busy} onClick={() => void load(true)}>Повторить</button></div>}
      {loading ? <div className="inbox-empty" role="status"><span className="inbox-empty-icon"><Icon name="bell" size={22}/></span><p>Загружаем уведомления…</p></div> : !items.length && !error ? <div className="inbox-empty"><span className="inbox-empty-icon"><Icon name="check" size={22}/></span><strong>Пока всё спокойно</strong><p>Здесь появятся события по вашим заданиям.</p></div> : <div className="inbox-list">{renderGroup("Новые", unread)}{renderGroup("Прочитанные", read)}</div>}
      {unread.length > 0 && <footer className="inbox-footer"><span>Показано: {items.length}</span><button type="button" disabled={!!busy} onClick={() => void markRead(unread)}>{busy === "all" ? "Сохраняем…" : "Прочитать показанные"}</button></footer>}
    </div>}
  </div>;
}
