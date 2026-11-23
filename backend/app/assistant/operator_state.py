"""Private, versioned state of an ERP task and its evidence-backed selection."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


COLLECTIONS = {
    'tasks_find': {'period', 'state', 'active_only', 'q', 'scheduled_only', 'equipment_id', 'equipment_ids',
                   'equipment_q', 'equipment_asset_code',
                   'unfinished_only', 'starts_on', 'ends_on', 'maintenance_only', 'unassigned_only',
                   'type_keys', 'type_codes', 'equipment_accepted_maintenance', 'on_days', 'limit', 'offset', 'sort'},
    'equipment_find': {'q', 'asset_code', 'accepted_maintenance', 'limit', 'offset'},
    'maintenance_catalog_read': {'type_codes', 'type_keys', 'limit', 'offset'},
    'equipment_service_history': {'latest_only', 'starts_on', 'ends_on', 'limit', 'offset'},
}
ROWS = {'tasks_find': ('task', 'id'), 'task_read': ('task', 'id'),
        'equipment_find': ('equipment', 'equipment_id'), 'equipment_read': ('equipment', 'equipment_id'),
        'staff_find': ('staff', 'user_id'), 'staff_read': ('staff', 'user_id')}
Constraint = str | bool | int | list[str]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TaskDelta(StrictModel):
    mode: Literal['continue', 'new', 'restore'] = 'continue'
    restore_task_id: UUID | None = None
    operation: Literal['read', 'change'] = 'read'
    source: Literal['', 'tasks_find', 'equipment_find', 'maintenance_catalog_read', 'equipment_service_history'] = ''
    set: dict[str, Constraint] = Field(default_factory=dict, max_length=20)
    clear: list[str] = Field(default_factory=list, max_length=20)
    use_equipment_selection: bool = False
    clear_equipment_selection: bool = False


class Entity(StrictModel):
    kind: Literal['equipment', 'task', 'staff']
    identity: UUID


class EquipmentSelection(StrictModel):
    receipt: str
    filters: dict[str, Constraint]
    members: list[UUID] = Field(max_length=25)
    complete: bool

    def task_filters(self):
        # This predicate is re-evaluated by SQL under the caller's current rights.
        keys = {'accepted_maintenance': 'equipment_accepted_maintenance', 'q': 'equipment_q',
                'asset_code': 'equipment_asset_code'}
        predicates = {target: self.filters[key] for key, target in keys.items() if key in self.filters}
        if predicates and not (self.filters.get('limit') or self.filters.get('offset')):
            return predicates
        if self.complete and self.members:
            return {'equipment_ids': [str(key) for key in self.members]}
        raise HTTPException(422, 'Выборка оборудования пуста или показана частично. Уточните область поиска.')


class TaskState(StrictModel):
    version: Literal[1] = 1
    task_id: UUID
    original_request: str
    operation: Literal['read', 'change'] = 'read'
    constraints: dict[str, dict[str, Constraint]] = Field(default_factory=dict)
    equipment: EquipmentSelection | None = None
    use_equipment_selection: bool = False
    references: dict[str, list[Entity]] = Field(default_factory=dict)

    def apply(self, delta):
        allowed = COLLECTIONS.get(delta.source, set())
        if (set(delta.set) | set(delta.clear)) - allowed or set(delta.set) & set(delta.clear):
            raise HTTPException(422, 'Измените только известные ограничения одного источника.')
        if delta.source:
            stable = self.constraints.setdefault(delta.source, {})
            for key in delta.clear:
                stable.pop(key, None)
            stable.update(delta.set)
        self.operation = delta.operation
        if delta.clear_equipment_selection and delta.use_equipment_selection:
            raise HTTPException(422, 'Укажите один способ работы с выборкой оборудования.')
        if delta.clear_equipment_selection:
            self.use_equipment_selection = False
            self.equipment = None
        elif delta.use_equipment_selection or (delta.source == 'tasks_find' and self.equipment):
            self.use_equipment_selection = True

    def bind(self, name, arguments):
        if name not in COLLECTIONS:
            return arguments
        constraints = dict(self.constraints.get(name, {}))
        query = arguments.get('query', {})
        if not isinstance(query, dict):
            raise HTTPException(422, 'Ожидается объект query.')
        if name == 'tasks_find' and self.use_equipment_selection:
            if self.equipment is None:
                raise HTTPException(422, 'Сначала прочитайте выборку оборудования.')
            inherited = self.equipment.task_filters()
            constraints = self._canonical_scope(constraints, inherited)
            query = self._canonical_scope(query, inherited)
            constraints.update(inherited)
        if any(key in query and query[key] != value for key, value in constraints.items()):
            raise HTTPException(422, 'Аргументы противоречат сохранённым ограничениям.')
        return {**arguments, 'query': {**query, **constraints}}

    def _canonical_scope(self, values, inherited):
        members = {str(key) for key in self.equipment.members}
        result = dict(values)
        for key in ('equipment_id', 'equipment_ids', 'equipment_accepted_maintenance', 'equipment_q',
                    'equipment_asset_code'):
            if key not in result:
                continue
            value = result.pop(key)
            exact_id = isinstance(value, str) and members == {value}
            exact_ids = (isinstance(value, list) and all(isinstance(item, str) for item in value)
                         and set(value) == members)
            explicit_members = self.equipment.complete and (key == 'equipment_id' and exact_id or
                                                            key == 'equipment_ids' and exact_ids)
            if key in inherited and value == inherited[key] or explicit_members:
                continue
            raise HTTPException(422, 'Область нарядов противоречит сохранённой выборке оборудования.')
        return result

    def observe(self, proof):
        name, value = proof['tool'], proof['result']
        if not proof['retained'] or not isinstance(value, dict):
            return
        if name in ROWS:
            kind, field = ROWS[name]
            self.references[kind] = [Entity(kind=kind, identity=row[field])
                                     for row in value.get('items', []) if row.get(field)]
        if name == 'equipment_find':
            query = proof['arguments'].get('query', {})
            stable = dict(self.constraints.get(name, {}))
            filters = {key: query[key] for key in ('q', 'asset_code', 'accepted_maintenance', 'offset') if query.get(key)}
            if 'q' in filters and not filters['q'].strip():
                filters.pop('q')
            if stable.get('limit'):
                filters['limit'] = stable['limit']
            self.equipment = EquipmentSelection(receipt=proof['id'], filters=filters,
                members=[entity.identity for entity in self.references['equipment']],
                complete=proof['complete'] or
                (bool(stable.get('limit')) and len(value['items']) == stable['limit'] and not query.get('offset')))

    def accept_query(self, name, raw):
        """Retain the actual successful filters. Transport defaults stay out of the task."""
        if name in COLLECTIONS:
            query = raw.get('query', {})
            self.constraints.setdefault(name, {}).update(
                {key: value for key, value in query.items() if key in COLLECTIONS[name] and value is not None})
