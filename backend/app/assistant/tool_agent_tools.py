"""Small typed maintenance vocabulary over the authenticated capability registry."""
import re
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, ValidationError, WithJsonSchema, model_validator
from sqlalchemy import text

from app.schemas.assistant import ReportAttachAndSubmit
from . import service
from .attachments import MAX_FILE, jpeg_input
from .inventory_report import label
from .report_target import TARGET_REQUIRED, named_order_references, resolve_report_target
from .tool_agent import Observation
from .tools import available, invoke, validate_arguments


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


RelativeDay = Literal['today', 'tomorrow', 'yesterday', 'day_after_tomorrow']
DAY_SHIFTS = {'yesterday': -1, 'today': 0, 'tomorrow': 1, 'day_after_tomorrow': 2}


class WorkOrders(Arguments):
    period: Literal['all', 'upcoming', 'overdue', 'undated'] = 'all'
    state: Literal['draft', 'assigned', 'clarification', 'rework', 'in_progress', 'in_review', 'completed', 'cancelled'] | None = Field(
        default=None, description='Точный статус; очередь ожидающих приёмки — in_review, не attention_only.')
    unfinished_only: bool = False
    unassigned_only: bool = False
    attention_only: bool = False
    maintenance_only: bool = Field(default=False,
        description='Только наряды, привязанные к правилу ТО. Не включайте для общей сводки, плана действий или просрочек без запроса исключить другие работы.')
    relative_day: RelativeDay | None = Field(
        default=None, description='День по серверным часам объекта: сегодня, завтра, вчера, послезавтра. Без явных дат.')
    day_offset_from_last_selection: int | None = Field(
        default=None, ge=-31, le=31, description='Сдвиг от дня последней выборки: -1 предыдущий, 0 тот же, 1 следующий.')
    on_date: date | None = Field(default=None, description='Ровно один день, YYYY-MM-DD')
    starts_on: date | None = Field(default=None, description='Первый включённый день многодневного диапазона, требуется ends_on')
    ends_on: date | None = Field(default=None, description='Последний включённый день многодневного диапазона, требуется starts_on')
    equipment_id: UUID | None = None
    equipment_asset_code: str | None = Field(default=None, max_length=128)
    q: str = Field(default='', max_length=200, description='Буквальная подстрока названия, метки или кода операции. Для именованного блока в заголовках передайте его имя и сохраняйте фильтр при уточнении. Не передавайте полный вопрос.')
    sort: Literal['earliest', 'latest', 'earliest_deadline'] = Field(default='earliest',
        description='earliest_deadline — по обязательному сроку (без срока в конце); не меняет фильтры по плановым датам.')
    presentation: Literal['schedule'] | None = Field(default=None,
        description='schedule — готовая таблица только за один явно указанный плановый день (period=all). Без диапазона, дополнительных вопросов, чтений или действий.')
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=8, ge=1, le=15)

    @model_validator(mode='after')
    def date_range(self):
        if self.day_offset_from_last_selection is not None and any(value is not None for value in
                (self.relative_day, self.on_date, self.starts_on, self.ends_on)):
            raise ValueError('Combining relative and explicit day reference is not allowed')
        if self.relative_day is not None and any(day is not None for day in (self.on_date, self.starts_on, self.ends_on)):
            raise ValueError('relative_day cannot be combined with explicit dates')
        if (self.starts_on is None) != (self.ends_on is None):
            raise ValueError('A date range needs both endpoints; use on_date for a single day')
        if self.starts_on is not None and (self.on_date is not None or self.starts_on > self.ends_on):
            raise ValueError('Use exactly one chronological interval or on_date')
        return self


class WorkOrder(Arguments):
    task_id: UUID

class ProposedReport(ReportAttachAndSubmit):
    task_id: UUID


class ReportPhotos(WorkOrder):
    phases: list[Literal['before', 'after']] = Field(default_factory=lambda: ['before', 'after'], min_length=1, max_length=2)
    compare_with_attachment: bool = Field(default=False, description='Только если пользователь явно просит сопоставить сообщение со снимками отчёта.')


class AcceptanceReadiness(WorkOrder):
    expected_revision: int = Field(ge=1)
    execution_id: UUID | None = None


class Equipment(Arguments):
    equipment_id: UUID


class EquipmentSearch(Arguments):
    q: str = Field(default='', max_length=200)
    asset_code: str | None = Field(default=None, max_length=128)
    offset: int = Field(default=0, ge=0, le=10000)


class Calendar(Arguments):
    starts_on: date
    ends_on: date
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=8, ge=1, le=15)


class CalculatedDates(Equipment):
    starts_on: date
    ends_on: date


LocalDateTime = Annotated[NaiveDatetime, WithJsonSchema({'type': 'string'})]
LocalClock = Annotated[time, WithJsonSchema({'type': 'string'})]


