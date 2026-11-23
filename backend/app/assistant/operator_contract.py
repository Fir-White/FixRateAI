"""Semantic objectives, trusted selectors and proof checks for bounded ERP reads."""
from datetime import date, datetime, timedelta
import re
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field

from .operator_state import StrictModel
from .maintenance_subject import dates as calendar_literals, type_keys, without_types


SOURCES = {
    'equipment_list': 'equipment_find',
    'equipment_card': 'equipment_read',
    'accepted_report': 'equipment_service_history',
    'equipment_regulation': 'regulations_read',
    'work_orders': 'tasks_find',
    'maintenance_types': 'maintenance_catalog_read',
    'maintenance_operations': 'maintenance_catalog_read',
}
EQUIPMENT_PATH = {'equipment_read', 'equipment_service_history', 'regulations_read'}
EQUIPMENT_SCOPE = {'equipment_id', 'equipment_ids', 'equipment_q', 'equipment_asset_code',
                   'equipment_accepted_maintenance'}
ScopeKind = Literal['inherit', 'site', 'asset_code', 'asset_name', 'asset_id']
RELATIVE_DAYS = {'вчера': -1, 'сегодня': 0, 'завтра': 1, 'послезавтра': 2}
WORK_STATE_LABELS = {
    'assigned': {'назначен', 'назначена', 'назначено', 'назначены', 'назначенный', 'назначенные', 'назначенных',
                 'назначенную'},
    'draft': {'черновик', 'черновики', 'черновиков', 'черновой', 'черновые', 'черновых'},
    'completed': {'завершённые', 'завершенные', 'завершённых', 'завершенных'},
    'cancelled': {'отменённые', 'отмененные', 'отменённых', 'отмененных'},
}


class GoalClarification(ValueError):
    """The current message and scoped history lack a required business selector."""


class DateChange(StrictModel):
    kind: Literal['today', 'tomorrow', 'yesterday', 'shift', 'absolute', 'clear']
    days: int | None = Field(default=None, ge=-31, le=31)
    start: date | None = None
    end: date | None = None
    quote: str = Field(default='', max_length=180)

    def dates(self, previous, today, question):
        if self.kind == 'clear':
            return {}
        if self.kind == 'absolute':
            literals = calendar_literals(question, today.isoformat()) or []
            if not self.start or self.start.isoformat() not in literals:
                raise HTTPException(422, 'Укажите местную дату в формате ГГГГ-ММ-ДД.')
            end = self.end or self.start
            if end < self.start or end != self.start and end.isoformat() not in literals:
                raise HTTPException(422, 'Укажите границы периода.')
            return {'starts_on': self.start.isoformat(), 'ends_on': end.isoformat()}
        if self.kind == 'shift':
            if self.days is None or not previous.get('starts_on') or not previous.get('ends_on'):
                raise GoalClarification('Укажите исходную дату или период для сдвига.')
            return {key: (date.fromisoformat(previous[key]) + timedelta(days=self.days)).isoformat()
                    for key in ('starts_on', 'ends_on')}
        value = (today + timedelta(days={'today': 0, 'tomorrow': 1, 'yesterday': -1}[self.kind])).isoformat()
        return {'starts_on': value, 'ends_on': value}


class ReadGoal(StrictModel):
    outcome: Literal['equipment_list', 'equipment_card', 'accepted_report', 'equipment_regulation',
                     'work_orders', 'maintenance_types', 'maintenance_operations']
    scope: ScopeKind = 'inherit'
    selector: str = Field(default='', max_length=180)
    scope_quote: str = Field(default='', max_length=180)
    accepted: Literal['none', 'present'] | None = None
    work_state: Literal['draft', 'assigned', 'clarification', 'rework', 'in_progress', 'in_review',
                        'completed', 'cancelled'] | None = None
    date: DateChange | None = None
    period: Literal['all', 'upcoming', 'overdue', 'undated'] | None = None
    sort: Literal['earliest', 'latest'] | None = None
    limit: int | None = Field(default=None, ge=1, le=25)
    offset: int | None = Field(default=None, ge=0)
    output: Literal['items', 'count', 'types'] = 'items'
    maintenance_only: bool | None = None
    scheduled_only: bool | None = None
    unassigned_only: bool | None = None
    type_code: str | None = Field(default=None, max_length=100)
    type_position: int | None = Field(default=None, ge=1, le=25)

    def bind_literal_selector(self, question):
        from .semantic_plan import asset_references

        equipment_goal = self.outcome in ('equipment_card', 'equipment_list', 'accepted_report', 'equipment_regulation')
        if not equipment_goal and self.outcome != 'work_orders':
            return self
        if self.scope in ('asset_name', 'asset_id'):
            return self
        codes = asset_references(without_types(question))
        match = next((code for code in codes if code.casefold() == self.selector.casefold()), None)
        if match is None and equipment_goal and not self.selector and len(codes) == 1:
            match = codes[0]
        if match and quoted_in(match, question):
            return self.model_copy(update={'scope': 'asset_code', 'selector': match})
        return self


