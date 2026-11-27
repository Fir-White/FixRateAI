"""LLM chooses a step. The ERP validates, previews, executes and verifies."""
from datetime import date, datetime, timedelta
from functools import lru_cache
import json
import re
from time import monotonic
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field, create_model

from app.schemas.assistant import GoalSpec, ToolSelection

from . import dynamic_dialogue as presentation
from . import service, workflow
from .action_outcomes import SUPPORTED
from .fact_presenter import present_facts
from .intents import mutation_command_requested, primary_document_requested, prohibits_changes
from .operator_contract import EQUIPMENT_PATH, GoalClarification, ReadContract, ReadGoal, contract_for, quoted_in
from .operator_state import COLLECTIONS, ROWS, StrictModel, TaskDelta, TaskState
from .tools import describe, invoke, validate_arguments


CORE = frozenset(presentation.TOOLS)
DISCOVERABLE_READS = {'assignment_prepare', 'staff_find', 'staff_read', 'task_acceptance_evidence'}
FACT_READS = {
    'calendar_evidence', 'calendar_read', 'checklist_catalog', 'components_read', 'draft_changes', 'draft_occurrences',
    'draft_policy', 'draft_read', 'drafts_find', 'equipment_executions', 'incidents_list', 'operation_read',
    'operations_list', 'overview_read', 'planning_context', 'plans_list', 'portfolio_list', 'regulations_list',
    'schedule_matrix', 'staff_calendar', 'task_attempts', 'tasks_analyze', 'work_order_analytics', 'workforce_read',
}
TARGET_KIND = {'task_id': 'task', 'equipment_id': 'equipment', 'user_id': 'staff'}
ASSIGNMENT_READS = {'assignment_context', 'assignment_preview', 'assignment_prepare'}
EXTRA_LABELS = {'staff_find': 'поиск сотрудников', 'staff_read': 'карточка сотрудника',
                'task_acceptance_evidence': 'материалы приёмки', 'assignment_prepare': 'серверный расчёт назначения'}
END_STATUSES = {'completed', 'partial', 'blocked', 'awaiting_confirmation', 'cancelled'}


def exposure(tool):
    if tool.mode == 'read' and tool.name in CORE | DISCOVERABLE_READS | FACT_READS:
        return 'read'
    if tool.name in SUPPORTED and not tool.secrets and not tool.optional_secrets:
        return 'confirmation'
    return 'unavailable'


class Decision(StrictModel):
    tool: str = Field(max_length=75)
    result_source: str = Field(default='', max_length=75)
    arguments_json: str = Field(default='{}', max_length=4500)
    task_delta: TaskDelta | None = None
    read_goal: ReadGoal | None = None
    receipt: str = Field(default='', max_length=12)
    presentation: Literal['continue', 'items', 'count', 'types', 'instructions'] = 'continue'
    clarification: Literal['', 'target', 'date', 'draft_policy', 'scope', 'unverified'] = ''


@lru_cache(maxsize=64)
def _schema(names, initial):
    fields = {'tool': (Literal[(*names, 'reply', 'clarify', 'discover')], ...),
              'arguments_json': (str, ...), 'presentation': (Decision.model_fields['presentation'].annotation, ...)}
    if initial:
        fields.update(read_goal=(ReadGoal | None, ...), task_delta=(TaskDelta | None, None))
    return create_model('OperatorPlan' if initial else 'OperatorStep', __base__=Decision, **fields)


class ScopeReview(StrictModel):
    independent: bool


@lru_cache(maxsize=4)
def _prompt(name):
    return (service.PROMPTS / name).read_text(encoding='utf-8')


