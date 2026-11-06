import { memo, useCallback, useId, useMemo, useRef, useState, type ButtonHTMLAttributes, type KeyboardEvent, type RefObject } from "react";
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
export type CalendarMode = "date" | "datetime-local" | "month" | "time";
function readValue(value: string, mode: CalendarMode) {
  const parts = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(value);
  const date = parts ? readDate(`${parts[3] ?? "01"}.${parts[2]}.${parts[1]}`) : null;
  const time = /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(mode === "datetime-local" ? value.split("T")[1] ?? "" : value);
  const validTime = !!time && Number(time[1]) <= 23 && Number(time[2]) <= 59 && Number(time[3] ?? 0) <= 59;
  const validDate = !!date && (mode === "month" ? /^\d{4}-\d{2}$/.test(value) : mode === "date" ? /^\d{4}-\d{2}-\d{2}$/.test(value) : /^\d{4}-\d{2}-\d{2}T/.test(value));
  if (mode === "time" ? !validTime : !validDate || (mode === "datetime-local" && !validTime)) return null;
  return { date, hour: time?.[1] ?? "", minute: time?.[2] ?? "", second: time?.[3] ?? "" };
}
export function calendarValueIssue(mode: CalendarMode, value: string, min?: string, max?: string, required = false) {
  if (!value) return required ? "Выберите значение." : "";
  if (!readValue(value, mode)) return "Укажите существующую дату и корректное время.";
  const comparable = (value: string) => mode === "time" && value.length === 5 || mode === "datetime-local" && value.length === 16 ? `${value}:00` : value;
  if (min && readValue(min, mode) && comparable(value) < comparable(min)) return `Выберите значение не раньше ${min.replace("T", " ")}.`;
  if (max && readValue(max, mode) && comparable(value) > comparable(max)) return `Выберите значение не позже ${max.replace("T", " ")}.`;
  return "";
}
const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const dayFormatter = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" });
const monthFormatter = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" });
const longDate = (date: Date) => dayFormatter.format(date);

