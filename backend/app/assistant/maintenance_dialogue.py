"""Object maintenance conversation backed by authorized, repeatable reads."""
import re
from datetime import date, datetime, time, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.schemas.assistant import GoalSpec, ToolSelection

from . import workflow
from .intents import prohibits_changes
from .maintenance_subject import dates, numbered_reference, type_keys, without_types
from .read_transport import result_summary, safe_arguments
from .semantic_plan import QUOTED, UUID, asset_references
from .tools import invoke, validate_arguments


CATALOG = 'maintenance_catalog_read'
TASKS = 'tasks_find'
PREVIEW = 'assignment_preview'
CONTEXT = 'assignment_context'
ASSIGN = 'task_assign'
TITLES = {
    'types': 'Виды технического обслуживания',
    'operations': 'Операции по действующим регламентам',
    'upcoming': 'Ближайшие задания по ТО',
    'overdue': 'Просроченные задания по ТО',
    'assignees': 'Текущие исполнители работ',
    'recommendation': 'Подбор исполнителя на ТО',
    'reason': 'Обоснование подбора исполнителя',
    'backlog': 'Количество невыполненных нарядов ТО',
    'dated_tasks': 'Наряды ТО по выбранным датам',
    'assignment': 'Подготовка назначения исполнителя на ТО',
}
MAINTENANCE = r'\b(?:то|техобслуживани\w*|техническ\w*\s+обслуживани\w*|регламентн\w*\s+(?:операци\w*|работ\w*))\b'
DETAIL = r'(?:(?:а|дальше)[, ]+)?(?:конкретнее|поподробнее|подробнее|детальнее|покажи\s+вс[её]|перечисли|все\s+по\s+пунктам|по\s+пунктам|продолжи\s+список|следующ\w*\s+страниц\w*)(?:\s*[,—-]?\s*(?:вс[её]|по\s+пунктам|пожалуйста|давай))*'
REACTION = r'(?:ну\s+)?(?:долба[её]б\w*|дебил\w*|идиот\w*|ты\s+долба[её]б\w*|что\s+за\s+бред|чушь|ты\s+серь[её]зно|стоп[, ]+что[^\w]*(?:как\s+так)?)'
OVERDUE = r'(?:а\s+)?(?:какие|что|покажи|перечисли|а)?\s*(?:из\s+них\s+)?просроч\w*(?:\s+(?:то|сейчас|у\s+нас|на\s+объекте|задани\w*|работ\w*))*'
ASSIGNEES = r'(?:а\s+)?кто\s+(?:(?:их|это|эти\s+работы)\s+)?(?:выполня\w*|назначен\w*|отвеча\w*)(?:\s+(?:их|это|за\s+них|на\s+них|на\s+эти\s+работы))*'
WHO_CAN_PERFORM = r'(?:а\s+)?кто\s+(?:(?:из\s+сотрудников|их|это)\s+)?(?:может|сможет)\s+(?:(?:их|это|эти\s+операции)\s+)?(?:выполнить|сделать)(?:\s+(?:их|это|эти\s+операции))?'
REASON = r'(?:а\s+)?почему(?:\s+(?:именно\s+)?(?:он[аи]?|его|е[её]|их|они|этот\s+исполнитель|эт[ау]\s+бригад\w*))?'
PICK = r'\b(?:выбери\w*|подбер[ие]\w*|предложи\w*|посоветуй\w*|кого\s+(?:лучше|можно)|кто\s+подойд[её]т)\b'
PERSON = r'\b(?:кого|подходящ\w*|исполнител\w*|сотрудник\w*|работник\w*|бригад\w*|специалист\w*)\b'
UNFINISHED = r'\b(?:невыполн\w*|незаверш\w*|открыт\w*)\b|\bне\s+(?:выполн\w*|закры\w*|заверш\w*)\b'
ASSIGN_COMMAND = r'^(?:(?:пожалуйста|давай|тогда|ок|хорошо)[, ]+)*(?:назначь|назначьте|назанчь|поручи|поручите)\b'
CONTINUE_ASSIGNMENT = r'(?:(?:ну|так|дак|тогда|давай|а)\s+)*(?:делай|выполняй|продолжай|проверь)(?:\s+(?:е[мп]а|уже|тогда|пожалуйста))*'
CATALOG_FOLLOWUP = r'\b(?:операци\w*|разновидност\w*|детал\w*|перечисл\w*|пункт\w*)\b|\b(?:вс[её]|их)\s+\d+\b'