class Selector(StrictModel):
    kind: Literal['asset_code', 'asset_name', 'asset_id']
    value: str = Field(min_length=1, max_length=180)

    def arguments(self):
        key = 'asset_code' if self.kind == 'asset_code' else 'q'
        return {'query': {key: self.value}}


class ReadContract(StrictModel):
    source: str
    outcome: str
    output: Literal['items', 'count', 'types']
    query: dict
    selector: Selector | None = None
    equipment_id: UUID | None = None
    equipment_scope: dict = Field(default_factory=dict)

    def arguments(self):
        path = {'equipment_id': str(self.equipment_id)} if self.equipment_id else {}
        query = {**self.query, **self.equipment_scope}
        if self.output == 'count':
            query.update(limit=1, offset=0)
        return {'path': path, 'query': query}

    def verifies(self, proof, timezone):
        if proof.get('tool') != self.source or not proof.get('retained'):
            return False
        arguments = self.arguments()
        checked = proof['arguments']
        if any(checked.get('path', {}).get(key) != value for key, value in arguments['path'].items()):
            return False
        if any(checked.get('query', {}).get(key) != value for key, value in arguments['query'].items()):
            return False
        data = proof['result']
        if not isinstance(data, dict):
            return False
        rows = data.get('items', [])
        if self.source == 'equipment_read':
            return len(rows) == 1 and rows[0].get('equipment_id') == str(self.equipment_id)
        if self.source == 'equipment_find':
            filters = data.get('filters', {})
            return all(filters.get(key) == arguments['query'][key]
                       for key in ('q', 'asset_code', 'accepted_maintenance') if key in arguments['query'])
        if self.source == 'equipment_service_history':
            return (data.get('equipment_id') == str(self.equipment_id) and data.get('only_accepted') is True and
                    data.get('latest_only') is True and all(row.get('accepted_at') for row in rows) and
                    all(data.get(key) == expected for key, expected in self.query.items()
                        if key in ('starts_on', 'ends_on')))
        if self.source == 'maintenance_catalog_read':
            return all(data.get(key) == expected for key, expected in self.query.items()
                       if key in ('type_codes', 'type_keys'))
        if self.source != 'tasks_find':
            return True
        applied = data.get('filters', {})
        expected = {**self.query, **self.equipment_scope}
        for key in ('state', 'starts_on', 'ends_on', 'sort', 'scheduled_only', 'maintenance_only', 'unassigned_only',
                    'equipment_asset_code', 'equipment_q', 'equipment_id', 'equipment_accepted_maintenance'):
            if key in expected and applied.get(key, False) != expected[key]:
                return False
        if 'equipment_ids' in expected and set(applied.get('equipment_ids', ())) != set(expected['equipment_ids']):
            return False
        if 'period' in expected and data.get('period') != expected['period']:
            return False
        if data.get('timezone') != timezone or type(data.get('total')) is not int:
            return False
        offset = expected.get('offset', 0)
        limit = expected.get('limit', 25)
        if len(rows) != min(limit, max(0, data['total'] - offset)):
            return False
        instants = []
        for row in rows:
            if expected.get('state') and row.get('state') != expected['state']:
                return False
            instant = row.get('matchedAt')
            if not instant:
                if expected.get('starts_on') or expected.get('ends_on') or expected.get('scheduled_only'):
                    return False
                continue
            local = datetime.fromisoformat(instant).astimezone(ZoneInfo(timezone))
            day = local.date().isoformat()
            if (day < expected.get('starts_on', day) or day > expected.get('ends_on', day) or
                    ('on_days' in expected and day not in expected['on_days'])):
                return False
            instants.append(local.timestamp())
        return instants == sorted(instants, reverse=expected.get('sort', 'latest' if
                                  expected.get('period') == 'overdue' else 'earliest') == 'latest')


def quoted_in(phrase, question):
    normalized = ' '.join(phrase.casefold().split())
    return bool(normalized and re.search(r'(?<!\w)' + re.escape(normalized) + r'(?!\w)',
                                         ' '.join(question.casefold().split())))


def _calendar_constraints(question, today):
    words = set(re.findall(r'\w+', question.casefold()))
    literals = calendar_literals(question, today.isoformat())
    if literals is None:
        raise HTTPException(422, 'Уточните календарную дату.')
    named = sorted(set(literals) | {(today + timedelta(days=shift)).isoformat()
                                   for label, shift in RELATIVE_DAYS.items() if label in words})
    if len(named) == 1:
        return {'starts_on': named[0], 'ends_on': named[0]}
    if len(named) > 1:
        if len(named) > 31:
            raise HTTPException(422, 'Укажите период или до 31 отдельной даты.')
        return {'on_days': named}
    return {}


def _work_state(question):
    words = re.findall(r'\w+', question.casefold())
    # A visible status label supplies a literal filter only when there is one
    # positive value. Comparisons and exclusions stay with semantic planning.
    if {'кроме', 'исключая', 'или', 'без', 'не'} & set(words):
        return None
    values = {state for state, labels in WORK_STATE_LABELS.items() if labels.intersection(words)}
    return next(iter(values)) if len(values) == 1 else None