def prepare(execution, thread, turn, history, files, sent_files, question, clock):
    execution.check()
    execution.thread, execution.turn = thread, turn
    execution.history, execution.files, execution.sent_files = history, files, sent_files
    execution.question, execution.clock = question, clock
    execution.read_only = True
    execution.tools = {key: tool for key, tool in execution.tools.items() if exposure(tool) != 'unavailable'}
    execution.client = (execution.app.state.assistant_provider_factory()
                        if hasattr(execution.app.state, 'assistant_provider_factory') else service.provider(turn['model_selection']))
    seconds = ((turn['deadline_at'] - service.now()).total_seconds() if turn.get('deadline_at')
               else service.turn_timeout_seconds(turn['model_selection']))
    execution.execution_deadline = monotonic() + max(0, seconds)
    execution.context, execution.books, execution.set_modes = {}, [], None
    if execution.state:
        if execution.state['scope'] != execution.scope or not execution.state.get('erp_operator'):
            raise HTTPException(403, 'Контекст поручения изменился')
        operator = execution.state['erp_operator']
        if operator.get('running_turn') != str(execution.turn_id):
            operator.update(attempts=0, reserved_output_tokens=0, errors=[], running_turn=str(execution.turn_id))
        return
    goal = GoalSpec(id='operator', title='Поручение по текущему объекту', tool='', kind='read', required_evidence='saved_data')
    execution.state = workflow.create_plan(ToolSelection(tools=[], goals=[goal]), question, execution.tools, execution.scope)
    execution.state['goals'][0].update(status='planned', reason=None)
    execution.state.update(erp_operator={'attempts': 0, 'reserved_output_tokens': 0, 'errors': [], 'discovered': [],
                                        'running_turn': str(execution.turn_id)},
                           root_turn_id=str(execution.turn_id), read_only=True, display_plan=True)
    execution.save()


def _prior_tasks(execution):
    result = {}
    for turn in execution.history:
        previous = turn.get('workflow') or {}
        task = (previous.get('erp_operator') or {}).get('task')
        if task and turn['status'] == 'completed' and previous.get('scope') == execution.scope:
            saved = TaskState.model_validate(task)
            if saved.equipment is None:
                earlier_card = next((proof for proof in reversed(previous.get('evidence', ()))
                                     if proof['tool'] == 'equipment_read' and proof.get('complete')), None)
                if earlier_card:
                    saved.observe(earlier_card)
            result.setdefault(str(saved.task_id), saved)
    return result


def _arguments(decision):
    args = json.loads(decision.arguments_json or '{}')
    if not isinstance(args, dict):
        raise HTTPException(422, 'Ожидается JSON-объект аргументов.')
    collection = COLLECTIONS.get(decision.tool, set())
    if args and set(args) <= collection:
        args = {'query': args}
    if set(args) - {'path', 'query', 'body'}:
        raise HTTPException(422, 'Используйте только path, query и body.')
    args = {key: value for key, value in args.items() if value is not None}
    if any(not isinstance(value, dict) for value in args.values()):
        raise HTTPException(422, 'Параметры path, query и body должны быть объектами.')
    if 'query' in args:
        args['query'] = {key: value for key, value in args['query'].items() if value is not None}
    return args


def _start_task(execution, goal, decision, tasks):
    delta = decision.task_delta or TaskDelta()
    task = None
    if delta.mode == 'restore':
        task = tasks.get(str(delta.restore_task_id))
        if task is None:
            raise HTTPException(422, 'Поручение для продолжения не найдено.')
    elif delta.mode == 'continue':
        task = next(iter(tasks.values()), None)
    if task is None:
        task = TaskState(task_id=execution.turn_id, original_request=execution.question)
    result_source = (decision.result_source if decision.result_source in execution.tools else '') or delta.source or decision.tool
    if delta.operation == 'read' and decision.tool not in ('clarify', 'discover'):
        source = execution.tools.get(result_source)
        if source is None or source.mode != 'read':
            raise HTTPException(422, 'Укажите доступный источник, который должен подтвердить результат.')
        if delta.source and delta.source != source.name and delta.source != 'equipment_find':
            raise HTTPException(422, 'Привяжите запрошенные ограничения к нужному источнику.')
        goal['title'] = source.title
    task.apply(delta)
    if result_source == 'tasks_find' and task.equipment and not delta.clear_equipment_selection:
        task.use_equipment_selection = True
    if delta.source in ('tasks_find', 'equipment_find', 'maintenance_catalog_read'):
        validate_arguments(execution.app, execution.tools[delta.source], task.bind(delta.source, {}))
    execution.state['erp_operator']['task'] = task.model_dump(mode='json')
    execution.state['erp_operator']['result_source'] = result_source if result_source in execution.tools else ''
    return task


def _small(value):
    return service.compact(presentation._small(value) if isinstance(value, dict) else value, 3200)


