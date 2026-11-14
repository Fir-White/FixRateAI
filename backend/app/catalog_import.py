"""Inspect the customer's HVAC layout as unconfirmed source data, never assignments."""
from collections import Counter
from hashlib import sha256
import re

from app.catalog_excel import column, read_workbook

PARSER_VERSION = 'hvac-catalog-v1'
SOURCE_KIND = 'hvac_january_catalog'
FLAGS = ['NEEDS_SEMANTICS', 'NEEDS_DURATION', 'NEEDS_ASSET_BINDING', 'NEEDS_POLICY']
KINDS = {'ТО1', 'ТО2', 'ТО2*', 'ТО3', 'ТОр'}


def raw_cell(cells, col, row):
    cell = cells.get(col)
    return dict(address=f'{col}{row}', present=cell is not None,
        text=cell.get('text', cell['value']) if cell else None,
        raw_value=cell.get('raw_value') if cell else None,
        cell_type=cell.get('cell_type') if cell else None,
        style=cell.get('style') if cell else None,
        formula=cell.get('formula_text') if cell else None)


def frequency_hint(raw):
    value = re.sub(r'\s+', ' ', raw).strip().lower()
    known = {'1/квар': ('quarter', 1), '2/год': ('yearly_count', 2), '1/год': ('year', 1),
        '1/мес': ('month', 1), '1/день': ('day', 1), '1/нед': ('week', 1),
        '1/4года': ('year', 4), '1/5 лет': ('year', 5), '2/сутки': ('daily_events', 2),
        'по необходимости': ('event', None), 'в составе то2, то3': ('included_in', None)}
    kind, interval = known.get(value, ('unknown', None))
    return dict(kind=kind, interval=interval, confirmed=False)


def inspect_catalog(content):
    sheets = read_workbook(content, provenance=True)
    if 'Лист1' not in sheets:
        raise ValueError('Нужен каталог СВиК: лист «Лист1» с колонками A:G и январём H:AL')
    rows = dict(sheets['Лист1'])
    header = rows.get(2, {})
    def text(cells, col): return cells.get(col, {}).get('value', '')
    if not ('операц' in text(header, 'B').lower() and 'период' in text(header, 'D').lower()
            and 'время' in text(header, 'E').lower() and 'январ' in text(header, 'H').lower()):
        raise ValueError('Структура листа не соответствует каталогу СВиК. Используйте исходный формат A:G, H:AL')
    days = rows.get(3, {})
    if any(text(days, column(day+7)) != str(day) for day in range(1,32)):
        raise ValueError('В H3:AL3 ожидаются дни января 1–31; месяц и даты нельзя угадывать')
    groups, operations, issues, group_by_code = [], [], [], {}
    context_headers = [dict(sheet='Лист1',**raw_cell(rows.get(3,{}),'B',3))]
    active_group = None
    seen_codes = set()
    # A source section can contain repeated titles and nested numbered groups.
    for row, cells in sorted(rows.items()):
        if row <= 3: continue
        code, title, kind, frequency = [text(cells, col) for col in ('A','B','C','D')]
        if not any((code,title,kind,frequency)): continue
        if not kind and not code and title:
            if len(context_headers) >= 250: raise ValueError('Слишком много заголовков каталога')
            context_headers.append(dict(sheet='Лист1',**raw_cell(cells,'B',row)))
            continue
        if not kind and code and title and not frequency:
            if len(groups) >= 250: raise ValueError('Слишком много разделов каталога')
            parent_code = code.rsplit('.',1)[0] if '.' in code else None
            parent = group_by_code.get(parent_code)
            identity = f'Лист1:{row}'
            group = dict(id=identity, code=code, title=title, row=row,
                parent_id=parent['id'] if parent else None, source_cells=[f'A{row}',f'B{row}'])
            groups.append(group); group_by_code[code] = group; active_group = group
            continue
        if not title and not kind: continue
        if len(operations) >= 1000: raise ValueError('В каталоге допускается не более 1000 операций')
        flags = list(FLAGS)
        if not active_group: issues.append(dict(code='GROUP_UNKNOWN',sheet='Лист1',cell=f'B{row}',message='Операция без подтверждённого раздела'))
        key = (active_group['id'] if active_group else None, code)
        if not code or key in seen_codes:
            issues.append(dict(code='OPERATION_CODE_AMBIGUOUS',sheet='Лист1',cell=f'A{row}',message='Пустой или повторяющийся код внутри раздела'))
        seen_codes.add(key)
        if kind not in KINDS: issues.append(dict(code='MAINTENANCE_TYPE_UNKNOWN',sheet='Лист1',cell=f'C{row}',message='Неизвестный вид ТО; исходное значение сохранено'))
        hint = frequency_hint(frequency)
        if hint['kind'] == 'unknown': issues.append(dict(code='FREQUENCY_UNKNOWN',sheet='Лист1',cell=f'D{row}',message='Периодичность требует разбора'))
        marks = [dict(day=day, **raw_cell(cells,column(day+7),row)) for day in range(1,32)]
        nonempty = sum(bool((m['text'] or '').strip()) for m in marks)
        raw = {col:raw_cell(cells,col,row) for col in ('A','B','C','D','E','F','G')}
        operations.append(dict(row=row, code=code, title=title, maintenance_type=kind,
            frequency_raw=raw['D']['text'] or '', frequency_hint=hint,
            group_id=active_group['id'] if active_group else None,
            quality_flags=flags, interpretation='UNKNOWN', ready_for_real_plan=False,
            norm_value=None, norm_unit=None, quantity=None, equipment_ids=[],
            calendar_month=1, calendar_year=None, mark_count=nonempty,
            source_cells={col:cell['address'] for col,cell in raw.items()},
            raw_cells=raw, calendar_marks=marks))
    if not operations: raise ValueError('В каталоге не найдены операции')
    second = dict(sheets.get('Лист2', []))
    diagnostic = []
    for row,col in ((6,'I'),(20,'I')):
        if row in second: diagnostic.append(raw_cell(second[row],col,row))
    i6 = text(second.get(6,{}),'I')
    if i6 and not re.fullmatch(r'[+-]?[0-9]+(?:[.,][0-9]+)?',i6):
        issues.append(dict(code='NON_NUMERIC_LABOR',sheet='Лист2',cell='I6',message='Текст вместо нормы часов. Итог I20 требует сверки; исходник не исправлен'))
    summary = dict(operation_count=len(operations), group_count=len(groups),
        top_level_group_count=sum(g['parent_id'] is None for g in groups),
        maintenance_types=dict(Counter(o['maintenance_type'] for o in operations)),
        frequency_counts=dict(Counter(o['frequency_raw'] for o in operations)),
        empty_duration_count=sum(not (o['raw_cells']['E']['text'] or '').strip() for o in operations),
        mark_count=sum(o['mark_count'] for o in operations),
        readiness_counts={flag:len(operations) for flag in FLAGS}, ready_count=0,
        issue_count=len(issues), ready_for_real_plan=False)
    return dict(parser_version=PARSER_VERSION, source_kind=SOURCE_KIND,
        source_sha256=sha256(content).hexdigest(), summary=summary,
        groups=groups, operations=operations, issues=issues, sheet2_diagnostic=diagnostic,
        header_context=[dict(sheet='Лист1',**raw_cell(rows.get(row,{}),col,row))
                        for row,col in ((1,'A'),(2,'H'))]+context_headers)
