"""Bounded factual presentation; no model calls, calculations or workflow mutation."""
from dataclasses import dataclass
import re
from urllib.parse import quote, urlencode

_LABELS = {
    'full_name': 'ФИО', 'name': 'Название', 'role': 'Роль',
    'asset_code': 'Инвентарный код', 'commissioned_on': 'Дата ввода', 'revision': 'Версия',
    'location': 'Расположение', 'serial_number': 'Серийный номер',
    'raw_norm_value': 'Исходная норма', 'norm_hours': 'Трудоёмкость',
    'crew_size': 'Требуется исполнителей', 'planning_duration_minutes': 'Длительность, мин',
    'is_active': 'Доступ действует', 'membership_is_active': 'Членство активно',
    'account_is_active': 'Учётная запись активна', 'email': 'Email',
    'employed_from': 'Начало работы', 'employed_until': 'Окончание работы',
    'qualifications': 'Квалификации', 'shifts': 'Смены', 'availability': 'Доступность',
    'verified_at': 'Подтверждено', 'valid_until': 'Действует до', 'valid_from': 'Действует с',
    'starts_local': 'Начало смены', 'ends_local': 'Окончание смены',
    'starts_at': 'Начало', 'ends_at': 'Окончание', 'pattern': 'Правило повторения',
    'staff': 'Сотрудники', 'crews': 'Бригады', 'skills': 'Квалификации',
    'task': 'Задание', 'execution': 'Отчёт', 'review': 'Фотоанализ', 'decision': 'Решение',
    'instructions': 'Инструкция', 'checklist': 'Чек-лист', 'answer': 'Ответ',
    'assignees': 'Исполнители', 'summary': 'Работа', 'state': 'Состояние',
    'normHours': 'Норма', 'normUnit': 'Единица нормы', 'norm_unit': 'Единица нормы',
    'durationMinutes': 'Длительность, мин', 'crewSize': 'Требуется исполнителей',
    'narrative': 'Комментарий отчёта', 'readings': 'Показания', 'acts': 'Акты',
    'actual': 'Фактические данные', 'requiredActs': 'Обязательные акты',
    'measurementRequirements': 'Обязательные измерения', 'reason': 'Причина',
    'verdict': 'Решение', 'decidedBy': 'Проверил', 'decidedAt': 'Дата решения',
    'scheduledStart': 'Назначенное начало', 'scheduledEnd': 'Назначенное окончание',
    'mandatoryDueDate': 'Нормативный срок', 'submittedAt': 'Отправлено',
    'before': 'До', 'after': 'После', 'worker_labels': 'Имена исполнителей',
    'worker_ids': 'Исполнители', 'person_hours': 'Трудоёмкость, чел·ч',
    'start_at': 'Начало', 'end_at': 'Окончание', 'locked': 'Закреплено',
    'items': 'Записи', 'total': 'Всего', 'title': 'Название', 'status': 'Состояние',
    'value': 'Значение', 'unit': 'Единица', 'complete': 'Полнота подтверждена',
}
_ROLES = {'director': 'Руководитель', 'chief_engineer': 'Главный инженер',
          'engineer': 'Инженер', 'dispatcher': 'Диспетчер',
          'executor': 'Исполнитель', 'admin': 'Администратор'}
_PRIVATE = re.compile(r'password|secret|token|cookie|authorization|api.?key|csrf', re.I)
_INTERNAL = {'trace', 'evidence', 'prompt', 'system_prompt', 'messages', 'headers',
             'raw_response', 'raw_request', 'metrics', 'internal', 'chain_of_thought',
             'allowedactions', 'payload_sha256', 'resource_sha256', 'sha256'}


@dataclass(frozen=True)
class FactPresentation:
    lines: list[str]
    truncated: bool
    protected_fields_omitted: int
    details_url: str | None
    nodes: int = 0
    rows: int = 0
    compact_rows: int = 0
    characters: int = 0


def _inline(value):
    # Source strings stay data, not Markdown directives or injected links.
    result = str(value).replace('\r', '').replace('\n', ' / ')
    for char in ('\\', '*', '_', '[', ']', '<', '>', '|', chr(96)):
        result = result.replace(char, '\\' + char)
    return result


