"""Deterministic user-facing task analysis. All totals come from the authorized API."""
import re
from fastapi import HTTPException
from .read_transport import read
from .inventory_report import label


def requested(question):
    return bool(re.search(r'анализ|разбер|проверь|покажи',question,re.I)
        and re.search(r'задани|наряд',question,re.I)
        and re.search(r'незаверш|просроч|дубликат|нагрузк|трудо[её]мк|все|всех',question,re.I)
        and not re.search(r'excel|xlsx|прикрепл[её]н|назначь|создай|отмени',question,re.I))


async def report(app,tool,headers,trace,check,question,principal):
    named=re.search(r'(?:ЖК|объект[ауе]?|здани[еяи])\s*[«"]([^»"]+)',question,re.I)
    if named and named[1].casefold() not in principal.site_name.casefold():
        return f'Сейчас выбран объект «{label(principal.site_name)}». Переключитесь на запрошенный объект: анализ не будет подменён данными другого здания.'
    calls=0;snapshot=None
    async def fetch(section,offset=0):
        nonlocal calls,snapshot
        check();calls+=1
        if calls>200:raise HTTPException(413,'Предел подробного отчёта')
        _,data=await read(app,tool,dict(query=dict(section=section,offset=offset)),headers,trace)
        if not data.get('complete'):raise HTTPException(409,'Неполный снимок')
        if snapshot and data['snapshot_id']!=snapshot:raise HTTPException(409,'Данные изменились во время анализа')
        snapshot=data['snapshot_id'];return data
    async def all_rows(section):
        result=[];offset=0
        while True:
            data=await fetch(section,offset);result.extend(data['items']);offset+=len(data['items'])
            if offset>=data['total']:return result
            if not data['items']:raise HTTPException(409,'Неполная страница')
    try:
        data=await fetch('summary')
        equipment=await all_rows('equipment');dates=await all_rows('dates')
        groups=await all_rows('duplicates') if data['business_duplicates']['candidate_groups'] else []
    except HTTPException as exc:
        if exc.status_code in (401,403):reason='Доступ к данным ограничен вашей ролью или контекст доступа изменился.'
        elif exc.status_code==409:reason='Данные изменились во время чтения либо снимок неполный.'
        elif exc.status_code==413:reason='Объём данных превышает безопасный предел полного отчёта.'
        else:reason='Не удалось прочитать данные из backend.'
        return 'Полный анализ не выполнен. '+reason+' Частичный результат не выдан за полный; это не означает отсутствия заданий.'
    return render(data,equipment,dates,groups)


