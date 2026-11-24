"""Small typed maintenance vocabulary over the authenticated capability registry."""
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import text

from . import service
from .attachments import MAX_FILE, jpeg_input
from .tool_agent import Observation
from .tools import available, invoke, validate_arguments


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class WorkOrders(Arguments):
    period: Literal['all', 'upcoming', 'overdue', 'undated'] = 'all'
    state: Literal['draft', 'assigned', 'clarification', 'rework', 'in_progress', 'in_review', 'completed', 'cancelled'] | None = None
    unfinished_only: bool = False
    unassigned_only: bool = False
    attention_only: bool = False
    maintenance_only: bool = False
    on_date: date | None = Field(default=None, description='Ровно один день, YYYY-MM-DD')
    starts_on: date | None = Field(default=None, description='Первый включённый день многодневного диапазона, требуется ends_on')
    ends_on: date | None = Field(default=None, description='Последний включённый день многодневного диапазона, требуется starts_on')
    equipment_id: UUID | None = None
    equipment_asset_code: str | None = Field(default=None, max_length=128)
    q: str = Field(default='', max_length=200, description='Буквальная подстрока названия/кода операции, не полный вопрос')
    sort: Literal['earliest', 'latest'] = 'earliest'
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=8, ge=1, le=15)

    @model_validator(mode='after')
    def date_range(self):
        if (self.starts_on is None) != (self.ends_on is None):
            raise ValueError('A date range needs both endpoints; use on_date for a single day')
        if self.starts_on is not None and (self.on_date is not None or self.starts_on > self.ends_on):
            raise ValueError('Use exactly one chronological interval or on_date')
        return self


class WorkOrder(Arguments):
    task_id: UUID


class ReportPhotos(WorkOrder):
    phases: list[Literal['before', 'after']] = Field(default_factory=lambda: ['before', 'after'], min_length=1, max_length=2)


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


class Assignment(WorkOrder):
    executor_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20,
        description='Только если нужен конкретный полный состав. Иначе сервер подбирает автоматически.')


class ProposedAssignment(Assignment):
    reason: str = Field(min_length=1, max_length=500, description='Краткая причина именно этого назначения.')


class Workbook(Arguments):
    attachment_id: UUID
    sheet: str | None = Field(default=None, max_length=255)
    offset: int = Field(default=0, ge=0, le=1048576)


# Public model vocabulary; transport names and write command bodies are never model-selected.
COMMON = {
    'find_work_orders': (WorkOrders, 'Найти наряды. Для одного дня используйте on_date и period=all. Фильтры пересекаются. '
                         'Дата — сохранённая плановая дата; для overdue — обязательный срок. '
                         'Для ближайшего ТО: period=upcoming, maintenance_only=true, unfinished_only=true, sort=earliest. '
                         'attention_only: просрочено, нет назначенного состава, на уточнении или доработке.'),
    'read_work_order': (WorkOrder, 'Свежая карточка указанного наряда, применённые инструкции, чек-лист, отчёт, замечания и список материалов.'),
    'find_equipment': (EquipmentSearch, 'Поиск доступного оборудования по подстроке названия, кода или места либо точному инвентарному коду.'),
    'read_equipment': (Equipment, 'Паспортные поля, место, состояние и доступные реквизиты конкретного оборудования.'),
    'read_regulations': (Equipment, 'Настройки регламентов и чек-листы конкретного оборудования. Отличайте действующие версии от остальных.'),
    'find_calendar_events': (Calendar, 'Запланированные календарные события ТО, включая события без сформированного наряда. '
                             'Включённые даты объекта, не более 92 дней; по плановой дате от раннего к позднему.'),
    'calculate_due_dates': (CalculatedDates, 'Расчёт дат ТО по утверждённым привязкам конкретного оборудования, а не реальные наряды.'),
    'read_report_photos': (ReportPhotos, 'Получить реальные изображения последней попытки доступного наряда, до двух на фазу. '
                           'Вызывайте только для визуальной оценки; учитывайте соответствие ракурса и фазы.'),
    'read_workbook': (Workbook, 'Без записи прочитать страницу строк личного XLSX, отправленного в текущем сообщении.'),
}
ENGINEER = {
    'check_assignment': (Assignment, 'Рассчитать доступный состав на сохранённую плановую дату наряда без записи. '
                         'Проверяются длительность, смены, пересечения и допуски; результат содержит причины и нагрузку.'),
    'propose_assignment': (ProposedAssignment, 'Подготовить карточку назначения или переназначения на сохранённую дату. '
                           'Только по запросу изменить конкретный наряд. Данные не меняются до подтверждения карточки человеком.'),
}

ORDER_FIELDS = (
    'id', 'code', 'title', 'summary', 'equipmentIds', 'equipmentName', 'scheduledStart', 'scheduledEnd', 'plannedDate',
    'mandatoryDueDate', 'matchedAt', 'state', 'rawStatus', 'priority', 'createdBy', 'assignees', 'isOverdue',
    'overdueSince', 'attentionReasons', 'durationMinutes', 'maintenanceType',
)


