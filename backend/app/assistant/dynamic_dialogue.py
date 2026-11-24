"""Opt-in model-driven tool loop using the same role, transport and action policy as v3."""
from datetime import date, timedelta
from functools import lru_cache
import json
import re
from time import monotonic
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, create_model

from app.schemas.assistant import GoalSpec, ToolSelection

from . import service, workflow
from .intents import prohibits_changes
from .inventory_report import label
from .maintenance_dialogue import ASSIGN_COMMAND, WORK_STATUS, _task_fact, _task_line
from .tools import invoke, validate_arguments


TOOLS = {
    'equipment_find': 'Реестр оборудования. query: asset_code, q, accepted_maintenance (none|present), limit, offset.',
    'equipment_read': 'Карточка оборудования. path: equipment_id.',
    'equipment_service_history': 'Фактические принятые отчёты. path: equipment_id. query: latest_only, starts_on, ends_on, limit, offset.',
    'maintenance_catalog_read': 'Виды и операции ТО. query: type_codes (точный код), type_keys (например то1), limit, offset. Список видов: presentation=types.',
    'regulations_read': 'Регламенты оборудования. path: equipment_id.',
    'tasks_find': 'Наряды по плановой дате. query: period (all|upcoming|overdue|undated), state, starts_on, ends_on, on_days, '
                  'equipment_id, equipment_accepted_maintenance, maintenance_only, unfinished_only, scheduled_only, unassigned_only, q, type_codes, limit, offset.',
    'task_read': 'Карточка наряда. path: task_id.',
    'assignment_context': 'Проверяемые ограничения подбора. path: task_id.',
    'assignment_preview': 'Неразрушающий расчёт состава. path: task_id. body: start_local, end_local, expected_revision.',
    'task_assign': 'Подготовить карточку назначения. Только receipt текущего успешного assignment_preview, без аргументов.',
}
SOURCE_NAMES = {
    'equipment_find': 'реестр оборудования', 'equipment_read': 'карточка оборудования',
    'equipment_service_history': 'отчёты и решения о приёмке', 'maintenance_catalog_read': 'действующие регламенты ТО',
    'regulations_read': 'регламенты оборудования', 'tasks_find': 'реестр нарядов', 'task_read': 'карточка наряда',
    'assignment_context': 'ограничения наряда', 'assignment_preview': 'серверный расчёт назначения',
}
CLARIFICATIONS = {
    'target': 'Укажите код оборудования или идентификатор наряда.',
    'date': 'На какую дату или период проверить данные?',
    'draft_policy': 'Считать ближайшим любой запланированный наряд, включая черновики, или только назначенные работы?',
    'scope': 'Уточните, какое оборудование или какие работы проверить.',
    'unverified': 'Не удалось подтвердить ответ доступным источником текущего объекта.',
}
MAX_STEPS = 5
PAGE_SIZE = 25


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')

    tool: str = Field(max_length=75)
    arguments_json: str = Field(max_length=2200)
    presentation: Literal['continue', 'items', 'count', 'types']
    receipt: str = Field(max_length=12)
    clarification: Literal['', 'target', 'date', 'draft_policy', 'scope', 'unverified']


@lru_cache(maxsize=16)
def _decision_schema(tools):
    names = (*tools, 'reply', 'clarify')
    return create_model('Decision', __base__=Decision, tool=(Literal[names], ...))


def prepare(execution, thread, turn, history, files, sent_files, question, clock):
    execution.check()
    execution.thread, execution.turn = thread, turn
    execution.history, execution.files, execution.sent_files = history, files, sent_files
    execution.question, execution.clock = question, clock
    execution.read_only = not re.search(ASSIGN_COMMAND, question.strip().casefold()) or prohibits_changes(question)
    execution.tools = {name: tool for name, tool in execution.tools.items()
                       if name in TOOLS and (tool.mode == 'read' or not execution.read_only)}
    execution.client = (execution.app.state.assistant_provider_factory()
                        if hasattr(execution.app.state, 'assistant_provider_factory') else service.provider(turn['model_selection']))
    seconds = ((turn['deadline_at'] - service.now()).total_seconds() if turn.get('deadline_at')
               else service.turn_timeout_seconds(turn['model_selection']))
    execution.execution_deadline = monotonic() + max(0, seconds)
    execution.context, execution.books, execution.set_modes = {}, [], None
    if execution.state:
        if execution.state['scope'] != execution.scope or not execution.state.get('llm_dynamic'):
            raise HTTPException(403, 'Контекст поручения изменился')
        return
    goal = GoalSpec(id='dynamic', title='Данные текущего объекта', tool='', kind='read', required_evidence='saved_data')
    execution.state = workflow.create_plan(ToolSelection(tools=[], goals=[goal]), question, execution.tools, execution.scope)
    execution.state['goals'][0].update(status='planned', reason=None)
    execution.state.update(llm_dynamic=True, root_turn_id=str(execution.turn_id),
                           read_only=execution.read_only, display_plan=False)
    execution.save()


