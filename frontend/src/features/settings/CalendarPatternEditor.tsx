import { useEffect, useState,useRef } from "react";
import { managementApi } from "@/shared/api/management";
import type { CalendarPattern } from "@/shared/types/management";
import { patternDefaults } from "@/shared/types/management";
import { FieldCaption, Input, Select  } from "@/shared/ui/Form";
import { Button } from "@/shared/ui/Button";

const frequencies: [CalendarPattern["frequency"], string][] = [["day","Дни"],["week","Недели"],["month","Месяцы"],["quarter","Календарные кварталы"],["year","Годы и сезоны"],["yearly_count","Заданное число раз в год"],["dates","Конкретные даты"]];
const weekdays=["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];

export function CalendarPatternEditor({value,onChange,disabled=false,rolling=false}: {value: CalendarPattern; onChange: (value: CalendarPattern)=>void; disabled?: boolean; rolling?:boolean}) {
  const set = (part: Partial<CalendarPattern>) => onChange({...value,...part});
  const periods=["month","quarter","year","yearly_count"].includes(value.frequency);
  const [year,setYear]=useState(Number(value.anchor_date.slice(0,4))||2026);
  const [month,setMonth]=useState(Number(value.anchor_date.slice(5,7))||1);
  const [preview,setPreview]=useState<{dates:string[];explanation:string}|null>(null);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const requestId=useRef(0);
  useEffect(()=>{requestId.current+=1;setPreview(null);setError('');setBusy(false);},[value,year,month]);
  useEffect(()=>()=>{requestId.current+=1;},[]);
  return <fieldset disabled={disabled} className="space-y-4 rounded-xl border border-line p-4">
    <legend className="px-2 font-semibold">Периодичность</legend>
    <div className="grid gap-4 sm:grid-cols-3">
      <label className="space-y-1 text-sm"><FieldCaption>Повторять по
        </FieldCaption><Select aria-label="Повторять по" value={value.frequency} onChange={event=>onChange({...patternDefaults(value.anchor_date,event.target.value as CalendarPattern["frequency"]),excluded_dates:value.excluded_dates})}>
          {frequencies.filter(([key])=>!rolling||["day","month","year"].includes(key)).map(([key,title])=><option key={key} value={key}>{title}</option>)}
        </Select>
      </label>
      <label className="space-y-1 text-sm"><FieldCaption>Не раньше даты
        </FieldCaption><Input aria-label="Не раньше даты" required type="date" min="2000-01-01" max="2100-12-31" value={value.anchor_date} onChange={event=>set({anchor_date:event.target.value})}/>
      </label>
      {value.frequency!=="dates" && <label className="space-y-1 text-sm"><FieldCaption>{{day:'Дней между повторениями',week:'Недель между повторениями',month:'Месяцев между повторениями',quarter:'Кварталов между повторениями',year:'Лет между циклами',yearly_count:'Лет между циклами'}[value.frequency]}
        </FieldCaption><Input aria-label="Интервал повторения" required type="number" min={1} max={10000} value={value.interval} onChange={event=>set({interval:Number(event.target.value)})}/>
      </label>}
    </div>
    {["week","yearly_count"].includes(value.frequency) && <div><p className="mb-2 text-sm">Дни недели</p><div className="flex flex-wrap gap-3">{weekdays.map((name,index)=><label key={name} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm">
      <input aria-label={name} type="checkbox" checked={value.weekdays.includes(index+1)} onChange={event=>set({weekdays:event.target.checked ? [...value.weekdays,index+1].sort((a,b)=>a-b) : value.weekdays.filter(day=>day!==index+1)})}/>{name}
    </label>)}</div><p className="mt-2 text-xs text-muted">Без выбора: для недель — день недели опорной даты; для числа повторений в год — любые дни.</p></div>}
    {!rolling&&value.frequency!=="dates" && <label className="block space-y-1 text-sm"><FieldCaption>Чётность недели
      </FieldCaption><Select aria-label="Чётность недели" value={value.week_parity} onChange={event=>set({week_parity:event.target.value as CalendarPattern["week_parity"]})}>
        <option value="any">Любая неделя</option><option value="even">Чётные недели ISO</option><option value="odd">Нечётные недели ISO</option>
      </Select><p className="text-xs text-muted"><FieldCaption>Неделя начинается в понедельник. Чётность определяется номером ISO-недели; 53-я и следующая 1-я — обе нечётные. Для непрерывного цикла «через неделю» задайте интервал 2.</FieldCaption></p>
    </label>}
    {value.frequency==="quarter" && <label className="block space-y-1 text-sm"><FieldCaption>Граница квартала
      </FieldCaption><Select aria-label="Граница квартала" value={value.period_edge} onChange={event=>set({period_edge:event.target.value as "start"|"end"})}><option value="start">Начало: январь, апрель, июль, октябрь</option><option value="end">Конец: март, июнь, сентябрь, декабрь</option></Select>
    </label>}
    {!rolling&&periods && <div className="grid gap-4 sm:grid-cols-2">
      <NumberList label="Дни месяца" values={value.month_days} onChange={days=>set({month_days:days})} hint={value.frequency==='yearly_count' ? '-1 — последний день. Без выбора разрешён любой день месяца.' : '-1 — последний день. Без выбора: день опоры; для квартала — выбранная граница.'}/>
      <label className="space-y-1 text-sm"><FieldCaption>Если дня нет в месяце
        </FieldCaption><Select aria-label="Если дня нет в месяце" value={value.short_month} onChange={event=>set({short_month:event.target.value as "last_day"|"skip"})}><option value="last_day">Последний день месяца</option><option value="skip">Пропустить этот месяц</option></Select>
      </label>
    </div>}
    {!rolling&&["year","yearly_count"].includes(value.frequency) && <div><p className="mb-2 text-sm">Месяцы повторения</p><div className="grid grid-cols-4 gap-2 sm:grid-cols-6">{Array.from({length:12},(_,i)=>i+1).map(month=><label key={month} className="flex items-center gap-2 text-sm"><input type="checkbox" aria-label={`Месяц ${month}`} checked={value.months.includes(month)} onChange={event=>set({months:event.target.checked ? [...value.months,month].sort((a,b)=>a-b) : value.months.filter(item=>item!==month)})}/>{new Intl.DateTimeFormat("ru-RU",{month:"short",timeZone:"UTC"}).format(new Date(Date.UTC(2026,month-1,1)))}</label>)}</div><p className="mt-2 text-xs text-muted">Без выбора: для годового цикла — месяц опоры, для числа повторений — весь год.</p></div>}
    {value.frequency==="yearly_count" && <label className="block space-y-1 text-sm"><FieldCaption>Повторений за календарный год
      </FieldCaption><Input aria-label="Повторений за календарный год" required type="number" min={1} max={366} value={value.count_per_year??5} onChange={event=>set({count_per_year:Number(event.target.value)})}/>
      <p className="text-xs text-muted"><FieldCaption>Даты распределяются среди допустимых дней конкретного календарного года с учётом фильтров. Если дней недостаточно, расчёт покажет причину. В первый неполный год остаётся соответствующая часть графика.</FieldCaption></p>
    </label>}
    {value.frequency==="dates" && <DateList label="Даты обслуживания" values={value.dates} onChange={dates=>set({dates})} required/>}
    {!rolling&&<DateList label="Исключить даты" values={value.excluded_dates} onChange={excluded_dates=>set({excluded_dates})}/>}
    {!rolling&&<section aria-label="Предпросмотр периодичности" className="space-y-3 border-t border-line pt-4"><p className="text-sm font-semibold">Проверить даты до сохранения</p><div className="flex flex-wrap items-end gap-3">
      <label className="text-sm"><FieldCaption>Год</FieldCaption><Input aria-label="Год предпросмотра" type="number" min={2000} max={2100} value={year} onChange={e=>setYear(Number(e.target.value))}/></label>
      <label className="text-sm"><FieldCaption>Месяц</FieldCaption><Select aria-label="Месяц предпросмотра" value={month} onChange={e=>setMonth(Number(e.target.value))}>{Array.from({length:12},(_,i)=>i+1).map(m=><option key={m} value={m}>{new Intl.DateTimeFormat('ru-RU',{month:'long',timeZone:'UTC'}).format(new Date(Date.UTC(2026,m-1,1)))}</option>)}</Select></label>
      <Button type="button" variant="secondary" disabled={busy} onClick={async event=>{
        const invalid=event.currentTarget.closest('fieldset')?.querySelector<HTMLInputElement>('input:invalid,select:invalid');
        if(invalid){invalid.reportValidity();return;}
        const current=++requestId.current;setBusy(true);setError('');setPreview(null);
        try{const result=await managementApi.previewPattern(value,year,month);if(requestId.current===current)setPreview(result);}
        catch(failure){if(requestId.current===current)setError(failure instanceof Error?failure.message:'Предпросмотр недоступен');}
        finally{if(requestId.current===current)setBusy(false);}
      }}>{busy?'Расчёт дат…':'Показать даты периодичности'}</Button>
    </div><p className="text-xs text-muted">Проверяется только календарное правило. Период действия оборудования, история и занятость учитываются при полном расчёте и подборе. Задания и назначения не создаются.</p>
      {error&&<p role="alert" className="text-sm text-amber-200">{error}</p>}
      {preview&&<><p className="text-xs text-muted">{preview.explanation}</p><ul className="flex flex-wrap gap-2">{preview.dates.map(day=><li key={day} className="rounded-lg border border-line px-2 py-1 text-sm">{day}</li>)}</ul>{!preview.dates.length&&<p className="text-sm">В этом месяце дат нет.</p>}</>}
    </section>}
  </fieldset>;
}

function NumberList({label,values,onChange,hint}: {label:string;values:number[];onChange:(values:number[])=>void;hint:string}) {
  const [text,setText]=useState(values.join(", "));
  useEffect(()=>setText(values.join(", ")),[values]);
  return <label className="space-y-1 text-sm"><FieldCaption>{label}</FieldCaption><Input aria-label={label} value={text} placeholder="Например: 1, 15, -1" onChange={event=>{
    const raw=event.target.value;setText(raw);
    const parts=raw.trim() ? raw.split(",").map(v=>Number(v.trim())) : [];
    const valid=parts.every(n=>Number.isInteger(n)&&(n===-1||n>=1&&n<=31))&&new Set(parts).size===parts.length;
    event.target.setCustomValidity(valid ? "" : "Укажите уникальные дни 1–31 через запятую; -1 означает последний день.");
    if(valid) onChange(parts);
  }}/><p className="text-xs text-muted"><FieldCaption>{hint}</FieldCaption></p></label>;
}

function DateList({label,values,onChange,required=false}: {label:string;values:string[];onChange:(values:string[])=>void;required?:boolean}) {
  const [day,setDay]=useState("");
  return <div className="space-y-2"><p className="text-sm"><FieldCaption>{label}</FieldCaption></p><div className="flex flex-wrap items-center gap-2">
    <Input aria-label={`${label}: новая дата`} type="date" value={day} onChange={event=>setDay(event.target.value)} className="max-w-52"/>
    <Button variant="secondary" type="button" disabled={!day||values.includes(day)} onClick={()=>{onChange([...values,day].sort());setDay("");}}>Добавить дату</Button>
  </div>{required&&!values.length&&<p className="text-xs text-amber-200"><FieldCaption>Добавьте хотя бы одну дату.</FieldCaption></p>}
  <div className="flex flex-wrap gap-2">{values.map(value=><Button key={value} variant="ghost" type="button" onClick={()=>onChange(values.filter(item=>item!==value))} aria-label={`Убрать ${value}`}>{value} ×</Button>)}</div></div>;
}