def _details(tool, arguments):
    paths = {
        'staff_read': ('/api/v1/assistant/workspace/staff/', 'user_id'),
        'task_read': ('/api/v1/maintenance/ui/tasks/', 'task_id'),
    }
    if tool in paths:
        prefix, field = paths[tool]
        identity = (arguments.get('path') or {}).get(field)
        # IDs originated in validated arguments, but never interpolate arbitrary paths.
        if isinstance(identity, str) and re.fullmatch(r'[0-9a-fA-F-]{36}', identity):
            return prefix + quote(identity, safe='')
    if tool == 'workforce_read':
        return '/api/v1/maintenance/management/workforce'
    if tool == 'draft_changes':
        query = arguments.get('query') or {}
        identity = query.get('identity')
        if (isinstance(identity, str) and re.fullmatch(r'[0-9a-fA-F-]{36}', identity)
                and all(type(query.get(k)) is int and query[k] > 0
                        for k in ('before_revision', 'after_revision'))):
            return '/api/v1/assistant/workspace/draft-changes?' + urlencode({
                k: query[k] for k in ('identity', 'before_revision', 'after_revision')})
    return None


def _scalar(value):
    return ('не указано' if value is None else 'да' if value is True else 'нет' if value is False
            else 'пустая строка' if value == '' else str(value))


def _equipment_list(value, *, max_rows, max_characters):
    """A registry list needs each identity, not every property of each card."""
    max_rows = min(50, max(0, max_rows))
    items = value['items']
    total = value.get('total')
    total = str(total) if type(total) is int and total >= 0 else 'не установлено'
    lines = [f'Найдено: {total}. Прочитано: {len(items)}.',
             'Краткий список: код, название, состояние и дата ввода. Остальные поля карточек не показаны.']
    shown = characters = 0
    truncated = False
    for row in items[:max_rows]:
        if not isinstance(row, dict):
            truncated = True
            break
        line = '- ' + '; '.join(_inline(_scalar(row.get(key))) for key in ('asset_code', 'name'))
        line += '; состояние: ' + _inline(_scalar(row.get('status')))
        line += '; дата ввода: ' + _inline(_scalar(row.get('commissioned_on'))) + '.'
        if characters + len(line) > max_characters:
            truncated = True
            break
        lines.append(line)
        shown += 1
        characters += len(line)
    truncated = truncated or shown < len(items)
    lines.append(f'Показано: {shown} из {len(items)} прочитанных строк.')
    if truncated:
        lines.append(f'Список показан частично: предел {max_rows} строк и {max_characters} символов. '
                     'Уточните фильтр или страницу; весь прочитанный результат здесь не показан.')
    return FactPresentation(lines, truncated, 0, None,nodes=shown,compact_rows=shown,characters=len('\n'.join(lines)))


def _tasks_list(value, *, max_rows, max_characters):
    max_rows = min(50, max(0, max_rows))
    items = value['items']
    total = value.get('total')
    total_text = str(total) if type(total) is int and total >= 0 else 'не установлено'
    periods = {'upcoming': 'ближайшие', 'all': 'все активные'}
    period_label = periods.get(str(value.get('period') or ''), str(value.get('period') or 'не указан'))
    states = {'draft': 'черновик', 'assigned': 'назначено', 'in_progress': 'в работе',
              'submitted': 'на проверке', 'rework': 'на доработке', 'rework_required': 'на доработке',
              'accepted': 'принято', 'cancelled': 'отменено'}
    lines = [f'Найдено заданий: {total_text} (период: {period_label}).']
    if not items:
        lines.append('Подходящих заданий не найдено.')
        return FactPresentation(lines, False, 0, None, nodes=1, compact_rows=0, characters=len('\n'.join(lines)))
    shown = characters = 0
    truncated = False
    for row in items[:max_rows]:
        if not isinstance(row, dict):
            truncated = True
            break
        title = _inline(row.get('title') or row.get('summary') or 'Задание')
        code = _inline(row.get('code') or '')
        eq = _inline(row.get('equipmentName') or 'оборудование не указано')
        state_ru = _inline(states.get(row.get('state'), row.get('state') or 'не указано'))
        due = _inline(row.get('mandatoryDueDate') or 'не указан')
        plan = _inline(str(row.get('scheduledStart') or 'не назначено')[:16].replace('T', ' '))
        assignees = row.get('assignees') if isinstance(row.get('assignees'), list) else []
        names = ', '.join(_inline(a.get('name')) for a in assignees if isinstance(a, dict) and a.get('name')) or 'не назначены'
        head = f'- {title} ({code})' if code else f'- {title}'
        line = f'{head} — {eq}; состояние: {state_ru}; срок: {due}; план: {plan}; исполнители: {names}.'
        if characters + len(line) > max_characters:
            truncated = True
            break
        lines.append(line)
        shown += 1
        characters += len(line)
    truncated = truncated or shown < len(items)
    if truncated:
        lines.append(f'Показано {shown} из {len(items)} прочитанных заданий (предел {max_rows} строк).')
    return FactPresentation(lines, truncated, 0, None, nodes=shown, compact_rows=shown, characters=len('\n'.join(lines)))


