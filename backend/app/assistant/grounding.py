"""Mandatory evidence for an explicit equipment-code lookup, independent of LLM routing."""
import re

def equipment_code(question):
    if not re.search(r'оборудован|насос|прибор|агрегат|устройств',question,re.I):return None
    if not re.search(r'найди|найти|покажи|открой|есть ли|существует ли|имеется ли|когда|какие|сколько',question,re.I):return None
    quoted=re.search(r'\bкод(?:ом|у|а)?\s*[:—-]?\s*[«"\']([^»"\'\n]{1,128})[»"\']',question,re.I)
    if quoted:return quoted[1]
    explicit=re.search(r'\bкод(?:ом|у|а)?\s*[:—-]?\s*([\w][\w./-]{1,127})',question,re.I)
    if explicit:return explicit[1].rstrip('.')
    # Bare inventory labels such as ITP-01. A UUID is not guessed or fabricated.
    bare=re.search(r'\b[\w]+[-/][\w./-]+\b',question)
    return bare[0] if bare and len(bare[0])<=128 and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',bare[0]) else None

def regulation_lookup(question):
    return bool(re.search(r'регламент|операци.{0,50}\bТО\b|\bТО\b.{0,50}операци',question,re.I)
        and not re.search(r'создай|добавь|измени|удали|назначь|опубликуй|прими',question,re.I))

def regulation_report(equipment,rows):
    from fastapi import HTTPException
    from .inventory_report import label
    if not isinstance(rows,list) or any(not isinstance(r,dict) or not isinstance(r.get('enabled'),bool) for r in rows):
        raise HTTPException(502,'Неверная форма конфигураций обслуживания')
    published=[r for r in rows if r['enabled']]
    operations={str(r['operation_id']) for r in published if r.get('operation_id')}
    if len(operations)==0 and published:raise HTTPException(502,'Не подтверждён состав операций обслуживания')
    lines=[f"### Регламенты: {label(equipment['asset_code'])} — {label(equipment['name'])}",
        f'Опубликованных конфигураций обслуживания: **{len(published)}**. Различных операций: **{len(operations)}**. Неопубликованных конфигураций: **{len(rows)-len(published)}**.',
        'Источник — сохранённые конфигурации этого оборудования. Наличие или отсутствие заданий в календаре не определяет наличие регламента.']
    if not published:lines.append('Опубликованных регламентов для этого оборудования не найдено. Это не означает отсутствия регламентов у другого оборудования.')
    else:
        lines.extend(['| Операция | Периодичность | Период действия |','|---|---|---|'])
        frequencies=dict(day='день',week='неделя',month='месяц',quarter='квартал',year='год',dates='точные даты',yearly_count='число раз в год')
        for row in published[:25]:
            pattern=row.get('pattern') or {};frequency=pattern.get('frequency');text=frequencies.get(frequency,'не подтверждена')
            if pattern.get('interval'):text+=f", интервал {pattern['interval']}"
            if frequency=='yearly_count':text+=f", {pattern.get('count_per_year','не указано')}"
            if frequency=='dates':text+=', '+', '.join(map(str,pattern.get('dates',[])[:12]))
            lines.append(f"| {label(row.get('title','Без названия'))} | {label(text)} | {label(row.get('valid_from') or 'не указано')} — {label(row.get('valid_until') or 'без конечной даты')} |")
        if len(published)>25:lines.append(f'Показаны первые 25 из {len(published)} конфигураций; количество рассчитано по всему прочитанному списку.')
        lines.append('Будущая дата начала означает, что конфигурация пока не действует. Здесь показана предусмотренная периодичность; необходимость конкретного ТО сегодня проверяется отдельно по календарю и факту выполнения.')
    return '\n'.join(line if i and line.startswith('|') and lines[i-1].startswith('|') else '\n'+line for i,line in enumerate(lines)).strip()
