"""Mandatory evidence for an explicit equipment-code lookup, independent of LLM routing."""
import re


def equipment_listing(question):
    from .intents import mutation_requested
    if mutation_requested(question):return False
    pieces=[part.strip().casefold() for part in re.split(r'[?!\.\n]',question.strip()) if part.strip()]
    if not pieces:return False
    first=pieces[0]
    for part in pieces[1:]:
        if not re.fullmatch(r'(?:(?:назови|покажи|укажи) (?:его|их) (?:название|названия) и (?:инвентарный код|инвентарные коды)|ничего не (?:меняй|изменяй)|не выполняй никаких действий)',part):return False
    return bool(re.fullmatch(r'(?:(?:какое|какие) оборудование (?:есть|зарегистрировано|установлено|доступно) (?:на|в) (?:текущем|этом) объекте|(?:покажи|перечисли)(?: всё| все)? оборудование(?: на (?:текущем|этом) объекте| текущего объекта)?|(?:список|реестр) оборудования(?: текущего объекта)?)',first))


def equipment_listing_report(value):
    from fastapi import HTTPException
    from .inventory_report import label
    if not isinstance(value,dict) or type(value.get('total')) is not int or value['total']<0 or not isinstance(value.get('items'),list):
        raise HTTPException(502,'Неверная форма списка оборудования')
    rows=value['items'];total=value['total']
    if len(rows)>total or (total and not rows) or any(not isinstance(row,dict) or not row.get('equipment_id') or not row.get('name') or not row.get('asset_code') for row in rows):
        raise HTTPException(502,'Противоречивый список оборудования')
    lines=['### Оборудование текущего объекта',f'Доступных записей в проверенном реестре: **{total}**.']
    if not total:lines.append('Проверенный реестр оборудования текущего объекта пуст. Это не говорит о других объектах или Excel-файлах.')
    else:
        lines.extend(['| Название | Инвентарный код |','|---|---|'])
        lines.extend(f"| {label(row['name'])} | {label(row['asset_code'])} |" for row in rows)
        if len(rows)<total:lines.append(f'Показано {len(rows)} из {total} записей. Это страница, а не полный перечень; остальные записи доступны в реестре.')
    return '\n\n'.join(lines[:2])+('\n\n'+'\n'.join(lines[2:]) if len(lines)>2 else '')


def failed_read_report(observations,tools):
    reads=[row for row in observations if row.get('tool') in tools and tools[row['tool']].mode=='read']
    if not reads or any('result' in row for row in reads):return None
    errors=[row for row in reads if 'error' in row]
    if len(errors)!=len(reads):return None
    codes={row.get('status_code') for row in errors}
    lines=['Не удалось получить запрошенные данные. Проверка не завершена; это не подтверждает отсутствие записей.']
    if codes & {401,403}:lines.append('Часть запросов отклонена проверкой доступа. Нужны соответствующие права в текущем объекте.')
    if 422 in codes:lines.append('Параметры чтения не прошли проверку. По неуспешному запросу нельзя судить о содержимом реестра.')
    if 404 in codes:lines.append('Запрошенная карточка или ресурс не найдены. Это не означает, что весь реестр пуст.')
    if any(isinstance(code,int) and code>=500 for code in codes):lines.append('Сервис данных недоступен или вернул ошибку. Данные не заменены пустым списком.')
    return '\n\n'.join(lines)

def equipment_code(question):
    if not re.search(r'оборудован|насос|прибор|агрегат|устройств',question,re.I):return None
    if not re.search(r'найди|найти|покажи|открой|есть ли|существует ли|имеется ли|когда|какие|сколько',question,re.I):return None
    quoted=re.search(r'\bкод(?:ом|у|а)?\s*[:—-]?\s*[«"\']([^»"\'\n]{1,128})[»"\']',question,re.I)
    if quoted:return quoted[1]
    explicit=re.search(r'\bкод(?:ом|у|а)?\s*[:—-]?\s*([\w][\w./-]{1,127})',question,re.I)
    if explicit:return explicit[1].rstrip('.')
    # Bare inventory labels such as ITP-01. A UUID is not guessed or fabricated.
    bare=re.search(r'\b[\w]+[-/][\w./-]+\b',question)
    return bare[0] if bare and len(bare[0])<=128 and not re.fullmatch(r'\d{4}-\d{2}-\d{2}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',bare[0]) else None

def regulation_lookup(question):
    from .intents import mutation_requested
    return bool(re.search(r'регламент|операци.{0,50}\bТО\b|\bТО\b.{0,50}операци',question,re.I)
        and not mutation_requested(question))

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