def _pick(value, fields):
    return {field: value[field] for field in fields if field in value}


def _project(name, value):
    if isinstance(value, list):
        return {'items': [_pick(row, ('binding_id', 'id', 'regulation_edition_id', 'maintenanceRuleId', 'title',
                                    'operationTitle', 'operation_title', 'active', 'publication_status'))
                          for row in value[:PAGE_SIZE] if isinstance(row, dict)], 'total': len(value)}
    source = _pick(value, ('status', 'code', 'total', 'offset', 'limit', 'filters', 'types', 'history_basis',
                           'matched_reports', 'actual_date_unknown_count', 'actual_date_conflict', 'complete', 'timezone'))
    if name == 'tasks_find':
        source['items'] = [_task_fact(item) for item in value['items']]
    elif name == 'equipment_find':
        source['items'] = [_pick(item, ('equipment_id', 'asset_code', 'name', 'location', 'status')) for item in value['items']]
    elif name == 'maintenance_catalog_read':
        source['items'] = [_pick(item, ('type_name', 'type_code', 'code', 'title')) for item in value['items']]
    elif name == 'equipment_service_history':
        source['items'] = [_pick(item, ('report_id', 'task_id', 'performed_at', 'accepted_at', 'actual_date_verified'))
                           for item in value['items']]
        if value.get('latest_only'):
            source['total'] = len(source['items'])
    elif name == 'task_read':
        source['items'] = [_task_fact(value['task'])]
    elif name == 'equipment_read':
        source['items'] = [_pick(value, ('equipment_id', 'asset_code', 'name', 'location', 'status'))]
    elif name == 'assignment_context':
        source.update(_pick(value, ('expectedRevision', 'defaultStartLocal', 'defaultEndLocal', 'explanation',
                                    'crewSize', 'requiredQualifications')))
    elif name == 'assignment_preview':
        source.update(_pick(value, ('explanation', 'selectedWorkers', 'startAt', 'endAt', 'command', 'crewId')))
    elif name == 'regulations_read':
        return _project(name, value.get('items', value.get('configurations', [])))
    return source


def _history(execution):
    recent = []
    for row in reversed(execution.history):
        saved = row.get('workflow') or {}
        if row['status'] != 'completed' or saved and saved.get('scope') != execution.scope:
            continue
        proofs = [dict(tool=p['tool'], arguments=p['arguments'], result=p['result'])
                  for p in saved.get('evidence', []) if p.get('retained') and p['tool'] in execution.tools
                  and p.get('scope') == execution.scope][-2:]
        recent.append(dict(question=row['content'][:1200], answer=(row['answer'] or '')[:800],
                           evidence=[{**p, 'result': _small(p['result'])} for p in proofs]))
    return recent


def _small(value):
    if isinstance(value, dict) and isinstance(value.get('items'), list):
        return {**value, 'items': value['items'][:4], 'shown_to_model': min(len(value['items']), 4)}
    return value


def _blocked(goal, reason, text):
    goal.update(status='blocked', reason=reason, response=text, response_source='server_workflow')


async def _read(execution, goal, tool, arguments):
    if not isinstance(arguments, dict) or 'view' in arguments:
        raise HTTPException(422, 'Недопустимый запрос источника')
    if tool.name in ('tasks_find', 'equipment_find', 'maintenance_catalog_read', 'equipment_service_history'):
        if arguments and not {'query', 'path', 'body'}.intersection(arguments):
            arguments = {'query': arguments}
        query = arguments.get('query', {})
        if not isinstance(query, dict) or type(query.get('limit', PAGE_SIZE)) is not int:
            raise HTTPException(422, 'Недопустимый размер страницы')
        arguments = {**arguments, 'query': {**query, 'limit': min(PAGE_SIZE, query.get('limit', PAGE_SIZE))}}
    checked = validate_arguments(execution.app, tool, arguments)
    if any(proof.get('retained') and proof['tool'] == tool.name and proof['arguments'] == checked
           for proof in execution.state['evidence'] if proof.get('dynamic_turn') == str(execution.turn_id)):
        raise HTTPException(409, 'Эта выборка уже проверена')
    execution.check()
    service.progress(execution.app, execution.turn_id, execution.trace, tool.name)
    started = monotonic()
    value = await invoke(execution.app, tool, checked, execution.headers)
    projected = _project(tool.name, value)
    proof = workflow.record_result(execution.state, goal, tool.name, checked, projected, elapsed=monotonic()-started)
    proof['dynamic_turn'] = str(execution.turn_id)
    execution.trace.append(dict(tool=tool.name, status='completed', arguments=checked,
                                result=service.bounded(projected), at=workflow.timestamp()))
    execution.save()
    return proof