def _project(name, value):
    if name in FACT_READS:
        return workflow.safe_evidence(value)
    if name == 'task_read':
        result = presentation._project(name, value)
        result.update(presentation._pick(value, ('allowedActions',)))
        result.update(presentation._pick(value['task'], ('instructions', 'methodologyRef')))
        if value.get('execution'):
            result['execution'] = presentation._pick(value['execution'], ('id', 'state', 'checklist'))
        return result
    if name in presentation.SOURCE_NAMES:
        result = presentation._project(name, value)
        if name == 'tasks_find':
            result['period'] = value['period']
            for row, source in zip(result['items'], value['items'], strict=True):
                row['matchedAt'] = source['matchedAt']
        if name == 'equipment_service_history':
            result.update(presentation._pick(value, ('equipment_id', 'only_accepted', 'latest_only', 'starts_on', 'ends_on')))
        if name == 'maintenance_catalog_read':
            result.update(presentation._pick(value, ('type_codes', 'type_keys')))
        return result
    if name == 'assignment_prepare':
        return presentation._project('assignment_preview', value)
    if name == 'staff_find':
        return {**value, 'items': [presentation._pick(row, ('user_id', 'full_name', 'role'))
                                   for row in value.get('items', [])]}
    if name == 'staff_read':
        return {'items': [presentation._pick(value, ('user_id', 'full_name', 'role'))]}
    return presentation._pick(value, ('task_id', 'revision', 'execution_id', 'missing_materials', 'acceptance_blocks',
                                      'submission_blocks', 'ready', 'submission_ready', 'task_state', 'report_state'))


async def _read(execution, goal, task, tool, arguments, *, semantic=False, observe=True):
    if tool.name in ASSIGNMENT_READS and execution.state['erp_operator'].get('mutation_target'):
        arguments = _bind_assignment(execution, tool.name, arguments)
    bound = arguments if semantic else task.bind(tool.name, arguments)
    if tool.name in COLLECTIONS:
        query = bound['query']
        limit = query.get('limit', presentation.PAGE_SIZE)
        if type(limit) is not int or not 1 <= limit <= presentation.PAGE_SIZE:
            raise HTTPException(422, 'Размер страницы от 1 до 25. Для полного перечня используйте страницы.')
        bound['query'] = {**query, 'limit': limit}
    checked = validate_arguments(execution.app, tool, bound)
    previous = next((proof for proof in _observed(execution).values() if proof['tool'] == tool.name and
                     proof['arguments'] == checked and proof.get('retained')), None)
    if previous:
        if semantic:
            return previous
        raise HTTPException(409, 'Эта выборка уже проверена. Используйте её receipt.')
    execution.check()
    service.progress(execution.app, execution.turn_id, execution.trace, tool.name)
    started = monotonic()
    value = _project(tool.name, await invoke(execution.app, tool, checked, execution.headers))
    proof = workflow.record_result(execution.state, goal, tool.name, checked, value, elapsed=monotonic() - started)
    proof['operator_turn'] = str(execution.turn_id)
    if not semantic:
        task.accept_query(tool.name, arguments)
    if observe:
        task.observe(proof)
    execution.trace.append(dict(tool=tool.name, status='completed', arguments=checked,
                                result=service.bounded(value), at=workflow.timestamp()))
    return proof


def _observed(execution):
    return {p['id']: p for p in execution.state['evidence'] if p.get('operator_turn') == str(execution.turn_id)}


def _can_prepare(execution, task):
    return task.operation == 'change' and _explicit_change(execution.question)


def _explicit_change(request):
    # This independent server check is a write safety gate, outside model routing.
    from .semantic_plan import QUOTED

    question = QUOTED.sub(' ', request)
    return not prohibits_changes(question) and mutation_command_requested(question.replace(',', '.'))


def _verified_target(arguments, proof):
    path = arguments.get('path', {})
    if not path:
        return
    if not proof or not proof.get('retained') or not proof.get('complete'):
        raise HTTPException(422, 'Получите актуальную карточку перед подготовкой изменения.')
    for key, identity in path.items():
        kind, field = ROWS.get(proof['tool'], (None, None))
        rows = proof['result'].get('items', [])
        if (not proof['tool'].endswith('_read') or TARGET_KIND.get(key) != kind or
                not any(str(row.get(field)) == str(identity) for row in rows)):
            raise HTTPException(422, 'Карточка не подтверждает целевую запись.')


