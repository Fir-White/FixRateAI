"""Server-owned steps for an executor's saved work order."""
from dataclasses import dataclass
import json
import re
from uuid import UUID

from fastapi import HTTPException

from app.schemas.assistant import GoalSpec, ToolSelection

from . import workflow as wf
from .semantic_plan import QUOTED, UUID as UUID_PATTERN, asset_references


STAGES = (
    ('task', 'Проверить исполнителя и найти задание', 'task_read'),
    ('start', 'Начать работу', 'task_start'),
    ('checklist', 'Получить чек-лист и запросить факты', 'task_read'),
    ('draft', 'Подготовить фактический отчёт', 'report_save'),
    ('submit', 'Передать отчёт инженеру на приёмку', 'report_submit'),
)
START = r'\b(?:начни(?:те)?|приступи(?:те)?|запусти(?:те)?)\b'
SUBMIT = r'\b(?:отправь(?:те)?|передай(?:те)?|сдай(?:те)?|направь(?:те)?)\b'
REPORT = r'\bотч[её]т\w*\b'
CHECKLIST = r'\bчек[-‑– ]?лист\w*\b'
QUOTES = re.compile(QUOTED.pattern + r'|“([^”]+)”|„([^“]+)“|`([^`]+)`')
FACTS = re.compile(r'^\s*факты\s*:\s*', re.I)


def request(text):
    """Recognize a direct task instruction and keep quoted titles out of verbs."""
    source = QUOTES.sub(' ', text).casefold()
    has_checklist = bool(re.search(CHECKLIST, source))
    has_report = bool(re.search(REPORT, source))
    if not re.search(START, source) or not (has_checklist or has_report):
        return None
    stages = ['task', 'start', 'checklist']
    if re.search(r'\b(?:заполни(?:те)?|сохрани(?:те)?|подготовь(?:те)?|составь(?:те)?)\b', source) or has_report:
        stages.append('draft')
    if has_report and re.search(SUBMIT, source):
        stages.append('submit')
    ambiguous_start = (re.search(r'\b(?:не|пример|покажи|объясни|как)\s+[^,.!?;]{0,40}?' + START, source)
                       or re.search(r'\bесли\s+[^,.!?;]{0,40}?,?\s*' + START, source))
    if ambiguous_start or re.search(
        r'\b(?:не|если)\s+[^,.!?;]{0,40}?\b(?:отправ|переда|сда|направ|заполн|сохран|подготов)\w*', source
    ):
        return dict(stages=stages, clarification='Укажите прямо, какие этапы нужно выполнить сейчас.')
    if re.search(r'\b(?:переключи(?:те(?:сь)?|сь)?|перейди(?:те)?)\s+(?:на|в)\b', source):
        return dict(stages=stages, clarification='Сначала выберите нужный объект в меню, затем отправьте поручение из его диалога.')
    selectors = [next(value for value in match.groups() if value is not None)
                 for match in QUOTES.finditer(text)]
    ids = set(re.findall(r'\b' + UUID_PATTERN + r'\b', QUOTES.sub(' ', text), re.I))
    ids.update(value for value in selectors if re.fullmatch(UUID_PATTERN, value, re.I))
    titles = [value.strip() for value in selectors if not re.fullmatch(UUID_PATTERN, value, re.I)]
    codes = asset_references(QUOTES.sub(' ', text))
    if len(ids) > 1 or len(titles) > 1 or len(codes) > 1:
        return dict(stages=stages, clarification='Для этого поручения укажите одно задание и один пост.')
    return dict(stages=stages, task_id=next(iter(ids), None), title=next(iter(titles), None),
                code=next(iter(codes), None))


def build_plan(command, question, tools, scope):
    specs = []
    for stage, title, tool in STAGES:
        if stage in command['stages']:
            specs.append(GoalSpec(id=stage, title=title, tool=tool if tool in tools else '',
                                  depends_on=[specs[-1].id] if specs else [], required_evidence='saved_data'))
    state = wf.create_plan(ToolSelection(tools=[], goals=specs), question, tools, scope)
    state['task_execution'] = command
    return state


@dataclass(frozen=True)
class Step:
    status: str
    message: str
    reason: str | None = None
    arguments: dict | None = None


def blocked(reason, message):
    return Step('blocked', message, reason)


def _normalize(value):
    return ' '.join(value.casefold().split())


def _missing_answers(report):
    return [(index, item) for index, item in enumerate(report['checklist'], 1) if item.get('required', True)
            and (not str(item.get('answer') or '').strip()
                 or item['answerKind'] == 'boolean' and item['answer'] != 'done')]