class Assignment(WorkOrder):
    executor_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20,
        description='Только если нужен конкретный полный состав. Иначе сервер подбирает автоматически.')
    start_local: LocalDateTime | None = Field(default=None,
        description='Начало точно заданного пользователем окна, YYYY-MM-DDTHH:MM без смещения UTC, вместе с end_local. Не подставляйте часы по словам «утром» или «днём».')
    end_local: LocalDateTime | None = Field(default=None,
        description='Конец того же окна, YYYY-MM-DDTHH:MM, без смещения UTC.')


class WorkforceLoad(Arguments):
    day: date | None = Field(default=None, description='Точная календарная дата объекта.')
    relative_day: RelativeDay | None = Field(default=None, description='День относительно серверных часов объекта.')
    window_start: LocalClock | None = Field(default=None, description='Начало по часам объекта, HH:MM без Z и смещения UTC. Вместе с window_end.')
    window_end: LocalClock | None = Field(default=None, description='Конец по часам объекта, HH:MM без Z и смещения UTC.')
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=12, ge=1, le=15)

    @model_validator(mode='after')
    def day_source(self):
        if (self.day is None) == (self.relative_day is None):
            raise ValueError('Use exactly one of day and relative_day')
        return self


class WorkOrderAnalysis(Arguments):
    starts_on: date | None = Field(default=None, description='Первый день интересующего периода по местному времени.')
    ends_on: date | None = Field(default=None, description='Последний включённый день интересующего периода.')
    cohort: Literal['unfinished', 'execution_pending', 'in_review'] = 'unfinished'


class ProposedAssignment(Assignment):
    reason: str = Field(min_length=1, max_length=500, description='Краткая причина именно этого назначения.')


class Workbook(Arguments):
    attachment_id: UUID
    sheet: str | None = Field(default=None, max_length=255)
    offset: int = Field(default=0, ge=0, le=1048576)


# Public model vocabulary; transport names and write command bodies are never model-selected.
COMMON = {
    'find_work_orders': (WorkOrders, 'Найти наряды. Для «сегодня» и «завтра» используйте relative_day и period=all; '
                          'on_date — только для конкретной календарной даты. Фильтры пересекаются. '
                          'Поиск за всё время без фильтров сразу даёт общий итог, статистику статусов и число работ сегодня. '
                         'Дата — сохранённая плановая дата; для overdue — обязательный срок. '
                         'Для ближайшего ТО: period=upcoming, maintenance_only=true, unfinished_only=true, sort=earliest. '
                          'attention_only: просрочено, нет назначенного состава, на уточнении или доработке; '
                          'не заменяет состояние in_review. Без q или equipment_* охват не ограничен именованным блоком.'),
    'read_work_order': (WorkOrder, 'Свежая карточка указанного наряда, применённые инструкции, чек-лист, отчёт, замечания и список материалов.'),
    'find_equipment': (EquipmentSearch, 'Поиск доступного оборудования по подстроке названия, кода или места либо точному инвентарному коду.'),
    'read_equipment': (Equipment, 'Паспортные поля, место, состояние и реквизиты оборудования. '
                       'Для инженера также последнее подтверждённое обслуживание этой единицы.'),
    'read_regulations': (Equipment, 'Настройки регламентов и чек-листы оборудования. Сейчас действуют только строки '
                         'с effective_status=active. publication_status=published не означает, что дата уже наступила.'),
    'read_equipment_service_history': (Equipment, 'Последнее подтверждённое обслуживание по принятому отчёту. '
                                       'Не подменяет дату выполнения датой сдачи, приёмки или плана.'),
    'check_acceptance_readiness': (AcceptanceReadiness, 'Прочитать комплектность и препятствия приёмке или сдаче '
                                   'актуальной попытки. Передать ревизию и идентификатор из свежей карточки. Без записи.'),
    'find_calendar_events': (Calendar, 'Запланированные календарные события ТО, включая события без сформированного наряда. '
                             'Включённые даты объекта, не более 92 дней; по плановой дате от раннего к позднему.'),
    'calculate_due_dates': (CalculatedDates, 'Расчёт дат ТО по утверждённым привязкам конкретного оборудования, а не реальные наряды.'),
    'read_report_photos': (ReportPhotos, 'Получить архивные снимки последней попытки наряда, до двух на фазу. '
                            'Не используйте для оценки приложенного кадра, если не попросили сопоставить источники.'),
    'read_workbook': (Workbook, 'Без записи прочитать страницу строк личного XLSX, отправленного в текущем сообщении.'),
}
ENGINEER = {
    'read_work_order_analysis': (WorkOrderAnalysis, 'Обзор всего объекта или его состояний за выбранный период. '
                                'Не фильтрует конкретный блок/зону/оборудование. Для именованной части используйте find_work_orders.'),
    'read_workforce_load': (WorkforceLoad, 'Загрузка всей команды за день и свободно ли конкретное окно. '
                            'Ноль подтверждённых минут и неизвестная загрузка различаются; допуски не проверяются.'),
    'check_assignment': (Assignment, 'Рассчитать полный состав на плановую дату наряда без записи. Передавайте '
                          'start_local и end_local только для точно заданного окна. Проверяются смены, пересечения, допуски и нагрузка.'),
    'propose_assignment': (ProposedAssignment, 'Подготовить карточку назначения на сохранённую дату. Если время было проверено '
                            'по запросу, передайте те же start_local и end_local. Только по просьбе изменить наряд; запись после подтверждения.'),
}