async def _propose(execution, goal, task, tool, proof, arguments):
    if not _can_prepare(execution, task):
        raise HTTPException(403, 'Для подготовки изменения нужно явное поручение пользователя.')
    execution.read_only = execution.state['read_only'] = False
    if tool.name == 'task_assign':
        # Only the server preview may supply assignment participants and dates.
        if arguments or not proof or proof['tool'] not in ('assignment_preview', 'assignment_prepare'):
            raise HTTPException(422, 'Используйте receipt расчёта назначения без новых параметров.')
        _guard_mutation_subject(execution, proof['arguments']['path'])
        if execution.state['erp_operator'].get('mutation_target') and proof['result'].get('status') == 'ok':
            selected = _selected_work(execution)
            window = _guard_assignment_window(execution, proof['result']['startAt'], proof['result']['endAt'])
            planned = (selected.get('scheduledStart'), selected.get('scheduledEnd'))
            if all(planned) and window != tuple(_local_instant(value, execution.scope['timezone']) for value in planned):
                raise HTTPException(422, 'Расчёт назначения изменил проверенное время наряда.')
        await presentation._propose(execution, goal, {**proof, 'tool': 'assignment_preview'})
        goal['title'] = tool.title
        return
    if tool.before:
        _verified_target(arguments, proof)
    _guard_mutation_subject(execution, arguments.get('path', {}))
    execution.check()
    with execution.app.state.factory() as session:
        action = await service.propose(execution.app, session, execution.principal, execution.thread, tool,
            arguments, tool.title, execution.headers, execution.turn_id, workflow_goal_id=goal['id'],
            workflow_root_turn_id=execution.state['root_turn_id'])
    goal.update(tool=tool.name, title=tool.title, mode='write', kind='change', response_source='server_workflow',
                response=f'{tool.title}. Проверьте и подтвердите данные в карточке.')
    workflow.record_result(execution.state, goal, tool.name, {'path': arguments.get('path', {})},
                           {'status': 'awaiting_confirmation'}, action_id=action['action_id'])
    execution.trace.append(dict(tool=tool.name, status='proposed', at=workflow.timestamp()))


def _selected_work(execution):
    selection = execution.state['erp_operator']['mutation_target']
    proved = _observed(execution).get(selection['receipt'])
    if not proved or proved['tool'] != 'tasks_find' or not proved['retained']:
        raise HTTPException(422, 'Сначала подтвердите выбор наряда по условиям поручения.')
    items = proved['result']['items']
    if len(items) != 1:
        raise HTTPException(422, 'Изменение возможно только для единственного проверенного наряда.')
    return items[0]


def _guard_mutation_subject(execution, path):
    if execution.state['erp_operator'].get('mutation_target'):
        if str(path.get('task_id')) != _selected_work(execution)['id']:
            raise HTTPException(422, 'Карточка должна относиться к проверенному наряду.')


def _local_instant(value, timezone):
    if not isinstance(value, str):
        raise HTTPException(422, 'Укажите местное время объекта.')
    instant = datetime.fromisoformat(value)
    return instant.astimezone(ZoneInfo(timezone)).replace(tzinfo=None) if instant.tzinfo else instant


def _guard_assignment_window(execution, start, end):
    zone = execution.scope['timezone']
    window = (_local_instant(start, zone), _local_instant(end, zone))
    day = window[0].date().isoformat()
    query = execution.state['erp_operator']['mutation_target']['contract']['query']
    if (day < query.get('starts_on', day) or day > query.get('ends_on', day) or
            ('on_days' in query and day not in query['on_days'])):
        raise HTTPException(422, 'Доступное время назначения выходит за проверенный период поручения.')
    mentioned = set(re.findall(r'(?<![\d:])(?:[01]\d|2[0-3]):[0-5]\d(?![\d:])', execution.question))
    if mentioned - {instant.strftime('%H:%M') for instant in window}:
        raise HTTPException(422, 'Запрошенное время отличается от проверенного расписания наряда.')
    return window