def _direct(source):
    maintenance = re.search(MAINTENANCE, source)
    personal = re.search(PICK, source) and re.search(PERSON, source)
    if personal and maintenance:
        return 'recommendation'
    if not maintenance:
        return None
    if re.search(r'\bпросроч\w*', source) and re.search(r'\b(?:какие|покажи|перечисли|есть\s+ли|что)\b', source):
        return 'overdue'
    if re.search(r'\b(?:ближайш\w*|предстоящ\w*|следующ\w*|завтра|сегодня)\b', source):
        if re.search(r'\b(?:когда|какие|что|покажи|найди|проверь|есть\s+ли)\b', source):
            return 'upcoming'
    if re.search(r'\b(?:какие|каких|что|перечисли|покажи|список|перечень|назови)\b', source):
        if re.search(r'\b(?:операци\w*|по\s+пунктам)\b', source):
            return 'operations'
        if re.search(r'\b(?:вид\w*|тип\w*|есть|провод\w*|выполня\w*|перечисли|покажи)\b', source):
            return 'types'
    return None


def _specific(question):
    # Let the normal planner interpret explicit equipment, named tasks and compound requests.
    return (QUOTED.search(question) or asset_references(question) or re.search(UUID, question, re.I) or
            re.search(r'[;\n]|\b(?:затем|а\s+также|и\s+(?:какие|кто|почему|посмотри|проверь|выпиши|назначь|сохрани|опубликуй|отмени)|'
                      r'сравни\w*|истори\w*|рейтин\w*|ранжир\w*|максим\w*|с\s+больш\w*\s+числ\w*)\b',
                      question, re.I))


def _previous(history, scope, clock):
    for row in history:
        if row.get('status') not in ('completed', 'failed'):
            continue
        state = row.get('workflow') or {}
        if state.get('scope') == scope and state.get('maintenance_dialogue'):
            return state['maintenance_dialogue'], False
        source = row['content'].strip().lower().rstrip('?! .')
        if re.fullmatch(DETAIL, source) or re.fullmatch(REACTION, source) or re.fullmatch(CONTINUE_ASSIGNMENT, source):
            continue
        if not state and not _specific(without_types(source)):
            created = row.get('created_at')
            prior_clock = {**clock, 'local_date': created.astimezone(ZoneInfo(clock['timezone'])).date().isoformat()} if created else clock
            if (intent := _assignment_request(source, prior_clock)) and (created or not intent['day']):
                return dict(intent, command_turn_id=str(row['turn_id'])), True
        if keys := type_keys(source):
            return dict(kind='operations', type_keys=keys), True
        direct = _direct(source) if not _specific(source) else None
        return (dict(kind=direct), True) if direct else (None, False)
    return None, False


def _day(source, clock):
    today = date.fromisoformat(clock['local_date'])
    if re.search(r'\bзавтра\b', source):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r'\bсегодня\b', source):
        return today.isoformat()
    return None


def _assignment_request(source, clock):
    keys = type_keys(source)
    if not (re.search(ASSIGN_COMMAND, source) and not prohibits_changes(source) and (keys or re.search(MAINTENANCE, source)) and
            re.search(PERSON, source) and re.search(r'\b(?:свободн\w*|без\s+исполнител\w*)\b', source)):
        return None
    individual = bool(re.search(r'\b(?:сотрудника|исполнителя|работника|специалиста)\b', source))
    return dict(kind='assignment', day=_day(source, clock), type_keys=keys, individual=individual)