def checklist_text(report):
    rows = []
    for index, item in enumerate(report['checklist'], 1):
        kind = {'boolean': 'подтверждение выполнения', 'number': item.get('unit') or 'число'}.get(item['answerKind'], 'текст')
        details = [kind, 'обязательно' if item.get('required', True) else 'по необходимости']
        if item.get('photoRequired'):
            details.append('фото до и после с одного ракурса')
        rows.append(f"{index}. {item['text']} ({', '.join(details)})")
    return '\n'.join(rows)


def missing_report(task, report):
    missing = [f"Пункт {index} — {item['text']}" for index, item in _missing_answers(report)]
    raw_order_equipment = task.get('equipmentIds') or (
        [] if task.get('equipmentId') is None else [task['equipmentId']]
    )
    order_equipment_ids = {str(eq) for eq in raw_order_equipment if eq is not None}
    paired = {}
    for photo in report['photos']:
        view_key = (photo.get('viewKey') or '').strip()
        raw_eq = photo.get('equipmentId')
        eq_id = str(raw_eq) if raw_eq is not None else None
        if not view_key:
            continue
        if order_equipment_ids and eq_id is not None and eq_id not in order_equipment_ids:
            continue
        paired.setdefault((photo['checklistItemId'], view_key, eq_id), set()).add(photo['phase'])
    with_pairs = {item_id for (item_id, _, _), phases in paired.items() if {'before', 'after'} <= phases}
    missing.extend(f"Пункт {index} — фото до и после с одного ракурса"
                   for index, item in enumerate(report['checklist'], 1)
                   if item.get('photoRequired') and item['id'] not in with_pairs)
    actual = report['actual'] or {}
    for key, label in (('started_at', 'Фактическое начало'), ('performed_at', 'Фактическое окончание'),
                       ('person_hours', 'Фактические трудозатраты, чел·ч')):
        if task.get('actualRequired') and not actual.get(key):
            missing.append(label)
    measurements = {(row['parameter_code'], row['unit'], row['phase']) for row in report['readings']}
    for requirement in task.get('measurementRequirements', []):
        if requirement.get('required', True):
            code, unit = requirement['parameter_code'], requirement['unit']
            for phase in requirement.get('phases', ['before', 'after']):
                if (code, unit, phase) not in measurements:
                    missing.append(f"Показание {code} ({unit}), {'до работы' if phase == 'before' else 'после работы'}")
    held_acts = {act.get('kind') for act in report['acts']}
    missing.extend(f'Акт или протокол — {kind}' for kind in task.get('requiredActs', []) if kind not in held_acts)
    return missing


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def report_payload(source, task, report):
    """Only explicit human-supplied values are merged with the fresh draft."""
    from app.main import ReportEdit

    value = FACTS.sub('', source, count=1)
    if value.lstrip().startswith('{'):
        fields = json.loads(value, object_pairs_hook=_unique_pairs)
    else:
        pairs = [_split_fact(line) for line in value.splitlines() if line.strip()]
        keyed = _unique_pairs(pairs)
        fields = {'answers': {key: answer for key, answer in keyed.items() if key != 'описание'}}
        if 'описание' in keyed:
            fields['narrative'] = keyed['описание']
    if not isinstance(fields, dict) or not fields or fields.keys() - {'answers', 'narrative', 'actual', 'readings'}:
        raise ValueError('unknown report fields')
    answers = fields.get('answers', {})
    if not isinstance(answers, dict) or (not answers and set(fields) == {'answers'}):
        raise ValueError('missing answers')
    by_number = {str(index): item for index, item in enumerate(report['checklist'], 1)}
    updates = {}
    for number, answer in answers.items():
        if number not in by_number or not isinstance(answer, str) or not answer.strip():
            raise ValueError('invalid checklist response')
        item = by_number[number]
        answer = answer.strip()
        if item['answerKind'] == 'boolean':
            answer = {'выполнено': 'done', 'не выполнено': 'not_done', 'не применимо': 'not_applicable'}.get(answer.casefold())
            if answer is None:
                raise ValueError('invalid execution confirmation')
        if item['answerKind'] == 'number':
            from decimal import Decimal, InvalidOperation
            answer = answer.replace(',', '.')
            try:
                if not Decimal(answer).is_finite():
                    raise ValueError('invalid number')
            except InvalidOperation as exc:
                raise ValueError('invalid number') from exc
        updates[UUID(item['id'])] = answer
    actual = fields.get('actual', {})
    readings = fields.get('readings', [])
    if not isinstance(actual, dict) or not isinstance(readings, list):
        raise ValueError('invalid execution data')
    merged_readings = {(r['equipment_id'], r['parameter_code'], r['phase']): r for r in report['readings']}
    explicit_readings = set()
    for reading in readings:
        if not isinstance(reading, dict) or task.get('equipmentId') is None:
            raise ValueError('invalid equipment reading')
        row = {'equipment_id': task['equipmentId'], **reading}
        key = (row['equipment_id'], row.get('parameter_code'), row.get('phase'))
        if row['equipment_id'] != task['equipmentId'] or key in explicit_readings:
            raise ValueError('invalid reading target')
        explicit_readings.add(key)
        merged_readings[key] = row
    payload = ReportEdit.model_validate(dict(expected_revision=task['revision'],
        narrative=fields.get('narrative', report['narrative']), answers=updates,
        actual={**(report.get('actual') or {}), **actual} or None, readings=list(merged_readings.values())))
    return payload.model_dump(mode='json')