def _equipment_line(row):
    states = {'active': 'в эксплуатации', 'retired': 'выведено из эксплуатации', 'under_repair': 'в ремонте'}
    return ' · '.join(label(row[key]) for key in ('asset_code', 'name', 'location', 'equipment_id') if row.get(key)) + (
        ' · ' + states.get(row['status'], label(row['status'])) if row.get('status') else '')


def _lines(source, value, presentation):
    if presentation == 'types' and source == 'maintenance_catalog_read':
        return [f'{label(row["type_name"])} · операций {row["operations"]}' for row in value.get('types', [])]
    if presentation == 'count' and type(value.get('total')) is int:
        return [f'Найдено **{value["total"]}**.']
    if presentation not in ('items', 'continue'):
        return None
    rows = value.get('items', [])
    if source in ('equipment_find', 'equipment_read'):
        return [_equipment_line(row) for row in rows]
    if source in ('tasks_find', 'task_read'):
        return [_task_line(row, people=True) + ' · ' + WORK_STATUS.get(row['state'], label(row['state'])) for row in rows]
    if source == 'maintenance_catalog_read':
        return [f'{label(row["type_name"])} · {label(row["code"])} — {label(row["title"])}' for row in rows]
    if source == 'equipment_service_history':
        return [f'Принятый отчёт {row["report_id"]} · '
                + (label(row['performed_at']) if row['actual_date_verified'] else 'фактическая дата неизвестна') for row in rows]
    if source == 'regulations_read':
        return [' · '.join(label(v) for v in row.values()) for row in rows if row]
    if source == 'assignment_preview' and value.get('status') == 'ok':
        people = ', '.join(label(person['name']) for person in value['selectedWorkers'])
        return [f'{people} · {value["startAt"]} — {value["endAt"]}. Подбор проверен по наряду.']
    return [label(value['explanation'])] if value.get('explanation') else None


def _deliver(execution, goal, proof, presentation):
    if not execution.read_only or not proof or not proof['retained'] or not isinstance(proof['result'], dict):
        return False
    value, source = proof['result'], proof['tool']
    if (rows := _lines(source, value, presentation)) is None:
        return False
    if not rows and (type(value.get('total')) is not int or value['total'] != 0):
        return False
    scope = value.get('history_basis')
    notes = []
    if scope:
        notes.append('Обслуженность проверена по принятым в системе отчётам ТО' + (
            ' в доступной истории назначений.' if scope['visibility'] == 'assigned_orders' else ' текущего объекта.'))
    if value.get('filters', {}).get('starts_on'):
        filters = value['filters']
        notes.append('Период ' + ' — '.join(dict.fromkeys(filter(None, (filters['starts_on'], filters.get('ends_on'))))) + '.')
    if presentation == 'items' and rows and type(value.get('total')) is int and value['total'] > len(rows):
        notes.append(f'Показано {len(rows)} из {value["total"]}.')
    source_name = SOURCE_NAMES[source]
    rendered = '\n'.join(f'{index}. {row}' for index, row in enumerate(rows, 1)) if len(rows) > 1 else (
        rows[0] if rows else 'В выбранной области записей нет.')
    answer = '\n\n'.join([rendered, *notes, f'Источник — {source_name} ({source}).'])
    read_limit = proof['arguments'].get('query', {}).get('limit')
    complete = (proof['complete'] or presentation in ('count', 'types') and proof['limitations'] == ['page_only']
                or presentation == 'items' and read_limit is not None and read_limit < PAGE_SIZE
                and len(rows) == read_limit and proof['limitations'] == ['page_only'])
    if complete and not proof['complete']:
        # Certify the requested projection of the receipt. The underlying page remains partial.
        projection = _pick(value, ('total', 'types', 'filters', 'history_basis', 'offset', 'limit'))
        if presentation == 'items':
            projection['selected_items'] = value['items']
        workflow.record_result(execution.state, goal, source, proof['arguments'], projection, count_call=False)
    if value.get('status') in ('needs_input', 'unavailable', 'blocked'):
        _blocked(goal, 'domain_blocker', answer)
    else:
        goal.update(tool=source, mode='read', status='completed' if complete else 'partial',
                    reason=None if complete else 'result_incomplete', response=answer, response_source='server_workflow')
    return True