// Time entry must not reconcile all calendar cells or rebuild their accessible labels.
const CalendarGrid = memo(function CalendarGrid({ year, monthIndex, selectedText, todayText, monthId, calendar, onSelect, onNavigate, min, max }: {
  year: number;
  monthIndex: number;
  selectedText: string;
  todayText: string;
  monthId: string;
  calendar: RefObject<HTMLDivElement | null>;
  onSelect: (date: Date) => void;
  onNavigate: (event: KeyboardEvent<HTMLButtonElement>, date: Date) => void;
  min?: string;
  max?: string;
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
  const focusText = weeks.flat().find(cell => cell && cell.text === selectedText && !(min && `${String(year).padStart(4,"0")}-${pad(monthIndex+1)}-${pad(cell.day)}` < min || max && `${String(year).padStart(4,"0")}-${pad(monthIndex+1)}-${pad(cell.day)}` > max))?.text
    ?? weeks.flat().find(cell => cell && !(min && `${String(year).padStart(4,"0")}-${pad(monthIndex+1)}-${pad(cell.day)}` < min || max && `${String(year).padStart(4,"0")}-${pad(monthIndex+1)}-${pad(cell.day)}` > max))?.text;
  return <div ref={calendar} role="grid" aria-labelledby={monthId} className="fr-date-grid">
    <div role="row">{weekdays.map(day => <span role="columnheader" key={day}>{day}</span>)}</div>
    {weeks.map((week, index) => <div role="row" key={index}>{week.map((cell, index) => {
      if (!cell) return <span role="gridcell" key={`blank-${index}`} />;
      const { day, date, text, label: dayLabel } = cell;
      const chosen = text === focusText;
      const key = `${String(year).padStart(4,"0")}-${pad(monthIndex+1)}-${pad(day)}`;
      return <span role="gridcell" aria-selected={!!selectedInMonth && text === selectedText} key={day}><button type="button" disabled={!!(min && key < min || max && key > max)} data-day={text} data-today={text === todayText || undefined} data-dialog-autofocus={chosen || undefined} tabIndex={chosen ? 0 : -1} aria-label={dayLabel} onClick={() => onSelect(date)} onKeyDown={event => onNavigate(event, date)}>{day}</button></span>;
    })}</div>)}
  </div>;
});

const monthNames = Array.from({length:12},(_,index)=>new Intl.DateTimeFormat("ru-RU",{month:"long"}).format(calendarDate(2026,index,1)));

export function DateTimeField({ label, value, onChange, disabled = false, mode = "datetime-local", min, max, required = false, hideLabel = false, fieldId, triggerProps, description }: {
  label: string; value: string; onChange: (value: string) => void; disabled?: boolean;
  mode?: CalendarMode; min?: string; max?: string; required?: boolean; hideLabel?: boolean; fieldId?: string;
  triggerProps?: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange" | "value">;
  description?: string;
}) {
  const generatedId = useId();
  const id = fieldId ?? generatedId;
  const calendar = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [hour, setHour] = useState("");
  const [minute, setMinute] = useState("");
  const [second, setSecond] = useState("");
  const [month, setMonth] = useState(() => new Date());
  const [chooseMonth, setChooseMonth] = useState(mode === "month");
  const [yearText, setYearText] = useState("");
  const current = readValue(value, mode);
  const selected = readDate(draft);
  const today = new Date();
  const todayText = dateText(today);
  const selectedText = selected ? dateText(selected) : "";
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const hasTime = mode === "time" || mode === "datetime-local";
  const showSeconds = second !== "" && second !== "00";
  const validTime = /^\d{1,2}$/.test(hour) && Number(hour) <= 23 && /^\d{1,2}$/.test(minute) && Number(minute) <= 59 && (!second || /^\d{1,2}$/.test(second) && Number(second) <= 59);
  const dateKey = selected ? `${String(selected.getFullYear()).padStart(4,"0")}-${pad(selected.getMonth()+1)}-${pad(selected.getDate())}` : "";
  const timeKey = `${pad(Number(hour))}:${pad(Number(minute))}${second ? `:${pad(Number(second))}` : ""}`;
  const nextValue = mode === "time" ? timeKey : mode === "month" ? dateKey.slice(0,7) : mode === "date" ? dateKey : `${dateKey}T${timeKey}`;
  const issue = calendarValueIssue(mode, nextValue, min, max, true);
  const validYear = /^\d{4}$/.test(yearText) && Number(yearText) >= 1;
  const canApply = !issue && (!hasTime || validTime) && (!chooseMonth || validYear);
  const minDay = mode === "date" || mode === "datetime-local" ? min?.slice(0,10) : undefined;
  const maxDay = mode === "date" || mode === "datetime-local" ? max?.slice(0,10) : undefined;

  function show() {
    const date = current?.date ?? today;
    setDraft(dateText(date));
    setHour(current?.hour ?? ""); setMinute(current?.minute ?? ""); setSecond(current?.second ?? "");
    setYearText(String(date.getFullYear()).padStart(4,"0"));
    setChooseMonth(mode === "month");
    setMonth(previous => previous.getFullYear() === date.getFullYear() && previous.getMonth() === date.getMonth() ? previous : calendarDate(date.getFullYear(), date.getMonth(), 1));
    setOpen(true);
  }
  const select = useCallback((date: Date, focus = false) => {
    if (date.getFullYear() < 1 || date.getFullYear() > 9999) return;
    const key = `${String(date.getFullYear()).padStart(4,"0")}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
    if (minDay && key < minDay || maxDay && key > maxDay) return;
    const text = dateText(date);
    setDraft(text);
    setMonth(previous => previous.getFullYear() === date.getFullYear() && previous.getMonth() === date.getMonth() ? previous : calendarDate(date.getFullYear(), date.getMonth(), 1));
    if (focus) requestAnimationFrame(() => calendar.current?.querySelector<HTMLButtonElement>(`[data-day="${text}"]`)?.focus());
  }, [minDay,maxDay]);
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
    event.preventDefault(); select(next, true);
  }, [year, monthIndex, select]);
  function apply() { if (!canApply || disabled) return; onChange(nextValue); setOpen(false); }
  const display = current ? mode === "time" ? `${current.hour}:${current.minute}${current.second && current.second !== "00" ? `:${current.second}` : ""}` : mode === "month" ? monthFormatter.format(current.date!).replace(/ г\.$/, "") : longDate(current.date!).replace(/ г\.$/, "") : mode === "time" ? "Выбрать время" : mode === "month" ? "Выбрать месяц" : "Выбрать дату";
  return <div className="fr-datetime-field">
    {!hideLabel && <label htmlFor={id}>{label}</label>}
    <button {...triggerProps} id={id} type="button" data-value={value} className="fr-datetime-trigger" disabled={disabled} onClick={show} aria-haspopup="dialog" aria-expanded={open && !disabled}>
      <Icon name={mode === "time" ? "clock" : "calendar"} size={19} />
      <span className={current ? "" : "fr-datetime-placeholder"}>{display}</span>
      {mode === "datetime-local" && <span className="fr-datetime-time"><Icon name="clock" size={14} />{current ? `${current.hour}:${current.minute}` : "Время"}</span>}
    </button>
    {open && !disabled && <Modal open instant className="fr-datetime-dialog" title={label} description={description ?? (mode === "datetime-local" ? "Выберите дату и укажите время в часовом поясе устройства." : mode === "time" ? "Укажите часы и минуты." : mode === "month" ? "Выберите месяц и год." : "Выберите дату в календаре.")} onClose={() => setOpen(false)} footer={<>
      {value && !required && <Button type="button" variant="ghost" onClick={() => { onChange(""); setOpen(false); }}>Очистить</Button>}
      <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Отмена</Button>
      <Button type="button" disabled={!canApply} onClick={apply}>Применить</Button>
    </>}>
      <div className="fr-datetime-picker">
        {mode !== "time" && <>
          {chooseMonth ? <>
            <div className="fr-datetime-month"><button type="button" aria-label="Предыдущий год" disabled={year<=1} onClick={()=>{setMonth(calendarDate(year-1,monthIndex,1));setYearText(String(year-1).padStart(4,"0"));}}><Icon name="back" size={18}/></button><label className="fr-calendar-year">Год<input aria-label="Год календаря" inputMode="numeric" maxLength={4} value={yearText} onChange={event=>{const text=event.target.value.replace(/\D/g,"");setYearText(text);if(text.length===4&&Number(text)>0)setMonth(calendarDate(Number(text),monthIndex,1));}}/></label><button type="button" aria-label="Следующий год" disabled={year>=9999} onClick={()=>{setMonth(calendarDate(year+1,monthIndex,1));setYearText(String(year+1).padStart(4,"0"));}}><Icon name="back" size={18} className="rotate-180"/></button></div>
            <div className="fr-calendar-months" role="group" aria-label="Выбор месяца">{monthNames.map((name,index)=>{const key=`${String(year).padStart(4,"0")}-${pad(index+1)}`;return <button key={name} type="button" aria-pressed={selected?.getFullYear()===year&&selected.getMonth()===index} disabled={!validYear || mode==="month"&&!!(min&&key<min||max&&key>max)} onClick={()=>{const day=mode==="month"?1:Math.min(selected?.getDate()??1,calendarDate(year,index+1,0).getDate());setDraft(dateText(calendarDate(year,index,day)));setMonth(calendarDate(year,index,1));if(mode!=="month")setChooseMonth(false);}}>{name}</button>;})}</div>
          </> : <>
            <div className="fr-datetime-month">
              <button type="button" aria-label="Предыдущий месяц" disabled={year === 1 && monthIndex === 0} onClick={() => setMonth(calendarDate(year, monthIndex - 1, 1))}><Icon name="back" size={18} /></button>
              <h3 id={`${id}-month`} aria-live="polite"><button type="button" aria-label="Выбрать месяц и год" onClick={()=>{setYearText(String(year));setChooseMonth(true);}}>{monthFormatter.format(month)}</button></h3>
              <button type="button" aria-label="Следующий месяц" disabled={year === 9999 && monthIndex === 11} onClick={() => setMonth(calendarDate(year, monthIndex + 1, 1))}><Icon name="back" size={18} className="rotate-180" /></button>
            </div>
            <CalendarGrid year={year} monthIndex={monthIndex} selectedText={selectedText} todayText={todayText} monthId={`${id}-month`} calendar={calendar} onSelect={select} onNavigate={navigate} min={minDay} max={maxDay}/>
          </>}
        </>}
        {mode !== "month" && <div className={`fr-datetime-entry ${mode !== "datetime-local" || second ? "fr-datetime-entry--single" : ""}`}>
          {mode !== "time" && <label>Дата<input inputMode="numeric" placeholder="ДД.ММ.ГГГГ" value={draft} aria-invalid={!selected || undefined} onChange={event => { const digits = event.target.value.replace(/\D/g, "").slice(0, 8); const text = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join("."); setDraft(text); const parsed = readDate(text); if (parsed) setMonth(calendarDate(parsed.getFullYear(), parsed.getMonth(), 1)); }} /></label>}
          {hasTime && <fieldset><legend>Время</legend><div className={showSeconds ? "fr-calendar-time-seconds" : ""}><label><span className={mode==="time"?"fr-time-unit-label":"sr-only"}>Часы</span><input aria-label="Часы" data-dialog-autofocus={mode==="time"||undefined} inputMode="numeric" placeholder="ЧЧ" maxLength={2} value={hour} onChange={event => setHour(event.target.value.replace(/\D/g, ""))} onBlur={() => { if (hour && Number(hour) <= 23) setHour(pad(Number(hour))); }} /></label><span aria-hidden="true">:</span><label><span className={mode==="time"?"fr-time-unit-label":"sr-only"}>Минуты</span><input aria-label="Минуты" inputMode="numeric" placeholder="ММ" maxLength={2} value={minute} onChange={event => setMinute(event.target.value.replace(/\D/g, ""))} onBlur={() => { if (minute && Number(minute) <= 59) setMinute(pad(Number(minute))); }} /></label>{showSeconds && <><span aria-hidden="true">:</span><input aria-label="Секунды" inputMode="numeric" maxLength={2} value={second} onChange={event=>setSecond(event.target.value.replace(/\D/g,""))}/></>}</div></fieldset>}
        </div>}
        <div className="fr-datetime-shortcuts">{mode !== "time" && <button type="button" onClick={() => {select(new Date());if(mode==="month")setYearText(String(today.getFullYear()));}}>Сегодня</button>}{hasTime && <button type="button" onClick={() => { const now = new Date(); setHour(pad(now.getHours())); setMinute(pad(now.getMinutes())); }}>Текущее время</button>}</div>
        {(!selected && mode !== "time" || hasTime && (!!hour && Number(hour)>23 || !!minute && Number(minute)>59) || issue) && <p role="status" className="fr-datetime-error">{issue || "Укажите существующую дату и время от 00:00 до 23:59."}</p>}
      </div>
    </Modal>}
  </div>;
}