def render(data,equipment,dates,groups):
    c=data['counters'];due=data['due'];scheduled=data['scheduled'];norm=data['norm_checks'];scope=data['scope']
    lines=[f"## Задания: {label(scope['site_name'])}",
        f"Проверено на **{data['local_date']}**, часовой пояс **{label(data['timezone'])}**. Источник — полный снимок доступных заданий PostgreSQL; Excel не требуется.",
        f"Всего записей — **{c['all_tasks']}**. Завершено — **{c['completed']}**, отменено — **{c['cancelled']}**. "
        f"Незавершённых — **{c['unfinished']}**, из них ожидают приёмки — **{c['by_status'].get('in_review',0)}**, выполняются — **{c['by_status'].get('in_progress',0)}**.",
        f"Прежний счётчик «незавершённые плановые задания» учитывал только черновики, назначенные, уточнение и доработку: **{c['execution_pending']}**. "
        f"Он исключал работу в процессе и на приёмке. Незавершённых с календарным происхождением — **{c['scheduled_unfinished']}**; анализ ниже охватывает **{data['selected_tasks']}** незавершённых заданий всех источников."]
    if scope['visibility']=='assigned_to_user':lines.append('Ваша роль позволяет анализировать только назначенные вам задания. Это не сводка всего здания.')
    lines.extend(['### Сроки',
        f"По нормативному сроку: просрочено — **{due.get('overdue',0)}**, срок сегодня — **{due.get('today',0)}**, будущий срок — **{due.get('future',0)}**, без срока — **{due.get('undated',0)}**.",
        f"По назначенному началу: сегодня — **{scheduled.get('today',0)}**, в будущем — **{scheduled.get('future',0)}**, в прошлом — **{scheduled.get('past',0)}**, время не назначено — **{scheduled.get('unscheduled',0)}**.",
        'Просрочка определяется истечением нормативного срока, включая задания на приёмке. Прошедшее время начала само по себе не означает нарушения нормативного срока.'])
    pending_due=data['execution_pending_due']
    lines.append(f"В прежней группе из {c['execution_pending']} заданий: просрочено **{pending_due.get('overdue',0)}**, срок сегодня **{pending_due.get('today',0)}**, будущий срок **{pending_due.get('future',0)}**, без срока **{pending_due.get('undated',0)}**.")
    if due.get('within_window'):lines.append(f"У {due['within_window']} заданий нормативный день и точный срок требуют проверки: день в прошлом, но срок ещё не истёк.")
    lines.extend(['### Нагрузка по оборудованию','| Оборудование | Незавершено | Ожидает исполнения¹ | На приёмке | Известные чел·ч |','|---|---:|---:|---:|---:|'])
    for item in equipment:
        lines.append(f"| {label(item['asset_code'])} — {label(item['name'])} | {item['tasks']} | {item['execution_pending']} | {item['in_review']} | {item['known_person_hours']} |")
    lines.append('¹ Черновики, назначенные, уточнение и доработка. Задания, связанные с несколькими единицами, учитываются в каждой строке; складывать строки оборудования нельзя.')
    for item in equipment:
        lines.append(f"**{label(item['asset_code'])}: фактические регламенты и горизонт**")
        for op in item['operations']:
            pattern=op['calendar_pattern'] or {};frequency=pattern.get('frequency') or op['period_unit'] or 'не подтверждена'
            frequency={'day':'день','week':'неделя','month':'месяц','quarter':'квартал','year':'год','dates':'конкретные даты','yearly_count':'число раз в год'}.get(frequency,frequency)
            interval=pattern.get('interval') or op['period_count'] or 'неизвестен'
            periods=', '.join(op['plan_periods']) or 'нет привязки к месячному плану'
            lines.append(f"- {label(op['title'])}: **{op['tasks']}** незавершённых, из них прежний счётчик — **{op['execution_pending']}**; "
                f"частота: {label(frequency)}, интервал {interval}, повторов за период {op['occurrences_per_period'] or 'не подтверждено'}; "
                f"исходные/нормативные даты {op['first_source_date'] or 'не указаны'} — {op['last_source_date'] or 'не указаны'}; месяцы планов: {periods}.")
        if item['operations_truncated']:lines.append(f"Показаны 25 из {item['operations_total']} конфигураций; итог по оборудованию рассчитан по всем заданиям.")
    lines.extend(['Число заданий выше числа операций, поскольку одна операция повторяется по датам. Здесь приведены сохранённые частоты и периоды; полноту генерации и соответствие каждой даты календарю этот отчёт не удостоверяет.',
        '### Нагрузка по датам','| Дата | Заданий | С назначенным началом | Только нормативный день | Известные чел·ч |','|---|---:|---:|---:|---:|'])
    for item in dates:lines.append(f"| {item['date']} | {item['tasks']} | {item['planned_tasks']} | {item['deadline_only_tasks']} | {item['known_person_hours']} |")
    duplicates=data['business_duplicates']
    lines.extend(['### Дубликаты и нормы',
        f"Кандидатов на бизнес-дубликаты: **{duplicates['candidate_groups']}** групп, **{duplicates['candidate_tasks']}** заданий. "
        f"Нельзя проверить ключ у **{duplicates['unchecked_tasks']}** заданий: не хватает оборудования, операции или даты.",
        'Проверяются оборудование, операция, исходная дата обязательства и номер повтора. Разные обязательства выходных, перенесённые на понедельник, не считаются дублями только по совпадению дня. Кандидаты требуют проверки, удаление не выполнялось.'])
    for group in groups:lines.append(f"- {label(group['operation_title'])}, исходная/нормативная дата {group['source_or_due_date']}, повтор {group['sequence']}: {group['count']} заданий.")
    lines.extend([f"Нормы: арифметически согласованы с длительностью и составом — **{norm.get('consistent',0)}**, расхождения — **{norm.get('mismatch',0)}**, "
        f"прочие проблемы — **{sum(v for k,v in norm.items() if k not in ('consistent','mismatch'))}**.",
        f"Известная трудоёмкость — **{data['known_person_hours']} чел·ч**; не определена у **{data['unknown_effort_tasks']}** заданий. Это плановая, а не фактическая длительность.",
        'Человеко-часы сопоставляются с минутами × числом исполнителей / 60. Для нормы в часах длительности сначала учитывается состав бригады. Совпадение арифметики не доказывает достоверность методики или выполнимость смены.'])
    labels=dict(missing_norm='не задана положительная норма',invalid_norm='норма записана некорректно',unknown_unit='не подтверждена единица нормы',missing_duration='не задана длительность',basis_unit_conflict='единица нормы противоречит способу учёта трудозатрат')
    for key,description in labels.items():
        if norm.get(key):lines.append(f"Требуют уточнения: {description} — **{norm[key]}** заданий.")
    if not data['selected_tasks']:lines.append('Незавершённых заданий в разрешённой области нет. Это не означает отсутствия объектов или регламентов.')
    return '\n'.join(line if i and ((line.startswith('|') and lines[i-1].startswith('|')) or (line.startswith('- ') and lines[i-1].startswith('- '))) else '\n'+line for i,line in enumerate(lines)).strip()