def _ground_interpretation(source, interpretation):
    registry = bool(re.search(r'\b(?:предусмотр\w*|реестр\w*|перечень|зарегистрирован\w*|записан\w*|список)\b', source))
    if interpretation == 'upcoming' and not re.search(
            r'\b(?:когда|план\w*|будет|скоро|сегодня|завтра|ближайш\w*|предстоящ\w*|следующ\w*)\b', source):
        return 'operations' if registry else 'other'
    if interpretation == 'overdue' and not re.search(r'\b(?:просроч\w*|задерж\w*|пропущ\w*|пропуст\w*)\b', source):
        return 'other'
    if interpretation == 'recommendation' and not re.search(r'\b(?:кто|кому|кого|подбер\w*|предлож\w*|выбер\w*)\b', source):
        return 'other'
    if interpretation == 'other' and registry and re.search(MAINTENANCE, source):
        return 'operations'
    return interpretation


def request(question, history, scope, clock, *, interpretation=None):
    source = ' '.join(question.casefold().split()).rstrip('?! .\\')
    # Guides and conceptual questions do not ask for a site dataset.
    if re.match(r'^(?:как\s+(?:посмотреть|узнать|найти|создать)|что\s+такое|зачем|объясни\s+разницу)\b', source) or re.search(
            r'\b(?:в\s+целом|обычно|вообще|как\s+правило|в\s+промышленности)\b', source):
        return None
    keys = type_keys(QUOTED.sub(' ', source))
    if _specific(without_types(question) if keys else question):
        return None
    prior, missed = _previous(history, scope, clock)
    maintenance = bool(keys or re.search(MAINTENANCE, source))
    unfinished = bool(re.search(UNFINISHED, source))
    assignment = bool(re.search(ASSIGN_COMMAND, source))
    if intent := _assignment_request(source, clock):
        return intent
    if prior and prior['kind'] == 'assignment' and re.fullmatch(CONTINUE_ASSIGNMENT, source):
        return dict(prior, acknowledge=None)
    if maintenance or prior and prior['kind'] in ('backlog', 'dated_tasks'):
        selected = dates(source, clock['local_date'])
        if selected is None or selected:
            if prior or selected is None or re.search(r'\b(?:напиши|перечисли|покажи|какие|сколько|найди)\b', source):
                return dict(kind='dated_tasks', days=selected, type_keys=keys or (prior or {}).get('type_keys', []),
                            unfinished=unfinished or bool(prior and (prior['kind'] == 'backlog' or prior.get('unfinished'))))
    if maintenance and unfinished and re.search(r'\b(?:сколько|число|количество)\b', source):
        return dict(kind='backlog', type_keys=keys, unfinished=True)
    if keys and not assignment and not re.search(PICK, source):
        return dict(kind='operations', type_keys=keys)
    if prior and prior['kind'] in ('types', 'operations') and (index := numbered_reference(source)) is not None:
        rows = prior.get('listed_types') or []
        if 1 <= index <= len(rows):
            return dict(kind='operations', type_codes=[rows[index-1]['type_code']], listed_types=rows)
        return dict(kind='operations', unknown_index=index, listed_types=rows)
    kind = _direct(source)
    if kind:
        return dict(kind=kind, day=_day(source, clock))
    if interpretation:
        interpretation = _ground_interpretation(source, interpretation)
    if not prior:
        return (dict(kind=interpretation, day=_day(source, clock)) if interpretation in ('types', 'operations',
                'upcoming', 'overdue', 'assignees', 'recommendation') and re.search(MAINTENANCE, source) else None)
    if re.fullmatch(REACTION, source):
        if prior['kind'] == 'assignment':
            return None
        return {**prior, 'acknowledge': 'missed' if missed else 'recheck'}
    if re.fullmatch(DETAIL, source) or prior['kind'] in ('types', 'operations') and re.search(CATALOG_FOLLOWUP, source):
        if prior['kind'] in ('types', 'operations'):
            offset = prior.get('next_offset', 0) if re.search(r'следующ|продолжи', source) else 0
            return {**prior, 'kind': 'operations', 'offset': offset or 0, 'acknowledge': None}
        offset = prior.get('next_offset', 0) if re.search(r'следующ|продолжи', source) else 0
        return {**prior, 'offset': offset or 0, 'acknowledge': None}
    if re.fullmatch(OVERDUE, source):
        return dict(kind='overdue')
    if prior['kind'] == 'operations' and 'unknown_index' not in prior and re.fullmatch(WHO_CAN_PERFORM, source):
        return dict(kind='recommendation', type_keys=prior.get('type_keys', []), type_codes=prior.get('type_codes', []),
                    catalog_reference=True)
    if re.fullmatch(ASSIGNEES, source) and prior['kind'] in ('overdue', 'upcoming', 'assignees', 'recommendation', 'reason'):
        return dict(kind='assignees', period=prior.get('period', 'upcoming'), day=prior.get('day'), task_id=prior.get('task_id'))
    if re.fullmatch(REASON, source) and prior['kind'] in ('recommendation', 'reason'):
        return {**prior, 'kind': 'reason', 'acknowledge': None}
    if re.search(PICK, source) and re.search(PERSON, source):
        return dict(kind='recommendation', day=_day(source, clock),
                    task_id=prior.get('task_id') if re.search(r'\b(?:него|не[её]|ту|это|эту|этот)\b', source) else None)
    if interpretation == 'reason' and prior['kind'] in ('recommendation', 'reason'):
        return {**prior, 'kind': 'reason', 'acknowledge': None}
    if interpretation == 'assignees' and prior['kind'] in ('overdue', 'upcoming', 'assignees'):
        return dict(kind='assignees', period=prior.get('period', 'upcoming'), day=prior.get('day'))
    if interpretation == 'operations' and prior['kind'] in ('types', 'operations'):
        return dict(kind='operations')
    if interpretation in ('upcoming', 'overdue', 'recommendation'):
        return dict(kind=interpretation, day=_day(source, clock))
    return None