def _split_fact(line):
    key, separator, value = line.partition(':')
    if not separator or not value.strip():
        raise ValueError('invalid report line')
    return key.strip().casefold(), value.strip()


async def step(state, goal, content, read):
    context = state['task_execution']
    phase = goal['id']
    if phase == 'task':
        if state['scope']['role'] != 'executor':
            return blocked('executor_role_required', 'Начать работу может назначенный исполнитель. Откройте диалог под его учётной записью.')
        if context.get('clarification'):
            return blocked('task_selection_required', context['clarification'])
        task_id, title = context.get('task_id'), context.get('title')
        if not task_id:
            if not title or len(title) > 200:
                return blocked('task_selection_required', 'Укажите точное название задания в кавычках или его ID.')
            result = await read('tasks_find', {'query': {'q': title, 'period': 'all', 'active_only': False}})
            matches = [task for task in result['items'] if _normalize(task['title']) == _normalize(title)]
            if not result.get('page_complete') or len(matches) > 1:
                return blocked('task_ambiguous', 'Найдено несколько возможных заданий. Откройте нужную карточку и укажите её ID.')
            if not matches:
                return blocked('task_not_visible', 'Задание с этим названием не найдено среди доступных вам на текущем объекте.')
            task_id = matches[0]['id']
    else:
        task_id = context['resolved_task_id']

    path = {'task_id': task_id}
    try:
        bundle = await read('task_read', {'path': path})
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            return blocked('task_not_visible', 'Задание недоступно в текущем объекте. Проверьте назначение и выбранный объект.')
        raise
    task = {**bundle['task'], 'actualRequired': bundle.get('actualRequired', False)}
    report, allowed = bundle['execution'], bundle['allowedActions']
    if phase == 'task':
        if title and _normalize(task['title']) != _normalize(title):
            return blocked('task_title_mismatch', 'Название найденного задания отличается. Проверьте название и ID в карточке.')
        if context.get('code'):
            if not task.get('equipmentId'):
                return blocked('equipment_mismatch', 'У задания нет привязанного оборудования. Уточните пост в карточке.')
            equipment = await read('equipment_read', {'path': {'equipment_id': task['equipmentId']}})
            if _normalize(equipment.get('asset_code') or '') != _normalize(context['code']):
                return blocked('equipment_mismatch', f"Задание относится к оборудованию «{task['equipmentName']}». Указанный пост не совпадает.")
        context['resolved_task_id'] = task['id']
        return Step('completed', f"Задание «{task['title']}» доступно вам как исполнителю. Оборудование — {task['equipmentName']}.")
    args = {'path': path, 'body': {'expected_revision': task['revision']}}
    if phase == 'start':
        if 'edit_report' in allowed and report and report['state'] == 'draft':
            return Step('completed', 'Работа уже начата. В карточке открыт ваш черновик.')
        if 'start' not in allowed:
            return blocked('task_start_unavailable', 'Начало работы сейчас недоступно. Проверьте состояние наряда и утверждённый чек-лист в карточке.')
        if FACTS.match(content):
            return Step('awaiting_input', 'Сначала начните работу. Нажмите «Продолжить поручение», чтобы получить карточку подтверждения.', 'start_before_facts')
        return Step('awaiting_confirmation', f"Подтвердите начало работы по заданию «{task['title']}».", arguments=args)
    if not report or report['state'] != 'draft' or 'edit_report' not in allowed:
        return blocked('report_not_editable', 'Доступный вам черновик отсутствует. Проверьте, кто ведёт отчёт и в каком он состоянии.')
    if context.get('report_id', report['id']) != report['id']:
        return blocked('report_attempt_changed', 'Открыта другая попытка отчёта. Сверьте её данные и начните новое поручение.')
    if phase == 'checklist':
        context['report_id'] = report['id']
        return Step('completed', 'Чек-лист из карточки задания\n\n' + (checklist_text(report) or 'Пунктов в сохранённом чек-листе нет.'))
    if phase == 'draft' and FACTS.match(content):
        try:
            args['body'] = report_payload(content, task, report)
        except (ValueError, TypeError):
            return Step('awaiting_input',
                        'Проверьте формат. Начните с «Факты:», затем укажите номер пункта и фактический ответ через двоеточие. Для отметки используйте «выполнено», «не выполнено» или «не применимо».',
                        'invalid_report_facts')
        return Step('awaiting_confirmation', 'Сверьте введённые факты в карточке действия и подтвердите сохранение черновика.', arguments=args)
    missing = missing_report(task, report)
    if missing:
        help_text = ('Укажите реальные ответы в сообщении «Факты:», по одному пункту на строку в формате «номер: ответ». '
                     'Показания по методике, время, фото и акты можно внести в карточке задания. После сохранения нажмите «Продолжить поручение».'
                     if phase == 'draft' else 'Внесите недостающие данные в карточке задания, затем нажмите «Продолжить поручение».')
        return Step('awaiting_input', 'Для отчёта ещё нужны:\n\n' + '\n'.join('- ' + row for row in missing) + '\n\n' + help_text,
                    'report_facts_required')
    if phase == 'draft':
        has_facts = any(report[field] for field in ('narrative', 'actual', 'readings', 'photos', 'acts')) or any(
            item.get('answer') for item in report['checklist'])
        if not has_facts:
            return Step('awaiting_input', 'Укажите фактическое описание или ответы в черновике, затем продолжите поручение.', 'report_facts_required')
        return Step('completed', 'Фактические данные для отчёта уже сохранены в карточке.')
    if 'submit' not in allowed:
        return blocked('report_submit_unavailable', 'Отправка этого отчёта сейчас недоступна. Проверьте карточку задания.')
    return Step('awaiting_confirmation', 'Сверьте сохранённый отчёт и подтвердите отправку инженеру на приёмку.', arguments=args)