ORDER_FIELDS = (
    'id', 'code', 'title', 'summary', 'equipmentIds', 'equipmentName', 'scheduledStart', 'scheduledEnd', 'plannedDate',
    'mandatoryDueDate', 'mandatoryDeadlineAt', 'plannedWindowEnded', 'deadlineRemainingMinutes',
    'matchedAt', 'state', 'rawStatus', 'priority', 'createdBy', 'assignees', 'isOverdue',
    'overdueSince', 'attentionReasons', 'durationMinutes', 'maintenanceType', 'lateAcceptanceBlocked',
)


def _page_for_model(value, budget):
    page = service.bounded(value)
    items = page['items']
    for count in range(len(items), 0 if items else -1, -1):
        end = page['offset'] + count
        result = dict(page, items=items[:count], page_complete=page['offset'] == 0 and end == page['total'],
                      next_offset=end if count and end < page['total'] else None)
        if len(service.dump(result)) <= budget:
            return result
    raise HTTPException(413, 'Строка не помещается в выдачу. Откройте карточку или уточните поиск.')


_SCHEDULE_STATES = dict(draft='Черновик', assigned='Назначен', clarification='На уточнении', in_progress='В работе',
                        in_review='На проверке', rework='На доработке', completed='Завершён', cancelled='Отменён')
_MARKDOWN_LITERAL = str.maketrans({ch: '\\'+ch for ch in '\\[]*_~'})


def _schedule_answer(page):
    def cell(value):
        return escape(label(value), quote=False).translate(_MARKDOWN_LITERAL)

    items, total = page['items'], page['total']
    if not total:
        return 'В доступных вам нарядах по этим условиям ничего не найдено.'
    if not items:
        return f'В выборке {total} нарядов. На запрошенной странице строк нет.'
    lines = [f'В выборке: {total}.' if page['page_complete'] else f'Показано {len(items)} из {total} нарядов.']
    if query := page['filters'].get('q'):
        lines.append(f'Поиск по названию, метке или коду операции: «{cell(query)}».')
    lines += ['', '| Наряд | Оборудование | Плановая дата | Плановое время | Состояние |',
              '| --- | --- | --- | --- | --- |']
    for row in items:
        day = date.fromisoformat(row['plannedDate']).strftime('%d.%m.%Y') if row.get('plannedDate') else 'Не задана'
        start = datetime.fromisoformat(row['scheduledStart']) if row.get('scheduledStart') else None
        end = datetime.fromisoformat(row['scheduledEnd']) if row.get('scheduledEnd') else None
        times = start.strftime('%H:%M') if start else 'Начало не задано'
        if end:
            times += ' — ' + end.strftime('%H:%M' if start and start.date() == end.date() else '%d.%m.%Y %H:%M')
        elif start:
            times += '; Окончание не задано'
        state = _SCHEDULE_STATES.get(row['rawStatus'], 'Не уточнено')
        lines.append(f"| {cell(row['title'])} | {cell(row['equipmentName'])} | {day} | {times} | {state} |")
    return '\n'.join(lines)


def _same_assignment(before, after):
    def comparable(body):
        return {**{key: value for key, value in body.items() if key not in ('reason', 'executor_ids')},
                'executor_ids': sorted(body['executor_ids'])}
    return comparable(before) == comparable(after)


_PHASES = {'до':'before', 'после':'after'}
_PHOTO_SOURCE_WORDS = {'фото', 'снимок', 'кадр', 'скриншот'}
_FILENAME_PHASES = {**_PHASES, 'before':'before', 'after':'after'}
_ATTACH_AND_SUBMIT = re.compile(
    r'(?:вот результат работы[,.]\s*)?(?:пожалуйста,\s*)?'
    r'(?:добавь(?:те)?|прикрепи(?:те)?)(?: (?:эти )?(?:фото|снимки|кадры))? (?:в|к) (?:его )?отч[её]ту?'
    r'(?:,?\s+(?:и|затем)) (?:сдай(?:те)?(?: (?:работу|отч[её]т))?'
    r'|отправь(?:те)?(?: отч[её]т| его)? (?:на проверку|инженеру))'
    r'(?:\. у меня несколько открытых нарядов)?[.!]?'
)


def _report_command(question, *, general_chat):
    if general_chat:
        names = named_order_references(question)
        if names and not question[:names[0].start()].strip():
            question = question[names[-1].end():].lstrip(' \r\n\t.,:—-')
    return _ATTACH_AND_SUBMIT.fullmatch(' '.join(question.casefold().split()))