def contract_for(task, goal, question, today, *, allow_scope_reset=False):
    source = SOURCES[goal.outcome]
    query = dict(task.constraints.get(source, {}))
    selector = None
    if goal.scope in ('asset_code', 'asset_name', 'asset_id'):
        if not quoted_in(goal.selector, question):
            raise HTTPException(422, 'Имя или код оборудования должен быть указан в сообщении.')
        selector = Selector(kind=goal.scope, value=goal.selector.strip())
        if goal.scope == 'asset_id':
            UUID(selector.value)
        if source == 'equipment_find':
            for field in ('q', 'asset_code', 'accepted_maintenance', 'offset', 'limit'):
                query.pop(field, None)
            if selector.kind != 'asset_id':
                query.update(selector.arguments()['query'])
            elif not goal.accepted and goal.output != 'count':
                source = 'equipment_read'
                query = {}
            else:
                raise HTTPException(422, 'Укажите инвентарный код для фильтрации выборки.')
        task.equipment = None
        task.use_equipment_selection = False
    if allow_scope_reset:
        task.equipment = None
        task.use_equipment_selection = False
        if source == 'equipment_find':
            for field in ('q', 'asset_code', 'accepted_maintenance', 'offset', 'limit'):
                query.pop(field, None)
    output = 'types' if goal.outcome == 'maintenance_types' else goal.output
    if source == 'equipment_find' and goal.accepted:
        query['accepted_maintenance'] = goal.accepted
    if source == 'equipment_find' and not selector and task.equipment:
        inherited = {key: value for key, value in task.equipment.filters.items()
                     if key in ('asset_code', 'q', 'limit', 'offset')}
        if 'asset_code' in inherited:
            query.pop('q', None)
        query.update(inherited)
    if source == 'equipment_service_history':
        query.pop('offset', None)
        query['latest_only'] = True
    date_selection = _calendar_constraints(question, today) if source in ('tasks_find', 'equipment_service_history') else {}
    if goal.date and goal.date.kind == 'absolute':
        date_selection = goal.date.dates(query, today, question)
    if source == 'equipment_service_history' and 'on_days' in date_selection:
        raise HTTPException(422, 'Для истории укажите один день или период.')
    if source in ('tasks_find', 'equipment_service_history') and (goal.date or date_selection):
        dates = date_selection or goal.date.dates(query, today, question)
        for field in ('starts_on', 'ends_on', 'on_days'):
            query.pop(field, None)
        query.update(dates)
    equipment_scope = {}
    identity = None
    if source == 'tasks_find':
        for field in EQUIPMENT_SCOPE:
            query.pop(field, None)
        literal_state = _work_state(question)
        fields = {'state': literal_state or goal.work_state, 'sort': goal.sort, 'period': goal.period,
                  'maintenance_only': goal.maintenance_only, 'scheduled_only': goal.scheduled_only,
                  'unassigned_only': goal.unassigned_only}
        query.update({key: value for key, value in fields.items() if value is not None})
        if query.get('state') == 'assigned':
            query.pop('unassigned_only', None)
        if goal.accepted:
            equipment_scope['equipment_accepted_maintenance'] = goal.accepted
        if task.equipment:
            inherited = task.equipment.task_filters()
            if any(key in equipment_scope and equipment_scope[key] != value for key, value in inherited.items()):
                raise HTTPException(422, 'Уточните, какую группу оборудования проверять.')
            equipment_scope.update(inherited)
        if selector and selector.kind == 'asset_code':
            equipment_scope['equipment_asset_code'] = selector.value
        elif selector and selector.kind == 'asset_id':
            equipment_scope['equipment_id'] = str(UUID(selector.value))
    if source in EQUIPMENT_PATH and selector is None:
        if task.equipment and task.equipment.complete and len(task.equipment.members) == 1:
            identity = task.equipment.members[0]
        else:
            raise GoalClarification('Уточните, по какой единице оборудования выполнить поиск.')
    if source == 'maintenance_catalog_read':
        if goal.outcome == 'maintenance_types':
            query = {}
        else:
            if goal.type_position is not None:
                if goal.type_position > len(task.maintenance_types):
                    raise HTTPException(422, 'Уточните вид обслуживания.')
                query.pop('type_keys', None)
                query['type_codes'] = [task.maintenance_types[goal.type_position - 1]]
            elif goal.type_code:
                query.pop('type_codes', None)
                keys = type_keys(goal.type_code)
                if keys:
                    query['type_keys'] = keys
                else:
                    query.pop('type_keys', None)
                    query['type_codes'] = [goal.type_code]
    if source in ('equipment_find', 'tasks_find', 'maintenance_catalog_read'):
        if goal.limit is not None:
            query['limit'] = goal.limit
        if goal.offset is not None:
            query['offset'] = goal.offset
    return ReadContract(source=source, outcome=goal.outcome, output=output, query=query,
                        selector=selector, equipment_id=identity, equipment_scope=equipment_scope)