def make_plan(intent, question, tools, scope, root_turn_id):
    kind = intent['kind']
    change = kind == 'assignment'
    name = (ASSIGN if change else CATALOG if kind in ('types', 'operations') else PREVIEW if kind in ('recommendation', 'reason')
            and PREVIEW in tools else 'task_read' if kind == 'assignees' and intent.get('task_id') else TASKS)
    goal = GoalSpec(id='maintenance-dialogue', title=TITLES[kind], tool=name,
                    kind='change' if change else 'read', required_evidence='saved_data')
    state = workflow.create_plan(ToolSelection(tools=[name], goals=[goal]), question, tools, scope)
    state.update(maintenance_dialogue=intent, read_only=not change, display_plan=False,
                 root_turn_id=intent.get('command_turn_id') or str(root_turn_id))
    if change:
        intent.setdefault('command_turn_id', str(root_turn_id))
    return state


class Source:
    def __init__(self, execution, goal):
        self.execution = execution
        self.goal = goal

    async def read(self, name, args, *, retain=lambda value: value, record=True):
        from . import service
        e = self.execution
        e.check()
        if e.calls_used >= service.MAX_TOOL_CALLS:
            raise HTTPException(413, 'Лимит чтения за один ответ')
        tool = e.tools.get(name)
        if not tool or tool.mode != 'read':
            raise HTTPException(403, 'Источник недоступен текущей роли')
        service.progress(e.app, e.turn_id, e.trace, name)
        start = monotonic()
        e.calls_used += 1
        try:
            checked = validate_arguments(e.app, tool, args)
            value = await invoke(e.app, tool, checked, e.headers)
            if not isinstance(value, dict):
                raise HTTPException(502, 'Ответ источника не получен')
        except HTTPException as exc:
            workflow.record_read_failure(e.state, self.goal, name, args, exc.status_code, elapsed=monotonic()-start)
            e.trace.append(dict(tool=name, status='denied', code=exc.status_code, at=workflow.timestamp()))
            raise
        entry = dict(tool=name, status='completed', result=result_summary(value), arguments=safe_arguments(checked), at=workflow.timestamp())
        if fact := service.progress_fact(name, value):
            if self.execution.state['maintenance_dialogue']['kind'] in ('types', 'backlog'):
                fact.pop('shown', None)
            entry['fact'] = fact
        e.trace.append(entry)
        if record:
            self.retain(name, checked, retain(value), elapsed=monotonic()-start)
        else:
            e.state['metrics']['tool_calls'] += 1
            e.state['metrics']['tool_seconds'] += round(monotonic()-start, 4)
        return value

    def retain(self, name, args, value, **kwargs):
        return workflow.record_result(self.execution.state, self.goal, name, args, value, **kwargs)


