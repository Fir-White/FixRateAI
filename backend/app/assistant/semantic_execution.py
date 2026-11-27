"""Execute and project server-compiled objectives through the existing tool pipeline."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlencode

from pydantic import ValidationError

from app.schemas.assistant import AgentStep, MAX_COLLECTION_PAGE
from app.schemas.maintenance import CalendarPattern
from app.scheduling.recurrence import pattern_description

from .inventory_report import label
from .semantic_plan import EQUIPMENT_ANALYSIS, UUID, positive_text


TASK_STATES = {'draft': 'черновик', 'assigned': 'назначено', 'in_progress': 'в работе',
               'rework': 'на доработке', 'rework_required': 'на доработке', 'in_review': 'на проверке',
               'submitted': 'на проверке', 'completed': 'завершено', 'accepted': 'принято',
               'cancelled': 'отменено', 'active': 'в эксплуатации', 'under_repair': 'в ремонте',
               'retired': 'выведено из эксплуатации'}
ROLES = {'chief_engineer': 'главный инженер', 'executor': 'исполнитель', 'engineer': 'инженер',
         'director': 'директор', 'dispatcher': 'диспетчер', 'admin': 'администратор'}
LABELS = {'id': 'ID', 'name': 'Название', 'location': 'Место установки', 'role': 'Роль', 'site': 'Здание',
          'email': 'Email', 'code': 'Код', 'state': 'Состояние', 'start': 'Плановое начало',
          'deadline': 'Нормативный срок', 'crew_size': 'Требуется исполнителей',
          'assignees': 'Назначенные исполнители', 'checklist': 'Чек-лист', 'revision': 'Ревизия',
          'closed': 'Фактическое закрытие', 'system_id': 'ID системы', 'site_id': 'ID объекта',
          'equipment_type_id': 'ID типа оборудования', 'parent_id': 'ID родительского оборудования',
          'serial_number': 'Серийный номер', 'commissioned_on': 'Дата ввода в эксплуатацию'}


def _call(goal, tool, args):
    return AgentStep(answer='', calls=[dict(tool=tool, goal_id=goal['id'],
        arguments_json=json.dumps(args, ensure_ascii=False), explanation=goal['title'])])


def _stop(message):
    return AgentStep(answer=message, calls=[])


def _read(proofs, tool):
    return next((proof['result'] for proof in reversed(proofs) if proof['tool'] == tool), None)


REFERENCE_SOURCES = {'task_read': 'task_id', 'equipment_read': 'equipment_id'}


@dataclass(frozen=True)
class EquipmentResolution:
    status: Literal['exact', 'ambiguous', 'empty', 'partial']
    candidates: tuple[dict, ...] = ()


def resolve_equipment(proof, subject, *, exact_name=False):
    from .semantic_plan import ASSET, normalize_reference

    value = proof.get('result')
    if not isinstance(value, dict) or not isinstance(value.get('items'), list):
        return EquipmentResolution('partial')
    rows = value['items']
    if (not proof.get('complete') or type(value.get('total')) is not int or value['total'] != len(rows) or
            any(not isinstance(row, dict) or not re.fullmatch(UUID, str(row.get('equipment_id', '')), re.I) for row in rows) or
            len({row['equipment_id'] for row in rows}) != len(rows)):
        return EquipmentResolution('partial')
    subject = normalize_reference(subject).casefold()
    if exact_name:
        candidates = tuple(row for row in rows if subject == str(row.get('name') or '').casefold())
    else:
        exact = tuple(row for row in rows if subject in (str(row.get('asset_code') or '').casefold(),
                                                        str(row.get('name') or '').casefold()))
        candidates = exact or (() if re.fullmatch(ASSET, subject, re.I) else tuple(rows))
    status = 'ambiguous' if len(candidates) > 1 else 'exact' if candidates else 'empty'
    return EquipmentResolution(status, candidates)


def equipment_resolution_text(resolution, subject):
    if resolution.status == 'ambiguous':
        rows = (f'- {label(row.get("asset_code") or "Без кода")} · {label(row.get("name") or "Без названия")} · ID {row["equipment_id"]}'
                for row in resolution.candidates)
        return 'Уточните инвентарный код или ID: найдено несколько единиц оборудования.\n' + '\n'.join(rows)
    if resolution.status == 'partial':
        return 'Полный результат поиска оборудования не подтверждён. Повторите чтение.'
    if resolution.status == 'empty':
        return f'Оборудование {label(subject)} не найдено в доступном актуальном реестре.'
    return f'Оборудование {label(subject)} найдено.'


def _reference(goal, meta, proofs):
    misses = goal.get('reference_misses', [])
    for tool, key in REFERENCE_SOURCES.items():
        if tool not in misses and _read(proofs, tool) is None:
            return _call(goal, tool, {'path': {key: meta['subject']}})
    return _stop('')


def _equipment(goal, meta, proofs):
    from .semantic_plan import ASSET

    target = goal['tool']
    subject = meta['subject']
    if re.fullmatch(UUID, subject, re.I):
        identity = subject
    else:
        lookup = next((proof for proof in reversed(proofs) if proof['tool'] == 'equipment_find'), None)
        if lookup is None:
            query = {'asset_code': subject} if not meta.get('exact_name') and re.fullmatch(ASSET, subject, re.I) else {'q': subject}
            return _call(goal, 'equipment_find', {'query': query})
        resolution = resolve_equipment(lookup, subject, exact_name=bool(meta.get('exact_name')))
        goal['resolution'] = dict(status=resolution.status,
                                  evidence_id=lookup['id'])
        if resolution.status != 'exact' or target == 'equipment_find':
            return _stop(equipment_resolution_text(resolution, subject))
        identity = resolution.candidates[0]['equipment_id']
    arguments = {'path': {'equipment_id': identity}}
    if target == 'equipment_edit':
        arguments['body'] = dict(meta['changes'])
        if 'expected_revision' in meta:
            arguments['body']['expected_revision'] = meta['expected_revision']
    if target == 'equipment_service_history':
        arguments['query'] = {**meta['query'], 'only_accepted': True}
        if meta.get('full'):
            arguments['query']['limit'] = min(meta.get('limit', MAX_COLLECTION_PAGE), MAX_COLLECTION_PAGE)
    elif target == 'calendar_evidence':
        arguments['query'] = {**meta['query'], 'approved_only': True}
    elif target == 'tasks_find':
        arguments = {'query': {**meta['query'], 'equipment_id': identity, 'unfinished_only': True,
                               'period': meta['period']}}
        arguments['query']['limit'] = (1 if meta.get('summary_only') else
                                      min(meta.get('limit', MAX_COLLECTION_PAGE), MAX_COLLECTION_PAGE))
    return _call(goal, target, arguments)


def _assign(goal, meta, proofs):
    candidate = meta['subject']
    if candidate is None:
        found = _read(proofs, 'tasks_find')
        if found is None:
            return _call(goal, 'tasks_find', {'query': {'period': 'upcoming'}})
        rows = found.get('items', [])
        if not rows:
            return _stop('Предстоящих заданий для назначения нет.')
        first = rows[0]
        if len(rows) > 1 and (not first.get('scheduledStart') or first['scheduledStart'] == rows[1].get('scheduledStart')):
            ids = ', '.join(row['id'] for row in rows[:3] if row.get('id'))
            return _stop('У нескольких ближайших работ одинаковое время. Уточните задание по названию или ID. ' + ids)
        candidate = first.get('id')
        if not candidate:
            return _stop('У ближайшей работы не подтверждён ID. Уточните задание.')
    if meta['one_worker']:
        card = _read(proofs, 'task_read')
        if card is None:
            return _call(goal, 'task_read', {'path': {'task_id': candidate}})
        required = (card.get('task') or {}).get('crewSize')
        if type(required) is not int:
            return _stop('Требуемый состав задания не подтверждён.')
        if required != 1:
            return _stop(f'Для этого задания требуется исполнителей: {required}. Одного назначить нельзя.')
    preparation = _read(proofs, 'assignment_prepare')
    if preparation is None:
        return _call(goal, 'assignment_prepare', {'path': {'task_id': candidate}, 'body': {'one_person_only': meta['one_worker']}})
    command = preparation.get('command')
    if not isinstance(command, dict):
        return _stop(str(preparation.get('explanation') or 'Назначение сейчас невозможно. Проверьте состав и время.'))
    if meta['one_worker'] and len(command.get('executor_ids') or []) != 1:
        return _stop('Для этого задания требуется другой состав. Одного исполнителя назначить нельзя.')
    if 'expected_revision' in meta and meta['expected_revision'] != command.get('expected_revision'):
        return _stop('Указанная ревизия не совпадает с текущей. Обновите карточку задания.')
    body = {key: command[key] for key in ('expected_revision', 'start_at', 'end_at', 'executor_ids', 'crew_id') if command.get(key) is not None}
    body['reason'] = 'По запросу пользователя подготовлено назначение на выбранное задание.'
    return _call(goal, 'task_assign', {'path': {'task_id': candidate}, 'body': body})


def next_step(goal, state, *, turn_evidence_start=None):
    meta = goal['semantic']
    target = goal['tool']
    proofs = [proof for proof in state['evidence'] if proof['goal_id'] == goal['id'] and
              proof.get('retained') and proof.get('status') != 'STALE']
    if meta['intent'] == 'reference_details':
        return _reference(goal, meta, proofs)
    if meta['intent'] in EQUIPMENT_ANALYSIS or target in (
            'equipment_read', 'equipment_find', 'equipment_edit', 'regulations_read', 'equipment_service_history'):
        if goal['mode'] == 'read' and target != 'equipment_find' and meta['subject'] and turn_evidence_start is not None:
            from .semantic_plan import ASSET
            query_key = 'asset_code' if re.fullmatch(ASSET, meta['subject'], re.I) else 'q'
            shared = next((proof for proof in reversed(state['evidence'][turn_evidence_start:])
                           if proof['tool'] == 'equipment_find' and proof.get('complete') and proof.get('retained')
                           and proof.get('scope') == state['scope'] and
                           proof['arguments'].get('query', {}).get(query_key) == meta['subject']), None)
            if shared is not None:
                goal['identity_evidence_id'] = shared['id']
                proofs.append(shared)
        return _equipment(goal, meta, proofs)
    if target == 'task_assign':
        return _assign(goal, meta, proofs)
    if target == 'task_read':
        return _call(goal, target, {'path': {'task_id': meta['subject']}})
    if target in ('task_start', 'task_cancel'):
        body = dict(meta.get('changes', {}))
        if 'expected_revision' in meta:
            body['expected_revision'] = meta['expected_revision']
        return _call(goal, target, {'path': {'task_id': meta['subject']}, 'body': body})
    if target == 'tasks_find':
        query = {**meta.get('query', {}), 'period': meta.get('list_period') or meta['period']}
        if meta.get('scheduled_only'):
            query['scheduled_only'] = True
        if meta.get('list_period') or meta.get('summary_only'):
            query['limit'] = 1
        elif meta['intent'] == 'task_list':
            query['limit'] = min(meta.get('limit', MAX_COLLECTION_PAGE), MAX_COLLECTION_PAGE)
        return _call(goal, target, {'query': query})
    if target == 'tasks_analyze':
        return _call(goal, target, {'query': {'section': 'summary', **meta.get('query', {})}})
    if target == 'staff_find':
        subject = meta['subject'].strip()
        # A surname prefix finds endings used by the saved spelling and natural inflection.
        words = re.findall(r'[\w@.+-]+', subject)
        search = words[-1][:max(4, len(words[-1])-2)] if len(words) > 1 else subject
        return _call(goal, target, {'query': {'q': search}})
    if target == 'staff_read':
        return _call(goal, target, {'path': {'user_id': meta['subject']}})
    if target == 'attachment_read':
        query = {'coordinates_mode': meta['workbook_mode']}
        for name in ('sheet', 'row'):
            if meta.get(name) is not None:
                query[name] = meta[name]
        return _call(goal, target, {'path': {'identity': state['scope']['conversation_id'],
            'attachment_id': meta['attachment_id']}, 'query': query})
    return _call(goal, target, {})


def _discussion_proofs(goal, state):
    goals = {item['id']: item for item in state['goals']}
    subject = goal['semantic'].get('subject')
    for proof in state['evidence']:
        owner = goals[proof['goal_id']]
        if (proof.get('complete') and proof.get('retained') and proof.get('scope') == state.get('scope') and
                proof.get('status') in ('FOUND', 'EMPTY') and proof['tool'] == owner['tool'] and
                (subject is None or str(owner.get('semantic', {}).get('subject')).casefold() == subject.casefold())):
            yield proof, owner


def explain_results(goal, state):
    for proof, _ in _discussion_proofs(goal, state):
        if proof['tool'] == 'task_read':
            task = proof['result'].get('task', {})
            if task.get('isOverdue') is True:
                return ('Карточка подтверждает просрочку. Для выяснения причины нужны факты о ходе работ. '
                        f'Источник {proof["id"]}.')
            if task.get('isOverdue') is False:
                return f'На момент чтения карточка не отмечена как просроченная. Источник {proof["id"]}.'
    return 'Проверенные чтения приведены выше. Дополнительный вывод по ним подтвердить не удалось.'


def recommendations(goal, state):
    """Rank review steps using only validated evidence from this request."""
    options = []
    for proof, owner in _discussion_proofs(goal, state):
        tool, result = proof['tool'], proof['result']
        source = f' · источник {proof["id"]}'
        if tool == 'task_read' and result.get('task', {}).get('isOverdue') is True:
            options.extend((
                (10, 'Найти ближайшее доступное окно с текущим исполнителем и уточнить причину просрочки.' + source),
                (15, 'Проверить, может ли допущенная бригада выполнить работу раньше.' + source),
            ))
        elif tool == 'tasks_find' and owner.get('semantic', {}).get('intent') == 'equipment_tasks':
            if result['period'] == 'overdue' and result['items']:
                options.append((10, 'Проверить причины просроченных работ и согласовать ближайшее доступное окно.' + source))
            if result['period'] == 'all' and result['items']:
                options.append((20, 'Сверить сроки и ответственных по незавершённым работам.' + source))
        elif tool == 'equipment_service_history':
            if proof['status'] == 'EMPTY':
                options.append((25, 'Сверить журнал обслуживания и акты приёмки, чтобы восстановить историю.' + source))
            else:
                options.append((40, 'Сверить объём работ в последнем принятом отчёте с текущим регламентом.' + source))
        elif tool == 'regulations_read':
            options.append((35, 'Сверить актуальность сохранённого регламента с утверждённой документацией.' + source))
        elif tool == 'equipment_read':
            options.append((60, 'При ближайшем допущенном обходе сверить запись о состоянии с фактическими наблюдениями.' + source))
    options.extend((
        (70, 'Уточнить, какие сведения об оборудовании ещё нужны для решения о работах.'),
        (80, 'Согласовать с ответственными критерии приоритета и ограничения доступа.'),
        (90, 'Выбрать контрольную точку для повторной проверки состояния и документов.'),
    ))
    selected = list(dict.fromkeys(message for _, message in sorted(options)))[:goal['semantic']['recommendation_count']]
    return '\n'.join(f'{i}. {message}' for i, message in enumerate(selected, 1))


def _instant(value):
    if not value:
        return None
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return value
    return instant.strftime('%d.%m.%Y %H:%M')


def _row(item, fields, identity_key='id'):
    checklist = item.get('checklist') or []
    def identity(key):
        value = item.get(key)
        return value if isinstance(value, str) and re.fullmatch(UUID, value, re.I) else None

    values = {
        'id': identity(identity_key), 'system_id': identity('system_id'),
        'site_id': identity('site_id') or identity('siteId'),
        'equipment_type_id': identity('equipment_type_id'), 'parent_id': identity('parent_equipment_id'),
        'serial_number': item.get('serial_number') if isinstance(item.get('serial_number'), str) else None,
        'commissioned_on': item.get('commissioned_on') if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(item.get('commissioned_on'))) else None,
        'name': item.get('name') or item.get('title') or item.get('full_name'),
        'code': item.get('asset_code'), 'location': item.get('location'),
        'role': ROLES.get(item.get('role'), item.get('role')), 'site': item.get('siteName'),
        'email': item.get('email'), 'state': TASK_STATES.get(item.get('state') or item.get('status'), item.get('state') or item.get('status')),
        'start': _instant(item.get('scheduledStart')), 'deadline': item.get('mandatoryDueDate'),
        'crew_size': item.get('crewSize'), 'assignees': ', '.join(str(row.get('name', '')) for row in item.get('assignees', [])),
        'revision': item.get('revision'),
        'closed': _instant(item.get('closedAt')) if item.get('state') == 'completed' else
                  'работа не закрыта' if item.get('state') != 'cancelled' else 'работа отменена',
    }
    main = ' · '.join(f'{LABELS[field]}: {label(str(values[field]))}' if values.get(field) not in (None, '')
                      else f'{LABELS[field]}: не указано' for field in fields if field != 'checklist')
    if 'checklist' not in fields:
        return main
    points = '\n'.join('- ' + label(row['text']) for row in checklist if row.get('text'))
    return '\n\n'.join(filter(None, (main, points or 'Согласованный чек-лист не найден.')))


def _staff(value, meta):
    subject = meta['subject'].casefold().replace('ё', 'е')
    def same_name(saved):
        expected = re.findall(r'[\w-]+', subject)
        actual = re.findall(r'[\w-]+', saved.casefold().replace('ё', 'е'))
        if not expected or len(expected) != len(actual):
            return False
        endings = ('а', 'у', 'ом', 'е', 'я', 'ю', 'ем', 'ы', 'и', 'ой', 'ей', 'ого', 'ому')
        return all(query == name or len(name) >= 4 and (query in {name + ending for ending in endings} or
                   name[-1] in 'аяьй' and query in {name[:-1]+ending for ending in endings})
                   for query, name in zip(expected, actual))
    rows = [row for row in value.get('items', []) if subject == str(row.get('email', '')).casefold() or
            same_name(str(row.get('full_name', '')))]
    if len(rows) == 1 and (value.get('total', 0) <= len(value.get('items', []))):
        return _row(rows[0], meta['fields'], 'user_id')
    return 'Сотрудник с указанными данными не найден.' if not rows else 'Уточните сотрудника по точному рабочему email.'


def _workbook(value, meta, request):
    mode = meta['workbook_mode']
    if mode == 'sheets':
        return '\n'.join('- ' + label(sheet['name']) for sheet in value['sheets']) or 'В книге нет листов.'
    if mode == 'structure':
        sheet = value['sheet']
        return f'{label(sheet["name"])}: строк {sheet["rows"]}, первая {sheet["first_row"]}, последняя {sheet["last_row"]}.'
    headers = value['headers']
    if mode == 'headers':
        return '\n'.join(f'{column}: {label(str(text))}' for column, text in headers.items()) or 'Строка заголовков пуста.'
    row = value['cells']
    output = []
    selected = meta['columns']
    if not selected and meta['whole_row']:
        selected = list(row)
    elif not selected:
        selected = [text.split(',')[0].strip() for text in headers.values() if isinstance(text, str) and
                    text.strip() and _header_mentioned(text.split(',')[0].strip(), positive_text(request))]
    for requested in dict.fromkeys(selected):
        wanted = ' '.join(re.findall(r'\w+', requested.casefold()))
        columns = [column for column, text in headers.items() if isinstance(text, str) and
                   (_header_mentioned(text.split(',')[0].strip(), requested)
                    or re.search(r'\b' + re.escape(wanted) + r'\b', text.casefold()))]
        if not columns and re.fullmatch(r'[A-Za-z]{1,3}', requested):
            columns = [requested.upper()]
        if len(columns) != 1:
            output.append(f'{label(requested)}: столбец не удалось определить однозначно.')
            continue
        column = columns[0]
        cell = _cell(row, column)
        if isinstance(cell, dict):
            cell = cell.get('value')
        output.append(f'{label(str(headers.get(column, requested)))}: {label(str(cell)) if cell not in (None, "") else "пусто"}.')
    return '\n'.join(output) or 'Уточните названия или буквы нужных столбцов.'


def _header_mentioned(header, text):
    words = re.findall(r'\w+', header.casefold())
    if not words:
        return False
    patterns = []
    for word in words:
        if len(word) >= 5 and word[-1] in 'аяь':
            patterns.append(re.escape(word[:-1]) + r'(?:а|у|е|ы|ой|я|ю|и|ей|ь)')
        else:
            patterns.append(re.escape(word))
    return bool(re.search(r'\b' + r'\s+'.join(patterns) + r'\b', text.casefold()))


def _cell(row, column):
    def column_number(letters):
        result = 0
        for letter in letters:
            result = result * 26 + ord(letter) - ord('A') + 1
        return result
    if column in row:
        return row[column]
    for address, value in row.items():
        if ':' in address:
            start, end = address.split(':', 1)
            if column_number(start) <= column_number(column) <= column_number(end):
                return value
    return None


def collection_lines(lines, *, total=None, complete=True, limit=None, location=None, delivery=None):
    """Apply the requested selection and a character budget independently of source paging."""
    total = total if type(total) is int else (len(lines) if complete else None)
    selected = lines[:limit]
    delivered = []
    characters = 0
    for line in selected:
        characters += len(line) + 1
        if characters > 32_000:
            break
        delivered.append(line)
    if len(delivered) != len(selected):
        complete = False
    if delivery is not None:
        delivery.update(rows=len(delivered), total=total, complete=complete)
    count = str(total) if total is not None else 'не подтверждено'
    if not complete:
        delivered.append(f'Показано записей: {len(delivered)}. Всего по источнику: {count}. Полный результат не подтверждён.'
                         + (f' Откройте {location}, чтобы просмотреть выборку в реестре.' if location else ''))
    elif total is not None and (total or limit):
        delivered.append(f'Показано записей: {len(delivered)} из {total}.' if limit is not None else f'Всего записей: {total}.')
    return delivered


def collection_link(proof, delivery):
    if not delivery or delivery.get('complete') is not False:
        return ''
    arguments = proof.get('arguments', {})
    query = {key: value for key, value in arguments.get('query', {}).items() if key not in ('offset', 'limit')}
    if proof['tool'] == 'tasks_find':
        path = '/api/v1/assistant/workspace/tasks'
    elif proof['tool'] == 'equipment_service_history':
        identity = arguments.get('path', {}).get('equipment_id', '')
        if not re.fullmatch(UUID, identity, re.I):
            return ''
        path = f'/api/v1/assistant/workspace/equipment/{identity}/history'
    else:
        return ''
    # The source performs the same authorization on each page. Start at the
    # beginning when the assistant could not confirm a complete snapshot.
    offset = delivery['rows'] if proof['tool'] == 'tasks_find' and delivery.get('total', 0) and delivery['rows'] < delivery['total'] else 0
    delivery['continuation'] = True
    page = 'следующую' if offset else 'первую'
    return f'\n[Открыть {page} страницу источника]({path}?{urlencode({**query, "offset": offset})}).'


def render(goal, proofs, request='', *, delivery=None):
    meta = goal['semantic']
    intent = meta['intent']
    if meta.get('block'):
        return meta['block']
    if goal.get('message') and (goal['status'] in ('blocked', 'partial', 'awaiting_input') and goal.get('reason') != 'semantic_page'):
        return label(goal['message'])
    if intent == 'reference_details':
        task, equipment = (_read(proofs, tool) for tool in REFERENCE_SOURCES)
        if task is not None and equipment is not None:
            return 'Этот ID совпал у задания и оборудования. Уточните тип карточки.'
        if task is not None and 'equipment_read' in goal.get('reference_misses', []):
            return _row(task['task'], meta['fields'])
        if equipment is not None and 'task_read' in goal.get('reference_misses', []):
            return _row(equipment, meta['fields'], 'equipment_id')
        if len(goal.get('reference_misses', [])) == len(REFERENCE_SOURCES):
            return 'Доступное задание или оборудование с таким ID не найдено.'
        return 'Не удалось подтвердить тип карточки по доступным источникам.'
    proof = next((proof for proof in reversed(proofs) if proof['tool'] == goal['tool']), None)
    value = proof['result'] if proof and proof.get('status') in (None, 'FOUND', 'EMPTY', 'PARTIAL') else None
    if value is None:
        return 'Не удалось подтвердить результат по доступному источнику.'
    scope_errors = {'requested_resource_mismatch', 'result_resource_mismatch', 'requested_equipment_code_not_verified',
                    'requested_period_mismatch', 'result_period_mismatch', 'history_equipment_reference_unverified',
                    'requested_task_scope_not_verified', 'requested_task_row_scope_mismatch', 'read_outcome_result_shape_mismatch'}
    if scope_errors.intersection(proof.get('limitations', [])):
        return 'Полученные данные не подтвердили выбранное оборудование, период или вид результата.'
    complete = proof.get('complete', goal.get('status') == 'completed')
    if intent in ('equipment_details', 'self_profile'):
        return _row(value, meta['fields'], 'equipment_id' if intent == 'equipment_details' else 'userId')
    if intent == 'equipment_exists':
        if goal['tool'] == 'equipment_read':
            return f'Оборудование {label(meta["subject"])} найдено.'
        resolution = resolve_equipment(proof, meta['subject'], exact_name=bool(meta.get('exact_name')))
        result = equipment_resolution_text(resolution, meta['subject'])
        if meta.get('external_registry_unavailable'):
            result += '\nУпомянутая выгрузка отсутствует среди вложений. Проверен актуальный реестр.'
        return result
    if intent == 'task_details':
        item = value.get('task') or {}
        return _row({**item, 'checklist': (value.get('execution') or {}).get('checklist')}, meta['fields'])
    if intent == 'task_count':
        if meta.get('list_period'):
            total = value.get('total') if value.get('period') == meta['list_period'] else None
        else:
            total = value.get('counters', {}).get(meta['counter']) if meta.get('counter') else value.get('selected_tasks')
            if value.get('complete') is not True:
                total = None
        return str(total) if type(total) is int else 'Не удалось подтвердить полное число заданий.'
    if intent == 'task_list':
        if meta.get('summary_only') and type(value.get('total')) is int:
            return f'Подходящих заданий: {value["total"]}.'
        rows = value.get('items', [])
        overdue = meta['period'] == 'overdue'
        selected = [item for item in rows if not overdue or item.get('isOverdue') is True]
        limit = meta.get('limit')
        lines = ['- ' + _row(item, meta['fields']) for item in selected]
        if not lines and complete:
            return 'Подходящих заданий нет.'
        complete = complete or bool(limit and len(lines) >= limit and proof.get('limitations') == ['page_only'])
        lines = collection_lines(lines, total=value.get('total'), complete=complete, limit=limit,
                                 location='раздел заданий', delivery=delivery)
        return '\n'.join(lines) + collection_link(proof, delivery)
    if intent == 'equipment_tasks':
        if meta.get('summary_only') and type(value.get('total')) is int:
            return f'Подходящих заданий: {value["total"]}.'
        rows = value['items']
        if meta['period'] == 'overdue':
            rows = [row for row in rows if row.get('isOverdue') is True]
        fields = list(dict.fromkeys([*meta['fields'], *(['id'] if not meta.get('exclude_id') else [])]))
        lines = [f'- {_row(row, fields)}' for row in rows]
        if not lines and complete:
            return 'Подходящих заданий нет.'
        limit = meta.get('limit')
        complete = complete or bool(limit and len(lines) >= limit and proof.get('limitations') == ['page_only'])
        lines = collection_lines(lines, total=value.get('total'), complete=complete, limit=limit,
                                 location='раздел заданий', delivery=delivery)
        return '\n'.join(lines) + collection_link(proof, delivery)
    if intent == 'staff_details':
        return _row(value, meta['fields'], 'user_id') if goal['tool'] == 'staff_read' else _staff(value, meta)
    if intent in ('maintenance_history', 'latest_maintenance'):
        rows = [row for row in value.get('items', []) if row.get('actual_date_verified') and row.get('performed_at')
                and row.get('accepted_at') and not row.get('actual_date_conflict')]
        lines = [f'- {_instant(row["performed_at"])} · отчёт {row["report_id"]}' for row in rows]
        if not lines:
            return ('Принятых отчётов с подтверждённой датой в проверенной области нет.' if complete else
                         'Дату фактического обслуживания по доступным отчётам подтвердить не удалось.')
        if intent == 'latest_maintenance':
            period = [f'Период принятых работ {value["starts_on"]} — {value["ends_on"]}.'] if meta.get('show_history_period') else []
            return '\n'.join([*period, *lines] if complete else [*period, *lines, 'Последнее фактическое обслуживание не установлено.'])
        lines = collection_lines(lines, total=value.get('total'), complete=complete,
                                 limit=meta.get('limit'), location='карточку оборудования', delivery=delivery)
        if meta.get('show_history_period'):
            lines.insert(0, f'Период принятых работ {value["starts_on"]} — {value["ends_on"]}.')
        return '\n'.join(lines) + collection_link(proof, delivery)
    if intent in ('service_frequency', 'active_regulations'):
        lines = []
        day = meta.get('local_date')
        for rule in value:
            if not rule.get('enabled'):
                continue
            if day and not (rule['valid_from'] <= day and (rule['valid_until'] is None or rule['valid_until'] >= day)):
                continue
            try:
                frequency = pattern_description(CalendarPattern.model_validate_json(json.dumps(rule.get('pattern'))))
            except ValidationError:
                frequency = 'периодичность в сохранённом регламенте не подтверждена'
            reference = (f' · привязка {rule["binding_id"]}, версия {rule["rule_version"]}'
                         if intent == 'active_regulations' or re.search(r'\b(?:uuid|id|идентификатор\w*)\b', positive_text(request), re.I) else '')
            lines.append(f'- {label(rule["title"])}: {label(frequency)}{reference}.')
        if lines:
            dated = (' По датам действия опубликованных сейчас записей на ' + day + '. '
                     'История публикаций на эту дату не подтверждена.') if meta.get('show_regulation_cutoff') and day else ''
            return 'По сохранённому регламенту объекта.' + dated + '\n' + '\n'.join(lines)
        if meta.get('show_regulation_cutoff') and day and complete:
            return f'Среди опубликованных сейчас записей регламент на {day} не найден. История публикаций на эту дату не подтверждена.'
        return ('Действующий сохранённый регламент не найден.' if complete else
                'Наличие действующего регламента не подтверждено.')
    if intent == 'maintenance_calendar':
        lines = [f'Период расчёта {value["starts_on"]} — {value["ends_on"]} · {value["timezone"]}.']
        next_dates = []
        for configuration in value['configurations']:
            if not configuration['complete']:
                lines.append('По одной из конфигураций полный расчёт недоступен.')
            for occurrence in configuration['occurrences']:
                effective = occurrence['effective_date']
                if meta['calendar_view'] == 'period' or effective >= meta['local_date']:
                    next_dates.append((effective, occurrence['source_date'], configuration['source']['binding_id']))
        if next_dates and meta['calendar_view'] == 'period':
            dates = [f'- {effective} · исходная дата {source} · привязка {binding}.'
                     for effective, source, binding in sorted(next_dates)]
            lines.extend(collection_lines(dates, complete=complete, limit=meta.get('limit'), delivery=delivery))
        elif next_dates:
            effective, source, binding = min(next_dates)
            prefix = 'Ближайшая расчётная обязанность' if complete else 'Дата в доступной части расчёта'
            lines.append(f'{prefix} — {effective} · исходная дата {source} · привязка {binding}.')
        elif complete:
            lines.append('В проверенном диапазоне подходящих расчётных обязанностей нет.')
        return '\n'.join(lines)
    if intent == 'workbook_row':
        return _workbook(value, meta, request)
    if intent == 'notifications':
        lines = ['- ' + label(row['message']) for row in value if row.get('message')]
        return '\n'.join(lines) or ('Уведомлений нет.' if complete else 'Полный список уведомлений не подтверждён.')
    return 'Не удалось подтвердить результат по доступному источнику.'