def _bind_assignment(execution, name, arguments):
    selected = _selected_work(execution)
    path = arguments.get('path', {})
    if 'task_id' in path and path['task_id'] != selected['id']:
        raise HTTPException(422, 'Предпросмотр должен относиться к проверенному наряду.')
    path = {**path, 'task_id': selected['id']}
    result = {**arguments, 'path': path}
    if name != 'assignment_preview':
        return result
    proof = next((item for item in _observed(execution).values() if item['tool'] == 'assignment_context' and
                  item['retained'] and item['arguments']['path'] == path), None)
    context = proof['result'] if proof else {}
    revision = context.get('expectedRevision')
    if revision is None:
        raise HTTPException(422, 'Сначала получите доступный период и ревизию из assignment_context.')
    if revision != selected['revision']:
        raise HTTPException(409, 'Наряд изменился после выбора. Проверьте его заново.')
    zone = execution.scope['timezone']
    defaults = {'start_local': context.get('defaultStartLocal'), 'end_local': context.get('defaultEndLocal')}
    scheduled = {'start_local': selected.get('scheduledStart'), 'end_local': selected.get('scheduledEnd')}
    window = scheduled if all(scheduled.values()) else defaults
    if not all(window.values()):
        raise HTTPException(422, 'Для назначения нужен подтверждённый интервал наряда.')
    local = dict(zip(window, _guard_assignment_window(execution, window['start_local'], window['end_local']), strict=True))
    body = result.get('body', {})
    if body.get('expected_revision', revision) != revision:
        raise HTTPException(409, 'Используйте проверенную ревизию наряда.')
    for key, wanted in local.items():
        if key not in body:
            continue
        provided = _local_instant(body[key], zone)
        default = _local_instant(defaults[key], zone) if defaults[key] else None
        if provided not in (wanted, default):
            raise HTTPException(422, 'Период предпросмотра должен совпадать с нарядом.')
    canonical = {key: instant.isoformat() for key, instant in local.items()}
    return {**result, 'body': {**body, **canonical, 'expected_revision': revision}}


def _deliver(execution, goal, task, proof, style, *, semantic=False):
    if task.operation != 'read' or not proof or not proof.get('retained'):
        return False
    source = proof['tool']
    if source != execution.state['erp_operator'].get('result_source'):
        return False
    constraints = task.constraints.get(source, {})
    if not semantic and type(constraints.get('limit')) is int and style != 'items':
        return False
    if style == 'instructions' and source == 'task_read':
        instructions = proof['result'].get('instructions')
        if not instructions:
            return False
        rows = [presentation.label(instructions)]
    elif source in presentation.SOURCE_NAMES:
        return presentation._deliver(execution, goal, proof, style)
    elif source == 'assignment_prepare':
        value = proof['result']
        rows = presentation._lines('assignment_preview', value, style)
    elif source.startswith('staff_'):
        value = proof['result']
        rows = [' · '.join(presentation.label(row[key]) for key in ('full_name', 'role', 'user_id') if row.get(key))
                for row in value['items']]
    elif source == 'task_acceptance_evidence':
        value = proof['result']
        rows = [f"Передача на приёмку · {'готово' if value.get('submission_ready') else 'есть препятствия'}.",
                f"Решение о приёмке · {'готово' if value.get('ready') else 'есть препятствия'}.",
                *dict.fromkeys(presentation.label(issue) for key in ('missing_materials', 'acceptance_blocks', 'submission_blocks')
                               for issue in value.get(key, []))]
    elif source in FACT_READS and style in ('items', 'count'):
        return _deliver_facts(execution, goal, proof, style)
    else:
        return False
    if not rows and proof['result'].get('total') != 0:
        return False
    text = '\n'.join(f'- {row}' for row in rows) if rows else 'В выбранной области записей нет.'
    label = EXTRA_LABELS.get(source) or presentation.SOURCE_NAMES[source]
    goal.update(tool=source, status='completed' if proof['complete'] else 'partial',
                reason=None if proof['complete'] else 'result_incomplete',
                response=f'{text}\n\nИсточник — {label} ({source}).', response_source='server_workflow')
    return True


def _deliver_facts(execution, goal, proof, style):
    source, value = proof['tool'], proof['result']
    complete = proof['complete']
    if style == 'count':
        if not isinstance(value, dict) or type(value.get('total')) is not int:
            return False
        text = f"Найдено **{value['total']}**."
        if proof['limitations'] == ['page_only']:
            workflow.record_result(execution.state, goal, source, proof['arguments'], {'total': value['total']},
                                   count_call=False)
            complete = True
    else:
        presented = present_facts(value, tool=source, arguments=proof['arguments'], max_characters=4000)
        if not presented.lines:
            return False
        text = '\n'.join(presented.lines)
        complete &= not presented.truncated
    if source in ('calendar_evidence', 'planning_context'):
        goal['required_evidence'] = 'calendar_calculation'
    goal.update(tool=source, mode='read', status='completed' if complete else 'partial',
                reason=None if complete else 'result_incomplete', response_source='server_workflow',
                response=f"{text}\n\nИсточник — {execution.tools[source].title} ({source}).")
    return True