def _line(value):
    from .inventory_report import label
    return label(' '.join(str(value).split()))


async def _catalog(source, intent):
    if 'unknown_index' in intent:
        source.goal.update(status='blocked', reason='type_reference_unverified')
        return 'Не нашёл такого пункта в предыдущем списке видов ТО. Укажите название вида или попросите показать список ещё раз.'
    offset = intent.get('offset', 0)
    details = intent['kind'] == 'operations'
    page_size = 50 if details else 1
    query = dict(offset=offset, limit=page_size)
    if intent.get('type_keys'):
        query['type_keys'] = intent['type_keys']
    if intent.get('type_codes'):
        query['type_codes'] = intent['type_codes']
    args = dict(query=query)
    first = await source.read(CATALOG, args, record=False)
    summary = {key: first[key] for key in ('date', 'total', 'types', 'snapshot_id', 'type_keys', 'type_codes')}
    if not details:
        intent['listed_types'] = first['types']
        source.retain(CATALOG, args, summary, count_call=False)
        if not first['types']:
            return 'В доступном реестре оборудования нет действующих утверждённых операций ТО.'
        lines = [f'Действующие виды ТО на {first["date"]}:']
        for item in first['types']:
            lines.append(f'{len(lines)}. {_line(item["type_name"])} — операций: {item["operations"]}.')
        return '\n\n'.join([lines[0], '\n'.join(lines[1:]), 'Источник — действующие регламенты оборудования.'])

    rows = list(first['items'])
    while offset + len(rows) < first['total'] and len(rows) < 150:
        page = await source.read(CATALOG, dict(query={**query, 'offset': offset + len(rows)}), record=False)
        if page['snapshot_id'] != first['snapshot_id'] or not page['items']:
            raise HTTPException(409, 'Реестр ТО изменился во время чтения')
        rows.extend(page['items'])
    # Keep both a practical chat page and the verified registry total.
    lines = []
    length = 0
    for item in rows:
        value = f'{offset + len(lines) + 1}. {_line(item["type_name"])} · {_line(item["code"])} — {_line(item["title"])}'
        if length + len(value) > 11000 and lines:
            break
        lines.append(value)
        length += len(value) + 1
    next_offset = offset + len(lines)
    intent['next_offset'] = next_offset if next_offset < first['total'] else None
    source.retain(CATALOG, args, dict(**summary, operations=rows[:len(lines)], offset=offset,
                                    complete=intent['next_offset'] is None and offset == 0), count_call=False)
    if not lines:
        if not first['total'] and intent.get('type_keys'):
            kinds = ', '.join(key.upper() for key in intent['type_keys'])
            return f'На {first["date"]} в доступных регламентах объекта нет действующих операций для {kinds}.'
        return ('Следующих операций на этой странице нет. Начало перечня доступно по запросу «Покажи все».' if first['total']
                else 'В доступном реестре оборудования нет действующих утверждённых операций ТО.')
    rest = f'\n\nПоказано до пункта {next_offset} из {first["total"]}. Следующие пункты доступны по запросу «Дальше, следующая страница».' if intent['next_offset'] else ''
    types = (', '.join(_line(item['type_name']) for item in first['types'])
             if intent.get('type_keys') or intent.get('type_codes') else '')
    headline = f'{types} · операций: {first["total"]}' if types else f'Всего операций: {first["total"]}'
    return headline + '\n\n' + '\n'.join(lines) + rest + '\n\nИсточник — действующие регламенты оборудования.'