def _same_assignment(before, after):
    def comparable(body):
        return {**{key: value for key, value in body.items() if key not in ('reason', 'executor_ids')},
                'executor_ids': sorted(body['executor_ids'])}
    return comparable(before) == comparable(after)


class ToolSession:
    def __init__(self, app, principal, thread, turn_id, headers, files):
        self.app, self.principal, self.thread, self.turn_id, self.headers = app, principal, thread, turn_id, headers
        self.files = {row['attachment_id']: row for row in files}
        self.registry = available(app, principal.role, 'assistant')
        self.definition = dict(COMMON) if principal.role in ('engineer', 'executor') else {}
        if not any(row['mime_type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                   for row in files):
            self.definition.pop('read_workbook', None)
        if principal.role == 'engineer':
            self.definition.update(ENGINEER)
            if files:
                self.definition.pop('propose_assignment')
        self.specs = [dict(type='function', function=dict(name=name, description=description,
                      parameters=model.model_json_schema())) for name, (model, description) in self.definition.items()]
        self.proposal = None
        self.scope = {'tasks': set(), 'equipment': set()}

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
            raise HTTPException(422, dict(message='Исправьте параметры по схеме инструмента.', issues=issues)) from None
        value = await getattr(self, name)(parsed)
        return value if isinstance(value, Observation) else service.compact(value, 10500)

    async def find_work_orders(self, args):
        query = args.model_dump(mode='json', exclude={'on_date'}, exclude_none=True)
        if args.on_date:
            query.update(starts_on=args.on_date, ends_on=args.on_date)
        page = await self.backend('tasks_find', query={**query, 'active_only': False, 'use_planned_date': True})
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
        return {key: page[key] for key in ('items', 'total', 'offset', 'limit', 'period', 'filters', 'page_complete')}

    async def read_work_order(self, args):
        data = await self.backend('task_read', path=dict(task_id=args.task_id))
        self.scope['tasks'].add(str(args.task_id))
        data['task']['regulation_equipment_ids'] = data['task'].get('equipmentIds', [])
        return data

    async def find_equipment(self, args):
        data = await self.backend('equipment_find', query={**args.model_dump(mode='json', exclude_none=True), 'limit': 8})
        self.scope['equipment'].update(str(row['equipment_id']) for row in data['items'])
        return {key: data[key] for key in ('items', 'total', 'offset', 'limit')}

    async def read_equipment(self, args):
        data = await self.backend('equipment_read', path=dict(equipment_id=args.equipment_id))
        self.scope['equipment'].add(str(args.equipment_id))
        return data

    async def read_regulations(self, args):
        data = await self.backend('regulations_read', path=dict(equipment_id=args.equipment_id))
        self.scope['equipment'].add(str(args.equipment_id))
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

    async def check_assignment(self, args):
        preview = await self._assignment(args)
        return self._assignment_facts(preview)

    async def _assignment(self, args):
        return await self.backend('assignment_prepare', path=dict(task_id=args.task_id),
            body=dict(executor_ids=args.executor_ids, use_planned_day=True))

    @staticmethod
    def _assignment_facts(preview):
        fields = ('status', 'code', 'taskTitle', 'plannedDay', 'windowStartLocal', 'windowEndLocal',
                  'startAt', 'endAt', 'selectedWorkers', 'crewName')
        result = {key: preview[key] for key in fields if key in preview}
        if preview.get('status') != 'ok':
            result['limitation'] = preview.get('explanation')
        workers = preview.get('workers', [])
        selected_ids = {worker['executorId'] for worker in result.get('selectedWorkers', [])}
        result['selectedWorkers'] = [{key: worker[key] for key in ('name', 'executorId', 'loadMinutes')}
                                     for worker in result.get('selectedWorkers', [])]
        result['eligibleAlternatives'] = [{key: worker[key] for key in ('name', 'executorId', 'loadMinutes', 'earliestStart')}
            for worker in workers if worker['status'] == 'available' and worker['executorId'] not in selected_ids][:6]
        result['excludedWorkers'] = [dict(name=worker['name'], reason=worker['explanation'])
                                     for worker in workers if worker['status'] == 'excluded'][:6]
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
        bundle = await self.backend('task_read', path=dict(task_id=args.task_id))
        self.scope['tasks'].add(str(args.task_id))
        report = bundle.get('execution') or {}
        photos = sorted(report.get('photos', []), key=lambda row: (row['viewKey'], row['id']))
        selected = [row for phase in dict.fromkeys(args.phases) for row in
                    [entry for entry in photos if entry.get('phase') == phase][:2]]
        data, images = [], []
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
                            except HTTPException:
                                pass
                data.append(outcome)
        return Observation(dict(report_id=report.get('id'), total_available=len(photos), photos=data), tuple(images))
