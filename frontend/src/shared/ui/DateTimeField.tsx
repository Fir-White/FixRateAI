import { memo, useCallback, useId, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { Modal } from "./Modal";
import "./date-time-field.css";

// These are local calendar values. UTC conversion belongs to the existing API consumer.
function calendarDate(year: number, month: number, day: number) {
  const date = new Date(0);
  date.setHours(12, 0, 0, 0);
  date.setFullYear(year, month, day);
  return date;
}
const pad = (value: number) => String(value).padStart(2, "0");
const dateText = (date: Date) => `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${String(date.getFullYear()).padStart(4, "0")}`;
function readDate(text: string) {
  const match = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(text);
  if (!match) return null;
  const [, day, month, year] = match.map(Number);
  const date = calendarDate(year, month - 1, day);
  return year >= 1 && year <= 9999 && date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
}
function readValue(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  return match ? { date: readDate(`${match[3]}.${match[2]}.${match[1]}`), hour: match[4], minute: match[5] } : null;
}
const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const dayFormatter = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" });
const monthFormatter = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" });
const longDate = (date: Date) => dayFormatter.format(date);

// Time entry must not reconcile all calendar cells or rebuild their accessible labels.
const CalendarGrid = memo(function CalendarGrid({ year, monthIndex, selectedText, todayText, monthId, calendar, onSelect, onNavigate }: {
  year: number;
  monthIndex: number;
  selectedText: string;
  todayText: string;
  monthId: string;
  calendar: RefObject<HTMLDivElement | null>;
  onSelect: (date: Date) => void;
  onNavigate: (event: KeyboardEvent<HTMLButtonElement>, date: Date) => void;
}) {
  const selectedInMonth = selectedText.endsWith(`.${pad(monthIndex + 1)}.${String(year).padStart(4, "0")}`);
  const weeks = useMemo(() => {
    const first = (calendarDate(year, monthIndex, 1).getDay() + 6) % 7;
    const count = calendarDate(year, monthIndex + 1, 0).getDate();
    const cells = Array.from({ length: Math.ceil((first + count) / 7) * 7 }, (_, index) => {
      const day = index - first + 1;
      if (day < 1 || day > count) return null;
      const date = calendarDate(year, monthIndex, day);
      return { day, date, text: dateText(date), label: longDate(date) };
    });
    return Array.from({ length: cells.length / 7 }, (_, week) => cells.slice(week * 7, week * 7 + 7));
  }, [year, monthIndex]);
  return <div ref={calendar} role="grid" aria-labelledby={monthId} className="fr-date-grid">
    <div role="row">{weekdays.map(day => <span role="columnheader" key={day}>{day}</span>)}</div>
    {weeks.map((week, index) => <div role="row" key={index}>{week.map((cell, index) => {
      if (!cell) return <span role="gridcell" key={`blank-${index}`} />;
      const { day, date, text, label: dayLabel } = cell;
      const chosen = selectedInMonth ? text === selectedText : day === 1;
      return <span role="gridcell" aria-selected={!!selectedInMonth && chosen} key={day}><button type="button" data-day={text} data-today={text === todayText || undefined} data-dialog-autofocus={chosen || undefined} tabIndex={chosen ? 0 : -1} aria-label={dayLabel} onClick={() => onSelect(date)} onKeyDown={event => onNavigate(event, date)}>{day}</button></span>;
    })}</div>)}
  </div>;
});

export function DateTimeField({ label, value, onChange, disabled = false }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const calendar = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [hour, setHour] = useState("");
  const [minute, setMinute] = useState("");
  const [month, setMonth] = useState(() => new Date());
  const current = readValue(value);
  const selected = readDate(draft);
  const today = new Date();
  const todayText = dateText(today);
  const selectedText = selected ? dateText(selected) : "";
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const validTime = /^\d{1,2}$/.test(hour) && Number(hour) <= 23 && /^\d{1,2}$/.test(minute) && Number(minute) <= 59;

  function show() {
    const date = current?.date ?? today;
    setDraft(dateText(date));
    setHour(current?.hour ?? "");
    setMinute(current?.minute ?? "");
    setMonth(previous => previous.getFullYear() === date.getFullYear() && previous.getMonth() === date.getMonth() ? previous : calendarDate(date.getFullYear(), date.getMonth(), 1));
    setOpen(true);
  }
  const select = useCallback((date: Date, focus = false) => {
    if (date.getFullYear() < 1 || date.getFullYear() > 9999) return;
    const text = dateText(date);
    setDraft(text);
    setMonth(previous => previous.getFullYear() === date.getFullYear() && previous.getMonth() === date.getMonth() ? previous : calendarDate(date.getFullYear(), date.getMonth(), 1));
    if (focus) requestAnimationFrame(() => calendar.current?.querySelector<HTMLButtonElement>(`[data-day="${text}"]`)?.focus());
  }, []);
  const navigate = useCallback((event: KeyboardEvent<HTMLButtonElement>, date: Date) => {
    const offset = ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 } as Record<string, number>)[event.key];
    let next: Date;
    if (offset) next = calendarDate(year, monthIndex, date.getDate() + offset);
    else if (event.key === "Home" || event.key === "End") {
      const weekday = (date.getDay() + 6) % 7;
      next = calendarDate(year, monthIndex, date.getDate() + (event.key === "Home" ? -weekday : 6 - weekday));
    } else if (event.key === "PageUp" || event.key === "PageDown") {
      const target = monthIndex + (event.key === "PageUp" ? -1 : 1);
      next = calendarDate(year, target, Math.min(date.getDate(), calendarDate(year, target + 1, 0).getDate()));
    } else return;
    event.preventDefault();
    select(next, true);
  }, [year, monthIndex, select]);
  function apply() {
    if (!selected || !validTime || disabled) return;
    onChange(`${String(selected.getFullYear()).padStart(4, "0")}-${pad(selected.getMonth() + 1)}-${pad(selected.getDate())}T${pad(Number(hour))}:${pad(Number(minute))}`);
    setOpen(false);
  }

  return <div className="fr-datetime-field">
    <label htmlFor={id}>{label}</label>
    <button id={id} type="button" className="fr-datetime-trigger" disabled={disabled} onClick={show} aria-haspopup="dialog" aria-expanded={open && !disabled}>
      <Icon name="calendar" size={19} />
      <span className={current?.date ? "" : "fr-datetime-placeholder"}>{current?.date ? longDate(current.date).replace(/ г\.$/, "") : "Выбрать дату"}</span>
      <span className="fr-datetime-time"><Icon name="clock" size={14} />{current ? `${current.hour}:${current.minute}` : "Время"}</span>
    </button>
    {open && !disabled && <Modal open instant className="fr-datetime-dialog" title={label} description="Выберите дату и укажите время в часовом поясе устройства." onClose={() => setOpen(false)} footer={<>
      {value && <Button type="button" variant="ghost" onClick={() => { onChange(""); setOpen(false); }}>Очистить</Button>}
      <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Отмена</Button>
      <Button type="button" disabled={!selected || !validTime} onClick={apply}>Применить</Button>
    </>}>
      <div className="fr-datetime-picker">
        <div className="fr-datetime-month">
          <button type="button" aria-label="Предыдущий месяц" disabled={year === 1 && monthIndex === 0} onClick={() => setMonth(calendarDate(year, monthIndex - 1, 1))}><Icon name="back" size={18} /></button>
          <h3 id={`${id}-month`} aria-live="polite">{monthFormatter.format(month)}</h3>
          <button type="button" aria-label="Следующий месяц" disabled={year === 9999 && monthIndex === 11} onClick={() => setMonth(calendarDate(year, monthIndex + 1, 1))}><Icon name="back" size={18} className="rotate-180" /></button>
        </div>
        <CalendarGrid year={year} monthIndex={monthIndex} selectedText={selectedText} todayText={todayText} monthId={`${id}-month`} calendar={calendar} onSelect={select} onNavigate={navigate}/>
        <div className="fr-datetime-entry">
          <label>Дата<input inputMode="numeric" placeholder="ДД.ММ.ГГГГ" value={draft} aria-invalid={!selected || undefined} onChange={event => { const digits = event.target.value.replace(/\D/g, "").slice(0, 8); const text = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join("."); setDraft(text); const parsed = readDate(text); if (parsed) setMonth(calendarDate(parsed.getFullYear(), parsed.getMonth(), 1)); }} /></label>
          <fieldset><legend>Время</legend><div><label><span className="sr-only">Часы</span><input aria-label="Часы" inputMode="numeric" placeholder="ЧЧ" maxLength={2} value={hour} onChange={event => setHour(event.target.value.replace(/\D/g, ""))} onBlur={() => { if (hour && Number(hour) <= 23) setHour(pad(Number(hour))); }} /></label><span aria-hidden="true">:</span><label><span className="sr-only">Минуты</span><input aria-label="Минуты" inputMode="numeric" placeholder="ММ" maxLength={2} value={minute} onChange={event => setMinute(event.target.value.replace(/\D/g, ""))} onBlur={() => { if (minute && Number(minute) <= 59) setMinute(pad(Number(minute))); }} /></label></div></fieldset>
        </div>
        <div className="fr-datetime-shortcuts"><button type="button" onClick={() => select(new Date())}>Сегодня</button><button type="button" onClick={() => { const now = new Date(); setHour(pad(now.getHours())); setMinute(pad(now.getMinutes())); }}>Текущее время</button></div>
        {(!selected || (!!hour && Number(hour) > 23) || (!!minute && Number(minute) > 59)) && <p role="status" className="fr-datetime-error">Укажите существующую дату и время от 00:00 до 23:59.</p>}
      </div>
    </Modal>}
  </div>;
}