def _task_fact(item):
    fields = ('id', 'title', 'equipmentName', 'scheduledStart', 'scheduledEnd', 'mandatoryDueDate',
              'regulatoryDeadlineAt', 'assignees', 'isOverdue', 'revision', 'matchedDay', 'state')
    return {key: item[key] for key in fields if key in item}


def _task_facts(value):
    return {**value, 'items': [_task_fact(item) for item in value['items']]}


def _task_detail(value):
    return {'task': _task_fact(value['task'])}


def _task_line(task, *, people=False):
    title = _line(task['title'])
    equipment = _line(task['equipmentName'])
    timing = (f'плановое начало {task["scheduledStart"][:16].replace("T", " ")}' if task.get('scheduledStart')
              else f'нормативный срок {task["mandatoryDueDate"]}' if task.get('mandatoryDueDate') else 'дата не указана')
    text = f'{title} · {equipment} · {timing} · наряд {task["id"]}'
    if task.get('isOverdue') and task.get('regulatoryDeadlineAt'):
        text += ' · просрочено, нормативный срок ' + task['regulatoryDeadlineAt'][:16].replace('T', ' ')
    if people:
        names = ', '.join(_line(item['name']) for item in task['assignees'])
        text += f' · {names or "исполнитель не назначен"}'
    return text


async def _tasks(source, intent, *, nearest=False):
    period = intent.get('period') or ('overdue' if intent['kind'] == 'overdue' else 'upcoming')
    intent['period'] = period
    query = dict(period=period, limit=1 if nearest else 25, maintenance_only=True)
    if not nearest and intent.get('offset'):
        query['offset'] = intent['offset']
    if period == 'overdue':
        query['unfinished_only'] = True
    if day := intent.get('day'):
        query.update(starts_on=day, ends_on=day)
    if intent.get('type_keys'):
        query['type_keys'] = intent['type_keys']
    if intent.get('type_codes'):
        query['type_codes'] = intent['type_codes']
    return await source.read(TASKS, dict(query=query), retain=_task_facts)


async def _assignments(source, intent):
    if intent.get('task_id'):
        task = await source.read('task_read', dict(path=dict(task_id=intent['task_id'])), retain=_task_detail)
        return 'Сохранённое назначение · ' + _task_line(task['task'], people=True)
    value = await _tasks(source, intent)
    if not value['items']:
        return ('Следующих работ на этой странице нет.' if value['total'] else
                'В доступных нарядах по ТО за выбранный период подходящих работ нет.')
    first = value['offset']
    last = first + len(value['items'])
    intent['next_offset'] = last if last < value['total'] else None
    lines = [f'Наряды по ТО · найдено {value["total"]}.']
    lines += [f'{i}. {_task_line(task, people=intent["kind"] == "assignees")}' for i, task in enumerate(value['items'], first+1)]
    if intent['next_offset']:
        lines.append(f'Показано до пункта {last} из {value["total"]}. Следующие наряды доступны по запросу «Следующая страница».')
    lines.append('Источник — наряды текущего объекта, доступные вашей роли.')
    return '\n'.join(lines)


WORK_STATUS = {'draft': 'черновик', 'assigned': 'назначено', 'clarification': 'требует уточнения',
               'rework': 'на доработке', 'in_progress': 'в работе', 'in_review': 'на приёмке'}