def _discover(execution, state, args):
    query = args.get('query', {})
    domain = query.get('domain')
    selected = query.get('name')
    task = state['task']
    matches = {name: tool for name, tool in execution.tools.items() if workflow.specialist(name) == domain
               and name not in CORE and (tool.mode == 'read' or task['operation'] == 'change')}
    if not matches:
        raise HTTPException(422, 'В этой области нет дополнительных доступных операций.')
    if selected:
        if selected not in matches:
            raise HTTPException(422, 'Операция недоступна в этой области.')
        state['discovered'] = sorted({*state['discovered'], selected})
    state['domain_capabilities'] = {name: tool.title for name, tool in matches.items()}


async def _review_clear(execution, question, quote, latest, field):
    if not quoted_in(quote, question):
        return False
    review = await execution.infer([dict(role='system', content=_prompt('erp-operator-scope.md')),
        dict(role='user', content=service.dump({'message': question, 'quote': quote, 'field': field,
                                               'prior_goal': latest.original_request[:500]}))], ScopeReview, 160)
    return review.independent


def _read_goal_from_tool(decision):
    # Some providers choose a registered read while omitting the optional
    # semantic envelope. Its tool name can identify a result, never authorize a write.
    outcomes = {'equipment_find': 'equipment_list', 'equipment_read': 'equipment_card',
                'equipment_service_history': 'accepted_report', 'regulations_read': 'equipment_regulation'}
    source = decision.result_source or decision.tool
    if source not in outcomes or decision.task_delta and decision.task_delta.operation == 'change':
        return None
    if source == 'equipment_find':
        if decision.task_delta is not None:
            return None
        query = _arguments(decision).get('query', {})
        if set(query) - {'asset_code', 'accepted_maintenance'}:
            return None
        code = query.get('asset_code') or ''
        return ReadGoal(outcome='equipment_list', scope='asset_code' if code else 'inherit',
                        selector=code, accepted=query.get('accepted_maintenance'),
                        output='count' if decision.presentation == 'count' else 'items')
    return ReadGoal(outcome=outcomes[source])


async def _build_read_contract(execution, decision, read_goal, tasks, today, wants_change):
    request = read_goal.bind_literal_selector(execution.question)
    delta = decision.task_delta or TaskDelta()
    latest = next(iter(tasks.values()), None)
    if delta.mode == 'restore':
        latest = tasks.get(str(delta.restore_task_id))
        if latest is None:
            raise HTTPException(422, 'Уточните, к какому поручению вернуться.')
    task = latest.model_copy(deep=True) if latest else TaskState(task_id=execution.turn_id,
                                                               original_request=execution.question)
    reset = (latest is not None and request.scope == 'site' and
             await _review_clear(execution, execution.question, request.scope_quote, latest, 'equipment_scope'))
    if delta.mode == 'new' and (reset or request.scope.startswith('asset_')):
        # Selecting a different asset changes the subject of an existing
        # order search. It does not also erase the order date and state.
        inherited = (task.constraints.get('tasks_find', {}).copy()
                     if not reset and request.outcome == task.last_outcome == 'work_orders' else {})
        task = TaskState(task_id=execution.turn_id, original_request=execution.question)
        if inherited:
            task.constraints['tasks_find'] = inherited
    if latest and request.date and request.date.kind == 'clear':
        if not await _review_clear(execution, execution.question, request.date.quote, latest, 'date'):
            request = request.model_copy(update={'date': None})
    task.operation = 'change' if wants_change and request.outcome == 'work_orders' else 'read'
    task.last_outcome = request.outcome
    contract = contract_for(task, request, execution.question, today, allow_scope_reset=reset)
    if contract.source not in execution.tools:
        raise HTTPException(403, 'Текущая роль не может прочитать этот источник.')
    task.constraints[contract.source] = contract.query
    state = execution.state['erp_operator']
    state.update(task=task.model_dump(mode='json'), semantic=contract.model_dump(mode='json'),
                 result_source=contract.source,
                 transition={'from': str(latest.task_id) if latest else None, 'to': str(task.task_id),
                             'scope_reset_verified': reset, 'proposal': read_goal.model_dump(mode='json'),
                             'selector_bound': request.selector if request.scope.startswith('asset_') else None})
    return task, contract