def _photo_labels(question, allow_single):
    """Accept only explicit labels, e.g. «фото 1 — до; фото 2 — после»."""
    clauses = question.casefold().translate(str.maketrans('.,:;!?', '\n'*6)).splitlines()
    values = {}
    for clause in clauses:
        words = clause.translate(str.maketrans({symbol:' ' for symbol in '—–()[]"«»'})).split()
        if words[-1:] == ['работы']:
            words.pop()
        if not words or words[-1] not in _PHASES:
            continue
        phase = _PHASES[words.pop()]
        if words[-1:] == ['-']:
            words.pop()
        if len(words)>=2 and words[-2] in _PHOTO_SOURCE_WORDS and words[-1] in ('1','2','3','4'):
            values.setdefault(int(words[-1]),set()).add(phase)
        elif allow_single and words and words[-1] in _PHOTO_SOURCE_WORDS:
            values.setdefault(1,set()).add(phase)
    if any(len(phases)!=1 for phases in values.values()):
        return None
    return {index:next(iter(phases)) for index,phases in values.items()}


def _filename_photo_labels(files):
    if len(files) != 2:
        return {}
    labels = {}
    for index, row in enumerate(files, 1):
        tokens = re.split(r'[\W_]+', row['original_name'].rsplit('.', 1)[0].casefold())
        phases = {_FILENAME_PHASES[token] for token in tokens if token in _FILENAME_PHASES}
        if len(phases) != 1:
            return {}
        labels[index] = phases.pop()
    return labels if len(set(labels.values())) == 2 else {}


def _required_photo_point(report):
    required = [row['id'] for row in report['checklist'] if row['photoRequired']]
    return required[0] if len(required) == 1 else None