async def _backlog(source, intent):
    query = dict(period='all', maintenance_only=True, unfinished_only=True, limit=1)
    if intent.get('type_keys'):
        query['type_keys'] = intent['type_keys']
    args = dict(query=query)
    value = await source.read(TASKS, args, retain=lambda result: {
        key: result[key] for key in ('total', 'timezone', 'checked_at', 'filters')})
    local = datetime.fromisoformat(value['checked_at'])
    local = local.astimezone(ZoneInfo(value['timezone']))
    states = ', '.join(WORK_STATUS[state] for state in value['filters']['states'])
    kind = ' · ' + ', '.join(key.upper() for key in intent['type_keys']) if intent.get('type_keys') else ''
    return (f'Невыполненных нарядов ТО{kind} — **{value["total"]}** на {local:%d.%m.%Y %H:%M} '
            f'({value["timezone"]}).\n\nУчтены доступные вам наряды с регламентом на текущем объекте '
            f'в состояниях «{states}». Источник — реестр нарядов.')


async def _dated_tasks(source, intent):
    days = intent.get('days')
    if not days or len(days) > 31:
        source.goal.update(status='blocked', reason='date_selection_unverified')
        return 'Не удалось определить даты. Укажите существующие дни с месяцем и годом, не более 31 дня за запрос.'
    query = dict(period='all', maintenance_only=True, unfinished_only=bool(intent.get('unfinished')),
                 active_only=False, on_days=days, offset=intent.get('offset', 0), limit=50)
    if intent.get('type_keys'):
        query['type_keys'] = intent['type_keys']
    data = await source.read(TASKS, dict(query=query), retain=_task_facts)
    label = 'Невыполненные наряды ТО' if intent.get('unfinished') else 'Наряды ТО'
    lines = [f'{label} на текущем объекте · всего {data["total"]}.']
    for day in days:
        count = data['day_counts'].get(day, 0)
        rows = [item for item in data['items'] if item['matchedDay'] == day]
        lines.append(f'**{day}** · {count}')
        lines.extend('- ' + _task_line(item) for item in rows)
    shown = data['offset'] + len(data['items'])
    intent['next_offset'] = shown if shown < data['total'] else None
    if intent['next_offset']:
        lines.append(f'Показано до пункта {shown} из {data["total"]}. Скажите «Следующая страница», чтобы увидеть остальные наряды.')
    lines.append('Источник — реестр нарядов. День определяется по плановому началу, а если оно не задано, по нормативному сроку.')
    return '\n\n'.join(lines)


def _window(context, task, day):
    if task.get('scheduledStart') and task.get('scheduledEnd'):
        return tuple(datetime.fromisoformat(task[key]).replace(tzinfo=None).isoformat()
                     for key in ('scheduledStart', 'scheduledEnd'))
    if day:
        start = datetime.combine(date.fromisoformat(day), time.min)
        return start.isoformat(), (start + timedelta(days=1)).isoformat()
    return context['defaultStartLocal'], context['defaultEndLocal']


def _preview_facts(value):
    return {key: value[key] for key in ('status', 'code', 'explanation', 'selectedWorkers', 'startAt', 'endAt', 'crewName')}