def present_facts(value, *, tool, arguments=None, max_rows=25, max_compact_rows=50, max_nodes=140,
                  max_depth=6, max_characters=12000):
    """Render facts; compact equipment has its own <=50 row budget, no per-card expansion."""
    arguments = arguments or {}
    if tool == 'equipment_find' and isinstance(value, dict) and isinstance(value.get('items'), list):
        return _equipment_list(value, max_rows=max_compact_rows, max_characters=max_characters)
    if tool == 'tasks_find' and isinstance(value, dict) and isinstance(value.get('items'), list):
        return _tasks_list(value, max_rows=max_compact_rows, max_characters=max_characters)
    rows = nodes = characters = hidden = 0
    truncated = False
    lines = []

    def append(text):
        nonlocal characters, truncated
        remaining = max_characters - characters
        if remaining <= 0:
            truncated = True
            return
        if len(text) > remaining:
            text = text[:remaining] + ' … [текст сокращён]'
            truncated = True
        lines.append(text)
        characters += len(text)

    def walk(node, label, depth):
        nonlocal rows, nodes, hidden, truncated
        if nodes >= max_nodes or depth > max_depth or characters >= max_characters:
            truncated = True
            return
        nodes += 1
        prefix = '  ' * min(depth, max_depth) + '- '
        if isinstance(node, dict):
            append(prefix + label + (':' if node else ': нет полей.'))
            for key, item in node.items():
                key = str(key)
                if _PRIVATE.search(key) or key.casefold() in _INTERNAL or (tool == 'enrollment_read' and key == 'code'):
                    hidden += 1
                    continue
                if nodes >= max_nodes or characters >= max_characters:
                    truncated = True
                    break
                walk(item, _LABELS.get(key, _inline(key)), depth + 1)
        elif isinstance(node, list):
            append(prefix + label + ': записей ' + str(len(node)) + '.')
            for index, item in enumerate(node):
                if rows >= max_rows or characters >= max_characters:
                    append(prefix + 'Показано ' + str(index) + ' из ' + str(len(node)) + ' записей этого раздела.')
                    truncated = True
                    break
                rows += 1
                walk(item, 'Запись ' + str(index + 1), depth + 1)
        else:
            text = ('не указано' if node is None else 'да' if node is True
                    else 'нет' if node is False else 'пустая строка' if node == ''
                    else _ROLES.get(node, node) if label == 'Роль' and isinstance(node, str)
                    else node)
            append(prefix + label + ': ' + _inline(text) + '.')

    walk(value, 'Данные сервера', 0)
    details = _details(tool, arguments)
    if hidden:
        lines.append('Защищённые и служебные поля не показаны.')
    if truncated:
        lines.append('Показана ограниченная часть результата: общий предел ' +
                     str(max_rows) + ' записей, ' + str(max_nodes) + ' полей, глубина ' +
                     str(max_depth) + ', до ' + str(max_characters) + ' символов основного текста.')
    if details:
        lines.append('[Открыть текущий ответ сервера с проверкой доступа](' + details + ').')
        lines.append('Ссылка повторно читает текущие данные; это не сохранённый снимок исходного ответа.')
        if tool == 'draft_changes':
            lines.append('Ссылка открывает первую страницу; полный список читается по страницам с параметром offset.')
    elif truncated:
        lines.append('Полная ссылка для этой операции пока не предусмотрена. Уточните раздел или страницу; весь результат здесь не показан.')
    return FactPresentation(lines, truncated, hidden, details,nodes=nodes,rows=rows,characters=len('\n'.join(lines)))