ACTION_MESSAGES = {
    'action_rejected': 'Вы отклонили действие. Для нового предложения отправьте новое поручение.',
    'action_stale': 'Карточка изменилась после подготовки предложения. Проверьте текущие данные и отправьте новое поручение.',
    'action_expired_request_fresh_proposal': 'Срок предложения истёк. Отправьте новое поручение для свежей карточки.',
    'action_failed': 'Система отклонила изменение. Откройте карточку задания и проверьте причину в результате действия.',
    'action_unavailable': 'Карточка подтверждения недоступна.',
    'action_executing': 'Система применяет подтверждённое действие.',
    'postcondition_unverified': 'Система не подтвердила итоговое состояние. Проверьте карточку задания перед повторной командой.',
    'read_only_reconciliation_required': 'Итог записи неизвестен. Проверьте карточку задания перед повторной командой.',
    'continue_task_from_verified_api': 'Черновик сохранён и проверен. Продолжите поручение, чтобы проверить его готовность.',
}


def message_for(goal):
    if goal['status'] == 'completed' and goal['id'] == 'start' and goal.get('action_id'):
        return 'Начало работы подтверждено. Черновик открыт.'
    if goal['status'] == 'completed' and goal['id'] == 'submit':
        return 'Отчёт передан инженеру. Статус задания — на приёмке.'
    return ACTION_MESSAGES.get(goal.get('reason'), goal.get('message'))


def render(state):
    sections = []
    for goal in state['goals']:
        message = message_for(goal)
        if message:
            sections.append(message)
        if goal['status'] != 'completed':
            if goal['id'] == 'checklist' and goal['status'] == 'planned':
                sections.append('Нажмите «Продолжить поручение», чтобы получить чек-лист.')
            break
    if not sections:
        sections.append('Не удалось проверить текущий этап. Продолжите сохранённое поручение.')
    task_id = state['task_execution'].get('resolved_task_id')
    if task_id:
        sections.append(f'[Открыть задание](/executor/tasks/{task_id})')
    return '\n\n'.join(sections)