async def _recommend(source, intent):
    if task_id := intent.get('task_id'):
        detail = await source.read('task_read', dict(path=dict(task_id=task_id)), retain=_task_detail)
        task = detail['task']
    else:
        upcoming = await _tasks(source, intent, nearest=True)
        task = next(iter(upcoming['items']), None)
        if not task:
            source.goal.update(status='blocked', reason='no_matching_maintenance_order')
            if intent.get('catalog_reference'):
                return ('Ближайших доступных нарядов по выбранным операциям ТО не найдено. '
                        'Для проверки исполнителей укажите наряд и время работ.')
            return 'В проверенном периоде нет ближайшего доступного наряда по ТО. Подбирать исполнителя пока не к чему.'
        intent['task_id'] = task['id']
    header = 'Проверенный наряд · ' + _task_line(task)
    if PREVIEW not in source.execution.tools:
        source.goal.update(status='blocked', reason='assignment_permission_required')
        return header + '\n\nПодбор по допускам, сменам и загрузке недоступен вашей роли.'
    path = dict(task_id=task['id'])
    context = await source.read(CONTEXT, dict(path=path))
    if context['expectedRevision'] != task['revision']:
        raise HTTPException(409, 'Наряд изменился между чтением и расчётом')
    if context['status'] != 'ready':
        source.goal.update(status='blocked', reason='assignment_context_unavailable')
        return header + '\n\nПодбор ограничен: ' + context['explanation']
    start, end = _window(context, task, intent.get('day'))
    value = await source.read(PREVIEW, dict(path=path, body=dict(expected_revision=context['expectedRevision'],
                                                               start_local=start, end_local=end)), retain=_preview_facts)
    if value['status'] != 'ok' or not value['selectedWorkers']:
        source.goal.update(status='blocked', reason='assignment_candidate_unavailable')
        return header + '\n\nПодходящий состав не подтверждён. ' + value['explanation']
    selected = value['selectedWorkers']
    ids = [worker['executorId'] for worker in selected]
    changed = intent['kind'] == 'reason' and intent.get('worker_ids') and ids != intent['worker_ids']
    intent['worker_ids'] = ids
    start = datetime.fromisoformat(value['startAt']).strftime('%d.%m.%Y %H:%M')
    end = datetime.fromisoformat(value['endAt']).strftime('%d.%m.%Y %H:%M')
    names = ', '.join(_line(worker['name']) for worker in selected)
    lines = [header, 'Подбор изменился после актуальной проверки.' if changed else '',
             f'Рекомендация · {names}, {start} — {end} ({context["timezone"]}).']
    skills = ', '.join(_line(skill) for skill in context['requiredQualifications'])
    lines.append('Проверены допуски' + (f' ({skills})' if skills else '') + ', смена, пересечения с другими работами и загрузка.')
    if intent['kind'] == 'reason':
        lines.append('Штатный подбор сначала ищет самое раннее время для полного состава. При равном времени учитывает меньшую загрузку.')
    for worker in selected:
        load = worker['loadMinutes']
        if load is not None:
            lines.append(f'{_line(worker["name"])} · учтённая загрузка {load} мин.')
    if intent.get('catalog_reference') and intent['kind'] != 'reason':
        source.goal.update(status='partial', reason='specific_order_required_for_other_operations')
        lines.append('Подбор относится к этому наряду. Для остальных операций укажите наряды или время работ.')
    lines.append('Назначение в системе не изменилось. Источник — расчёт состава по актуальным данным наряда и команды.')
    return '\n\n'.join(filter(None, lines))


async def execute(execution, goal):
    intent = execution.state['maintenance_dialogue']
    source = Source(execution, goal)
    try:
        if intent['kind'] in ('types', 'operations'):
            answer = await _catalog(source, intent)
        elif intent['kind'] == 'backlog':
            answer = await _backlog(source, intent)
        elif intent['kind'] == 'dated_tasks':
            answer = await _dated_tasks(source, intent)
        elif intent['kind'] == 'assignment':
            from .maintenance_assignment import prepare
            answer = await prepare(source, intent)
        elif intent['kind'] in ('recommendation', 'reason'):
            answer = await _recommend(source, intent)
        else:
            answer = await _assignments(source, intent)
    except HTTPException as exc:
        goal.update(status='blocked', reason=f'maintenance_source_{exc.status_code}')
        answer = ('Источник недоступен в текущей роли или на выбранном объекте.' if exc.status_code in (401, 403, 404)
                  else 'Не удалось получить согласованные данные из источника. Повторите запрос или уточните период.')
    if intent.get('acknowledge'):
        intro = ('Пропустил проверку по данным объекта. Исправляю.' if intent['acknowledge'] == 'missed'
                 else 'Перепроверил по данным объекта.')
        answer = intro + '\n\n' + answer
    goal.update(response=answer, response_source='server_workflow')
    workflow.update_outcome(execution.state)