async def _propose(execution, goal, proof):
    if execution.read_only or not proof or proof['tool'] != 'assignment_preview' or not proof['complete']:
        raise HTTPException(403, 'Подготовка назначения требует явного поручения и проверенного расчёта')
    preview = proof['result']
    if preview.get('status') != 'ok' or not preview.get('command') or not preview.get('selectedWorkers'):
        raise HTTPException(409, 'Состав не подтверждён')
    path = proof['arguments']['path']
    body = {**preview['command'], 'crew_id': preview.get('crewId')}
    people = ', '.join(label(item['name']) for item in preview['selectedWorkers'])
    description = f'Назначение на наряд {path["task_id"]} · {people} · {preview["startAt"]} — {preview["endAt"]}'
    execution.check()
    with execution.app.state.factory() as session:
        action = await service.propose(execution.app, session, execution.principal, execution.thread,
            execution.tools['task_assign'], dict(path=path, body=body), description, execution.headers, execution.turn_id,
            workflow_goal_id=goal['id'], workflow_root_turn_id=execution.state['root_turn_id'])
    goal.update(tool='task_assign', mode='write', kind='change', response_source='server_workflow',
                response=f'{description}. Проверьте и подтвердите карточку назначения.')
    workflow.record_result(execution.state, goal, 'task_assign', dict(path=path),
                           dict(status='awaiting_confirmation'), action_id=action['action_id'])
    execution.trace.append(dict(tool='task_assign', status='proposed', at=workflow.timestamp()))


async def execute(execution, goal):
    if goal.get('action_id') or goal.get('status') in ('completed', 'cancelled'):
        return
    if execution.files:
        _blocked(goal, 'attachments_unsupported', 'Экспериментальный режим работает с реестрами. Для вложений выберите штатный режим.')
        return
    goal.update(status='running', reason=None)
    instruction = (service.PROMPTS / 'llm-dynamic.md').read_text(encoding='utf-8')
    context = dict(question=execution.question, history=_history(execution), clock=execution.clock,
                   tomorrow=(date.fromisoformat(execution.clock['local_date']) + timedelta(days=1)).isoformat(),
                   role=execution.scope['role'], tools={name: TOOLS[name] for name in execution.tools})
    errors = []
    schema = _decision_schema(tuple(execution.tools))
    for _ in range(MAX_STEPS):
        execution.check()
        observed = {p['id']: p for p in execution.state['evidence'] if p.get('dynamic_turn') == str(execution.turn_id)}
        payload = dict(context, results=[dict(receipt=key, tool=p['tool'], arguments=p['arguments'],
                       result=_small(p['result'])) for key, p in observed.items() if p['retained']], failures=errors)
        decision = await execution.infer([dict(role='system', content=instruction),
                                         dict(role='user', content=service.dump(payload))], schema, 700)
        proof = observed.get(decision.receipt)
        if decision.tool == 'clarify':
            _blocked(goal, 'dynamic_clarification', CLARIFICATIONS.get(decision.clarification, CLARIFICATIONS['unverified']))
            return
        if decision.tool == 'reply':
            if _deliver(execution, goal, proof, decision.presentation):
                return
            errors.append({'tool': 'reply', 'status': 'unverified_receipt'})
            continue
        try:
            tool = execution.tools.get(decision.tool)
            if not tool:
                raise HTTPException(403, 'Инструмент недоступен')
            if tool.name == 'task_assign':
                await _propose(execution, goal, proof)
                return
            arguments = json.loads(decision.arguments_json or '{}')
            result = await _read(execution, goal, tool, arguments)
            if decision.presentation != 'continue' and _deliver(execution, goal, result, decision.presentation):
                return
        except (HTTPException, ValueError) as exc:
            status = exc.status_code if isinstance(exc, HTTPException) else 422
            error = {'tool': decision.tool, 'status': status}
            if status == 422:
                error['detail'] = (str(exc.detail)[:220] if isinstance(exc, HTTPException)
                                   else 'arguments_json must contain a JSON object.')
            errors.append(error)
            if decision.tool in execution.tools and execution.tools[decision.tool].mode == 'read':
                workflow.record_read_failure(execution.state, goal, decision.tool, {}, status)
            execution.trace.append(dict(tool=decision.tool if decision.tool in execution.tools else '__dynamic_denied',
                                        status='denied', code=status, at=workflow.timestamp()))
    _blocked(goal, 'dynamic_budget_or_evidence', CLARIFICATIONS['unverified'])