async def _resolve_asset(execution, goal, task, contract):
    selector = contract.selector
    if selector.kind == 'asset_id':
        return selector.value
    args = selector.arguments()
    args['query']['limit'] = 2
    proof = await _read(execution, goal, task, execution.tools['equipment_find'], args, semantic=True, observe=False)
    if not proof['retained']:
        raise HTTPException(422, 'Не удалось подтвердить выбранное оборудование.')
    result = proof['result']
    if result.get('total') == 0:
        raise HTTPException(404, 'Указанное оборудование не найдено в доступной области.')
    if result.get('total') != 1 or len(result.get('items', ())) != 1:
        raise HTTPException(422, 'Уточните код или точное название оборудования.')
    task.observe(proof)
    return result['items'][0]['equipment_id']


async def _fulfil_read(execution, goal, task, contract):
    state = execution.state['erp_operator']
    goal['title'] = execution.tools[contract.source].title
    try:
        needs_resolution = (contract.source in EQUIPMENT_PATH and not contract.equipment_id or
                            contract.source == 'tasks_find' and contract.selector and
                            contract.selector.kind == 'asset_name' and 'equipment_id' not in contract.equipment_scope)
        if needs_resolution:
            identity = UUID(await _resolve_asset(execution, goal, task, contract))
            if contract.source in EQUIPMENT_PATH:
                contract.equipment_id = identity
            else:
                contract.equipment_scope = {'equipment_id': str(identity), **contract.equipment_scope}
            state.update(task=task.model_dump(mode='json'), semantic=contract.model_dump(mode='json'))
            return False
        proof = await _read(execution, goal, task, execution.tools[contract.source], contract.arguments(), semantic=True)
        started = monotonic()
        verified = contract.verifies(proof, execution.scope['timezone'])
        execution.state['metrics']['goal_verification_seconds'] = round(monotonic() - started, 6)
        if not verified:
            presentation._blocked(goal, 'operator_goal_unverified', 'Результат источника не подтвердил условия поручения.')
            return True
        state['task'] = task.model_dump(mode='json')
        state['verified_receipt'] = proof['id']
        if task.operation == 'change':
            state.pop('semantic')
            state['mutation_target'] = dict(contract=contract.model_dump(mode='json'), receipt=proof['id'])
            return False
        if _deliver(execution, goal, task, proof, contract.output, semantic=True):
            return True
        presentation._blocked(goal, 'operator_goal_unverified', presentation.CLARIFICATIONS['unverified'])
        return True
    except HTTPException as exc:
        reason = {403: 'permission_denied', 404: 'target_not_found', 422: 'operator_clarification'}.get(
            exc.status_code, 'operator_source_failed')
        execution.trace.append(dict(tool=contract.source, status='denied', code=exc.status_code, at=workflow.timestamp()))
        presentation._blocked(goal, reason, str(exc.detail) if exc.status_code in (403, 404, 422) else
                              presentation.CLARIFICATIONS['unverified'])
        return True