class ToolSession:
    def __init__(self, app, principal, thread, turn_id, headers, files, *, local_date: date,
                 last_selected_day: date | None = None, earlier_photos=(), question=''):
        self.app, self.principal, self.thread, self.turn_id, self.headers = app, principal, thread, turn_id, headers
        self.local_date = local_date
        self.last_selected_day = last_selected_day
        self.question = question
        self.files = {row['attachment_id']: row for row in files}
        self.report_files = {row['attachment_id']: row for row in files if row['mime_type'].startswith('image/')}
        self.filename_photo_labels = _filename_photo_labels(self.report_files.values())
        if not self.report_files:
            self.report_files = {row['attachment_id']: row for row in earlier_photos}
        self.registry = available(app, principal.role, 'assistant')
        self.definition = dict(COMMON) if principal.role in ('engineer', 'executor') else {}
        if not any(row['mime_type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                   for row in files):
            self.definition.pop('read_workbook', None)
        if principal.role == 'engineer':
            self.definition.update(ENGINEER)
            if files:
                self.definition.pop('propose_assignment')
        if principal.role == 'executor' and self.report_files:
            self.definition['propose_report_attach_and_submit'] = (ProposedReport,
                'Подготовить одно подтверждение прикрепления явно отправленных фото и передачи отчёта при полном комплекте. '
                'При неполном комплекте карточка допустима: после подтверждения фото сохраняются в черновике без сдачи. '
                'Только по просьбе исполнителя. Сначала прочитайте выбранный наряд, его ревизию, попытку и пункты. '
                'Фазы указывает пользователь или их подсказывают однозначные имена двух текущих файлов. '
                'Не угадывайте фазу, ракурс и пункт. Не меняет наряд без клика.')
        self.specs = [dict(type='function', function=dict(name=name, description=description,
                      parameters=model.model_json_schema())) for name, (model, description) in self.definition.items()]
        self.proposal = None
        self.scope = {'tasks': set(), 'equipment': set()}
        self.read_tasks = set()
        self.checked_assignment_windows: dict[UUID, tuple[datetime | None, datetime | None]] = {}

    @property
    def visibility(self):
        return 'assigned_orders' if self.principal.role == 'executor' else 'site'

    async def backend(self, name, **args):
        tool = self.registry.get(name)
        if tool is None or tool.mode != 'read':
            raise HTTPException(403, 'Операция недоступна для текущей роли.')
        return await invoke(self.app, tool, validate_arguments(self.app, tool, args), self.headers)

    async def dispatch(self, name, arguments):
        if name not in self.definition:
            raise HTTPException(403, 'Инструмент недоступен.')
        try:
            parsed = self.definition[name][0].model_validate(arguments)
        except ValidationError as exc:
            fields = self.definition[name][0].model_fields
            issues = [dict(field=e['loc'][0] if e['loc'] and e['loc'][0] in fields else 'arguments',
                           type=e['type']) for e in exc.errors(include_input=False, include_context=False, include_url=False)[:6]]
            message = ('Передайте начало и конец по часам объекта в формате YYYY-MM-DDTHH:MM, без Z и смещения UTC.'
                       if any(issue['type'] == 'timezone_naive' for issue in issues)
                       else 'Исправьте параметры по схеме инструмента.')
            raise HTTPException(422, dict(message=message, issues=issues)) from None
        value = await getattr(self, name)(parsed)
        if name in ('find_work_orders', 'find_calendar_events', 'read_workforce_load'):
            page = _page_for_model(value, 10500)
            if name == 'find_work_orders' and parsed.presentation == 'schedule':
                return Observation(page, final_answer=_schedule_answer(page))
            return page
        return value if isinstance(value, Observation) else service.compact(value, 10500)

    async def find_work_orders(self, args):
        query = args.model_dump(mode='json', exclude={'on_date', 'relative_day', 'day_offset_from_last_selection', 'presentation'},
                                exclude_none=True)
        if not args.model_dump(exclude_defaults=True, exclude={'sort', 'offset', 'limit', 'presentation'}):
            query['summary_on'] = self.local_date
        day = args.on_date
        if args.day_offset_from_last_selection is not None:
            if self.last_selected_day is None:
                raise HTTPException(422, 'В текущем диалоге нет последней выборки ровно за один день.')
            try:
                day = self.last_selected_day + timedelta(days=args.day_offset_from_last_selection)
            except OverflowError:
                raise HTTPException(422, 'Сдвиг выходит за допустимые даты.') from None
        elif args.relative_day is not None:
            day = self.local_date + timedelta(days=DAY_SHIFTS[args.relative_day])
        day = day or (args.starts_on if args.starts_on == args.ends_on else None)
        if args.presentation == 'schedule' and (day is None or args.period != 'all'):
            raise HTTPException(422, 'Готовая таблица доступна только за один выбранный плановый день (period=all). '
                                     'Для диапазона или других периодов повторите чтение без presentation, сохранив фильтры запроса.')
        if day is not None:
            query.update(starts_on=day, ends_on=day)
        page = await self.backend('tasks_find', query={**query, 'active_only': False, 'use_planned_date': True,
                                                       'displayed_search': True})
        self.last_selected_day = day
        items = []
        for row in page['items']:
            item = {key: row[key] for key in ORDER_FIELDS if key in row}
            minutes = row.get('overdueMinutes')
            if minutes is not None:
                days, rest = divmod(minutes, 1440)
                hours, remainder = divmod(rest, 60)
                item['overdueDuration'] = dict(days=days, hours=hours, minutes=remainder)
            items.append(item)
        page['items'] = items
        for item in page['items']:
            self.scope['tasks'].add(item['id'])
            item['assignees'] = [{k: person[k] for k in ('executorId', 'name')} for person in item.get('assignees', ())]
        result = dict(local_date=self.local_date.isoformat(), timezone=self.principal.timezone, visibility=self.visibility,
                      resolved_day=day.isoformat() if day is not None else None,
                      **{key: page[key] for key in ('items', 'total', 'offset', 'limit', 'period', 'filters', 'page_complete', 'checked_at')})
        if 'summary' in page:
            result['summary'] = dict(status_counts=page['summary']['status_counts'], today=page['summary']['day'])
        if 'planned_duration' in page:
            result['planned_duration'] = page['planned_duration']
        if 'planned_start_summary' in page:
            result['planned_start_summary'] = page['planned_start_summary']
        return result

    async def read_work_order(self, args):
        data = await self.backend('task_read', path=dict(task_id=args.task_id))
        self.scope['tasks'].add(str(args.task_id))
        self.read_tasks.add(args.task_id)
        data['task']['regulation_equipment_ids'] = data['task'].get('equipmentIds', [])
        decision, report = data.get('decision'), data.get('execution')
        if decision and (report is None or decision['executionId'] != report['id']):
            data['previousDecision'], data['decision'] = decision, None
        task = data['task']
        if report and task['state'] in ('in_progress', 'submitted'):
            try:
                readiness = await self.check_acceptance_readiness(AcceptanceReadiness(
                    task_id=args.task_id, expected_revision=task['revision'], execution_id=report['id']))
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                data['readiness'] = dict(status='stale')
            else:
                data['readiness'] = {key: readiness[key] for key in ('revision', 'execution_id', 'ready',
                    'submission_ready', 'missing_materials', 'acceptance_blocks', 'submission_blocks')}
        return data

    def general_report_target(self):
        if (self.thread.get('subject_task_id') or 'propose_report_attach_and_submit' not in self.definition
                or not self.filename_photo_labels or not _report_command(self.question, general_chat=True)):
            return None
        with self.app.state.factory() as session:
            target = resolve_report_target(session, self.principal, self.question)
        if target is None:
            raise HTTPException(422, TARGET_REQUIRED)
        return target

    def named_report_arguments(self, subject):
        if ('propose_report_attach_and_submit' not in self.definition or not self.filename_photo_labels
                or not subject or not _report_command(self.question, general_chat=not self.thread.get('subject_task_id'))
                or not {'upload_photo','submit'}.issubset(subject.get('allowedActions', ()))):
            return None
        report = subject.get('execution')
        point = _required_photo_point(report) if report else None
        if not point:
            return None
        return dict(task_id=subject['task']['id'], expected_revision=subject['task']['revision'],
                    execution_id=report['id'], photos=[
                        dict(attachment_id=str(identity), checklist_item_id=point,
                             phase=self.filename_photo_labels[index], view_key='front')
                        for index, identity in enumerate(self.report_files, 1)])

    async def propose_report_attach_and_submit(self, args):
        subject = self.thread.get('subject_task_id')
        tool = self.registry.get('report_attach_and_submit')
        if tool is None or (subject and subject != args.task_id):
            raise HTTPException(403, 'Этот наряд не относится к открытому диалогу.')
        if self.proposal:
            raise HTTPException(409, 'Карточка уже подготовлена.')
        if args.task_id not in self.read_tasks:
            raise HTTPException(422, 'Сначала прочитайте нужный наряд.')
        if any(p.attachment_id not in self.report_files for p in args.photos):
            raise HTTPException(404, 'Используйте только явно отправленные фотографии этого диалога.')
        positions = {identity:index for index,identity in enumerate(self.report_files, 1)}
        labels = _photo_labels(self.question, len(positions)==1 and bool(self.files))
        filenames = _filename_photo_labels(self.report_files.values())
        if labels and any(index in filenames and phase != filenames[index] for index, phase in labels.items()):
            raise HTTPException(422, 'Указанные фазы противоречат именам файлов. Уточните, какой кадр «до», а какой «после», '
                                     'и исправьте подписи или отправьте файлы с однозначными именами.')
        from_names = labels == {} and bool(self.filename_photo_labels)
        if {positions[p.attachment_id]:p.phase for p in args.photos} != (self.filename_photo_labels if from_names else labels):
            raise HTTPException(422, 'Укажите фазу каждого выбранного снимка, например: «фото 1 — до, фото 2 — после».')
        data = await self.backend('task_read', path=dict(task_id=args.task_id))
        task, report = data['task'], data.get('execution')
        if not subject:
            with self.app.state.factory() as session:
                target = resolve_report_target(session, self.principal, self.question)
            if self.read_tasks != {args.task_id} or target != args.task_id:
                raise HTTPException(422, TARGET_REQUIRED)
        if (not report or report['id'] != str(args.execution_id) or task['revision'] != args.expected_revision
                or 'upload_photo' not in data['allowedActions'] or 'submit' not in data['allowedActions']):
            raise HTTPException(409, 'Действие доступно только автору актуального черновика отчёта.')
        items = {row['id']:row['text'] for row in report['checklist']}
        if any(str(p.checklist_item_id) not in items for p in args.photos):
            raise HTTPException(422, 'Укажите пункт чек-листа текущей попытки.')
        if from_names and {str(p.checklist_item_id) for p in args.photos} != {_required_photo_point(report)}:
            raise HTTPException(422, 'Укажите пункт, фазы и ракурс для снимков: в отчёте нет одного однозначного пункта для этой пары.')
        lines = [f"{task['title'][:360]} — попытка №{report['attemptNumber']}."]
        bindings = sorted(args.photos, key=lambda p: positions[p.attachment_id])
        for index, p in enumerate(bindings, 1):
            phase = 'до' if p.phase == 'before' else 'после'
            lines.append(f"Снимок {index}: {self.report_files[p.attachment_id]['original_name'][:160]} — {items[str(p.checklist_item_id)][:240]}, {phase}, ракурс: {p.view_key}.")
        if from_names:
            lines.append('Фазы предложены по именам файлов. Проверьте фазы, пункт и ракурс перед подтверждением.')
        lines.append('Если комплект неполный, фото сохранятся в черновике, отчёт не будет отправлен.')
        arguments = dict(path=dict(task_id=args.task_id), body=args.model_copy(update={'photos':bindings}).model_dump(
            mode='json', exclude={'task_id'}))
        with self.app.state.factory() as session:
            action = await service.propose(self.app, session, self.principal, self.thread, tool,
                                           arguments, '\n'.join(lines), self.headers, self.turn_id)
        self.proposal = action['action_id']
        return dict(status='awaiting_confirmation', action_id=str(self.proposal))

    async def check_acceptance_readiness(self, args):
        data = await self.backend('task_acceptance_evidence', path=dict(task_id=args.task_id),
            query=args.model_dump(mode='json', exclude={'task_id'}, exclude_none=True))
        self.scope['tasks'].add(str(args.task_id))
        return data

    async def find_equipment(self, args):
        data = await self.backend('equipment_find', query={**args.model_dump(mode='json', exclude_none=True), 'limit': 8})
        self.scope['equipment'].update(str(row['equipment_id']) for row in data['items'])
        return dict(visibility=self.visibility, **{key: data[key] for key in ('items', 'total', 'offset', 'limit')})

    async def read_equipment(self, args):
        data = await self.backend('equipment_read', path=dict(equipment_id=args.equipment_id))
        self.scope['equipment'].add(str(args.equipment_id))
        if self.principal.role == 'engineer':
            data['latestAcceptedService'] = await self.read_equipment_service_history(args)
        return data

    async def read_regulations(self, args):
        data = await self.backend('regulations_read', path=dict(equipment_id=args.equipment_id),
                                  query=dict(include_effectivity=True))
        self.scope['equipment'].add(str(args.equipment_id))
        today = self.local_date.isoformat()
        for row in data:
            start, end = row['effective_from'], row['effective_until']
            if row['publication_status'] != 'published':
                status = row['publication_status']
            elif not row['edition_approved']:
                status = 'unapproved'
            elif not row['operation_available'] or (end and end < start):
                status = 'inactive'
            elif today < start:
                status = 'future'
            elif end and today > end:
                status = 'expired'
            else:
                status = 'active'
            row.update(effective_on=today, effective_status=status)
        return data

    async def read_equipment_service_history(self, args):
        data = await self.backend('equipment_service_history', path=dict(equipment_id=args.equipment_id),
                                  query=dict(only_accepted=True, latest_only=True))
        self.scope['equipment'].add(str(args.equipment_id))
        self.scope['tasks'].update(str(item['task_id']) for item in data.get('items', []) if item.get('task_id'))
        return data

    async def find_calendar_events(self, args):
        if not 0 <= (args.ends_on - args.starts_on).days < 92 or not 2000 <= args.starts_on.year <= args.ends_on.year <= 2200:
            raise HTTPException(422, 'Выберите непрерывный период от 1 до 92 дней в пределах 2000–2200 гг.')
        first, last = args.starts_on.isoformat(), args.ends_on.isoformat()
        year, month = args.starts_on.year, args.starts_on.month
        items = []
        while (year, month) <= (args.ends_on.year, args.ends_on.month):
            page = await self.backend('calendar_read', query=dict(year=year, month=month))
            # The calendar can also return entries by source month. Filter on planned dates,
            # reading each entry only in its actual planned month.
            prefix = f'{year:04d}-{month:02d}'
            items.extend(row for row in page if row.get('status') == 'planned'
                         and isinstance(row.get('occurrenceDate'), str)
                         and row['occurrenceDate'][:7] == prefix and first <= row['occurrenceDate'] <= last)
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        items.sort(key=lambda row: (row['occurrenceDate'], row['id']))
        page = items[args.offset:args.offset + args.limit]
        self.scope['tasks'].update(row['taskId'] for row in page if row.get('taskId'))
        return dict(source='saved_calendar_events', starts_on=first, ends_on=last, total=len(items),
                    offset=args.offset, limit=args.limit, items=page)

    async def calculate_due_dates(self, args):
        data = await self.backend('calendar_evidence', path=dict(equipment_id=args.equipment_id),
            query=dict(starts_on=args.starts_on, ends_on=args.ends_on, approved_only=True, next_only=True))
        self.scope['equipment'].add(str(args.equipment_id))
        return data

    async def read_workforce_load(self, args):
        day = args.day or self.local_date + timedelta(days=DAY_SHIFTS[args.relative_day])
        return await self.backend('workforce_load', query={**args.model_dump(mode='json',
            exclude={'day', 'relative_day'}, exclude_none=True), 'day': day.isoformat()})

    async def read_work_order_analysis(self, args):
        result = await self.backend('tasks_analyze', query=args.model_dump(mode='json', exclude_none=True))
        fields = ('checked_at', 'timezone', 'scope', 'complete', 'selected_tasks', 'due', 'scheduled',
                  'known_person_hours', 'unknown_effort_tasks', 'limitations')
        sample = result.get('sample', [])[:5]
        return {**{key: result[key] for key in fields}, 'site_counters': result['counters'],
                'illustrative_sample': sample, 'sample_truncated': result['selected_tasks'] > len(sample),
                'schedule_optimization_performed': False}

    async def check_assignment(self, args):
        if args.start_local is not None or args.end_local is not None:
            self.checked_assignment_windows[args.task_id] = (args.start_local, args.end_local)
        preview = await self._assignment(args)
        return self._assignment_facts(preview)

    async def _assignment(self, args):
        window = self.checked_assignment_windows.get(args.task_id)
        requested = (args.start_local, args.end_local)
        if window is not None:
            if requested == (None, None):
                start, end = window
                args = args.model_copy(update=dict(start_local=start, end_local=end))
            elif requested != window:
                raise HTTPException(422, 'Время отличается от проверенного окна. Сначала проверьте новое окно.')
        elif requested != (None, None):
            self.checked_assignment_windows[args.task_id] = requested
        preview = await self.backend('assignment_prepare', path=dict(task_id=args.task_id),
            body={**args.model_dump(mode='json', include={'executor_ids', 'start_local', 'end_local'}, exclude_none=True),
                  'use_planned_day': True})
        if args.start_local is not None:
            preview['exactWindow'] = True
        return preview

    @staticmethod
    def _assignment_facts(preview):
        fields = ('status', 'code', 'taskTitle', 'plannedDay', 'exactWindow', 'windowStartLocal', 'windowEndLocal',
                  'startAt', 'endAt', 'selectedWorkers', 'crewName')
        result = {key: preview[key] for key in fields if key in preview}
        if preview.get('status') != 'ok':
            result['limitation'] = preview.get('explanation')
        workers = preview.get('workers', [])
        selected_ids = {worker['executorId'] for worker in result.get('selectedWorkers', [])}
        result['selectedWorkers'] = [{key: worker[key] for key in ('name', 'executorId', 'loadMinutes')}
                                     for worker in result.get('selectedWorkers', [])]
        alternatives = [{key: worker[key] for key in ('name', 'executorId', 'loadMinutes', 'earliestStart')}
            for worker in workers if worker['status'] == 'available' and worker['executorId'] not in selected_ids]
        excluded = [dict(name=worker['name'], reason=worker['explanation'])
                    for worker in workers if worker['status'] == 'excluded']
        result.update(eligibleAlternatives=alternatives[:6], eligibleAlternativeCount=len(alternatives),
                      excludedWorkers=excluded[:6], excludedWorkerCount=len(excluded),
                      candidateDetailsTruncated=max(len(alternatives), len(excluded)) > 6)
        result['candidateCount'] = len(workers)
        result['ranking'] = ['loadMinutes', 'earliestStart', 'technical_tie_breaker'] if preview.get('recommendationMode') == 'automatic' else None
        context = preview.get('context', {})
        result.update(crewSize=context.get('crewSize'), durationMinutes=context.get('durationMinutes'),
                      qualifications=context.get('requiredQualifications', []))
        return result

    async def propose_assignment(self, args):
        if self.proposal:
            raise HTTPException(409, 'В этом ответе уже подготовлена карточка назначения. Другой состав запросите отдельно.')
        preview = await self._assignment(args)
        result = self._assignment_facts(preview)
        if not preview.get('command'):
            return result
        tool = self.registry.get('task_assign')
        if tool is None or tool.mode != 'write':
            raise HTTPException(403, 'Назначение недоступно для текущей роли.')
        arguments = validate_arguments(self.app, tool, dict(path=dict(task_id=args.task_id),
            body={**preview['command'], 'reason': args.reason, 'crew_id': preview.get('crewId')}))
        names = ', '.join(row['name'] for row in preview['selectedWorkers'])
        explanation = (f"{preview['taskTitle']} — {names}; "
                       f"{preview['startAt']} — {preview['endAt']}. Причина: {args.reason}")
        with self.app.state.factory() as session:
            pending = session.execute(text('''SELECT a.action_id,a.arguments FROM assistant_actions a
                JOIN assistant_turns t ON t.turn_id=a.turn_id
                WHERE a.conversation_id=:chat AND a.tool_name='task_assign' AND a.status='proposed'
                  AND a.expires_at>now() AND t.execution_engine='v4' AND t.status='completed'
                  AND a.arguments #>> '{path,task_id}'=:task ORDER BY a.created_at DESC'''),
                dict(chat=self.thread['conversation_id'], task=str(args.task_id))).mappings()
            existing = next((row for row in pending if _same_assignment(row['arguments']['body'], arguments['body'])), None)
            if existing:
                self.proposal = existing['action_id']
                return {**result, 'status': 'awaiting_confirmation', 'action_id': str(self.proposal), 'reused': True}
            action = await service.propose(self.app, session, self.principal, self.thread, tool,
                arguments, explanation, self.headers, self.turn_id)
        self.proposal = action['action_id']
        return {**result, 'status': 'awaiting_confirmation', 'action_id': str(self.proposal),
                 'notice': 'Предложение создано. Назначение не выполнено.'}

    async def read_workbook(self, args):
        file = self.files.get(args.attachment_id)
        if file is None or file['mime_type'] != 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            raise HTTPException(404, 'Книга не прикреплена к этому сообщению.')
        return await self.backend('attachment_read',
            path=dict(identity=self.thread['conversation_id'], attachment_id=args.attachment_id),
            query={**args.model_dump(mode='json', exclude={'attachment_id'}, exclude_none=True), 'limit': 8})

    async def read_report_photos(self, args):
        if not args.compare_with_attachment and any(row['mime_type'].startswith('image/') for row in self.files.values()):
            raise HTTPException(422, 'Оцените приложенное изображение отдельно. Архив откройте только для явно запрошенного сравнения.')
        bundle = await self.backend('task_read', path=dict(task_id=args.task_id))
        self.scope['tasks'].add(str(args.task_id))
        report = bundle.get('execution') or {}
        photos = sorted(report.get('photos', []), key=lambda row: (row['viewKey'], row['id']))
        selected = [row for phase in dict.fromkeys(args.phases) for row in
                    [entry for entry in photos if entry.get('phase') == phase][:2]]
        data, images, resources = [], [], []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
                                     base_url='http://assistant.internal', follow_redirects=False) as client:
            for row in selected:
                path = f"/api/v1/maintenance/photos/{UUID(row['id'])}/content"
                outcome = {k: row[k] for k in ('id', 'phase', 'viewKey', 'checklistItemId')}
                async with client.stream('GET', path, headers=self.headers) as response:
                    if response.status_code == 200 and response.headers.get('content-type', '').startswith('image/'):
                        blob = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(blob) + len(chunk) > MAX_FILE:
                                break
                            blob.extend(chunk)
                        else:
                            try:
                                images.append(jpeg_input(blob))
                                outcome['image_index'] = len(images)
                                phase = 'до работы' if row['phase'] == 'before' else 'после работы'
                                resources.append(dict(url=path, mime=response.headers['content-type'],
                                                      title=f"Фото из отчёта · {phase} · {row['viewKey']}"))
                            except HTTPException:
                                pass
                data.append(outcome)
        return Observation(dict(source='saved_report_photos', report_id=report.get('id'),
                                total_available=len(photos), photos=data), tuple(images), tuple(resources))