async def step(execution, goal):
    state = execution.state['erp_operator']
    if goal.get('action_id') or goal['status'] in END_STATUSES:
        return True
    if execution.files:
        presentation._blocked(goal, 'operator_attachments_unsupported', 'Для приложения файлов доступен штатный режим.')
        return True
    if primary_document_requested(execution.question):
        presentation._blocked(goal, 'operator_primary_document_required', 'Для проверки нужен оригинал документа производителя.')
        return True
    if 'semantic' in state:
        return await _fulfil_read(execution, goal, TaskState.model_validate(state['task']),
                                 ReadContract.model_validate(state['semantic']))
    settings = execution.app.state.settings
    tokens = min(750, settings.assistant_operator_output_tokens - state['reserved_output_tokens'])
    if state['attempts'] >= settings.assistant_operator_steps or tokens < 300:
        presentation._blocked(goal, 'operator_budget_or_evidence', presentation.CLARIFICATIONS['unverified'])
        if _observed(execution):
            goal['status'] = 'partial'
        return True
    goal.update(status='running', reason=None)
    task = TaskState.model_validate(state['task']) if 'task' in state else None
    tasks = _prior_tasks(execution) if task is None else {}
    observed = _observed(execution)
    enabled = {name: tool for name, tool in execution.tools.items() if name in CORE or name in state['discovered']}
    wants_change = _explicit_change(execution.question)
    context = dict(question=execution.question, task=state.get('task'),
        prior_tasks=[prior.model_dump(mode='json') if index == 0 else
                     dict(task_id=str(prior.task_id), original_request=prior.original_request)
                     for index, prior in enumerate(tasks.values())],
        clock=execution.clock, tomorrow=(date.fromisoformat(execution.clock['local_date']) + timedelta(days=1)).isoformat(),
        role=execution.scope['role'], explicit_change_requested=wants_change,
        domains=sorted({workflow.specialist(name) for name in execution.tools}),
        domain_capabilities=state.get('domain_capabilities', {}),
        tools={name: (presentation.TOOLS[name] if name in CORE else describe(execution.app, tool)['inputSchema'])
               for name, tool in enabled.items() if tool.mode == 'read' or task is None or task.operation == 'change'},
        recent=[{'question': row['content'][:500]}
                for row in execution.history[:2] if (row.get('workflow') or {}).get('scope') == execution.scope],
        results=[dict(receipt=key, tool=proof['tool'], arguments=proof['arguments'], complete=proof['complete'],
                      result=_small(proof['result'])) for key, proof in observed.items() if proof['retained']],
        failures=state['errors'][-4:])
    state['attempts'] += 1
    state['reserved_output_tokens'] += tokens
    instruction = _prompt('erp-operator-goal.md' if task is None else 'erp-operator.md')
    schema = _schema(tuple(context['tools']), task is None)
    decision = await execution.infer([dict(role='system', content=instruction),
                                      dict(role='user', content=service.dump(context))], schema, tokens)
    try:
        if task is None:
            read_goal = decision.read_goal or _read_goal_from_tool(decision)
            if read_goal:
                if wants_change and (read_goal.outcome != 'work_orders' or read_goal.output != 'items'):
                    raise HTTPException(422, 'Для изменения нужен план выбора одного наряда.')
                started = monotonic()
                await _build_read_contract(execution, decision, read_goal, tasks,
                                           date.fromisoformat(execution.clock['local_date']), wants_change)
                execution.state['metrics']['goal_binding_seconds'] = round(monotonic() - started, 6)
                return False
            task = _start_task(execution, goal, decision, tasks)
        elif not state.get('mutation_target') and (decision.task_delta is not None or decision.read_goal is not None):
            raise HTTPException(422, 'Изменения ограничений принимаются один раз на реплику.')
        proof = observed.get(decision.receipt)
        if decision.tool == 'clarify':
            presentation._blocked(goal, 'operator_clarification', presentation.CLARIFICATIONS.get(
                decision.clarification, presentation.CLARIFICATIONS['unverified']))
            return True
        if decision.tool == 'reply':
            if _deliver(execution, goal, task, proof, decision.presentation):
                return True
            raise HTTPException(422, 'Выберите подтверждённый receipt, который отвечает на поручение.')
        arguments = _arguments(decision)
        if decision.tool == 'discover':
            started = monotonic()
            _discover(execution, state, arguments)
            metrics = execution.state['metrics']
            metrics['discovery_seconds'] = metrics.get('discovery_seconds', 0) + round(monotonic() - started, 6)
            return False
        tool = enabled.get(decision.tool)
        if tool is None:
            raise HTTPException(403, 'Операция отсутствует в доступном каталоге.')
        if task.operation == 'read' and not state['result_source']:
            source = enabled.get(decision.result_source or decision.tool)
            if source and source.mode == 'read':
                state['result_source'] = source.name
                goal['title'] = source.title
        if tool.mode == 'write':
            await _propose(execution, goal, task, tool, proof, arguments)
            return True
        proof = await _read(execution, goal, task, tool, arguments)
        state['task'] = task.model_dump(mode='json')
        return decision.presentation != 'continue' and _deliver(execution, goal, task, proof, decision.presentation)
    except GoalClarification as exc:
        presentation._blocked(goal, 'operator_clarification', str(exc))
        return True
    except (HTTPException, ValueError) as exc:
        code = exc.status_code if isinstance(exc, HTTPException) else 422
        detail = str(exc.detail)[:220] if isinstance(exc, HTTPException) and code < 500 else 'Проверьте схему аргументов.'
        state['errors'].append(dict(tool=decision.tool if decision.tool in enabled or decision.tool in
                                    ('reply', 'discover', 'clarify') else 'unavailable', status=code, detail=detail))
        execution.trace.append(dict(tool=state['errors'][-1]['tool'], status='denied', code=code,
                                    at=workflow.timestamp()))
        return False
