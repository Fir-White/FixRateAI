"""Execute validated edges of a read-only dataflow using ordinary authorized GETs."""
from datetime import date, datetime, timezone
import time

from fastapi import HTTPException
from app.schemas.assistant import MAX_COLLECTION_PAGE
from . import workflow
from .analysis_contract import AggregateQuery, AggregateResult, ResourceRef, SelectedInput, TaskAcceptanceReceipt
from .analysis_scope import _months_before
from .dependent_planning import SOURCE, TARGETS, query_arguments
from .read_transport import read


def read_selection(state, goal_id):
    proof = next((proof for proof in reversed(state['evidence'])
                  if proof['goal_id']==goal_id and proof.get('output_type')=='aggregate'
                  and proof['complete'] and proof['retained'] and proof['scope']==state['scope']), None)
    if proof is not None:
        return AggregateResult.model_validate(proof['result']), proof
    return None, None


def validate_selection(value, query, principal):
    output = AggregateResult.model_validate(value)
    groups = output.groups
    if output.query != query or output.site_id != principal.site_id or output.timezone != principal.timezone:
        raise ValueError('Scope of aggregate result does not match the request')
    if query.as_of and output.as_of != query.as_of:
        raise ValueError('As-of date does not match')
    if query.group_by == 'period':
        if [row.window for row in groups] != query.windows or any(row.id is not None for row in groups):
            raise ValueError('Planning periods do not match')
    else:
        if (len(groups) != min(query.limit, max(0, output.eligible_groups-query.offset)) or
                len({row.id for row in groups}) != len(groups) or any(row.id is None for row in groups)):
            raise ValueError('Invalid identities or result count')
        if query.group_by=='task':
            latest = datetime.max.replace(tzinfo=timezone.utc)
            rank_keys = [(row.deadline_on or date.max, row.id) if query.tie_breaker == 'uuid'
                         else (row.deadline_on or date.max, row.deadline_at or latest, row.id) for row in groups]
            if query.metric=='earliest_overdue' and any(row.overdue!=1 or not row.deadline_on for row in groups):
                raise ValueError('Non-overdue task in selected cohort')
        elif query.metric=='without_service':
            rank_keys = []  # Registry code order uses the database collation.
        else:
            rank_keys = [(-getattr(row, query.metric), row.id if query.tie_breaker == 'uuid'
                          else row.oldest_due or date.max) for row in groups]
        if query.first_equipment_code:
            wanted = {query.first_equipment_code.casefold(), query.second_equipment_code.casefold()}
            actual = {str(row.code or '').casefold() for row in groups}
            if len(actual) != len(groups) or not actual <= wanted or any(not row.state or not row.label for row in groups):
                raise ValueError('Equipment comparison returned a different card')
        if rank_keys != sorted(rank_keys):
            raise ValueError('Invalid rank order')
    for row in groups:
        tasks = row.overdue_tasks
        if (row.overdue > row.unfinished or row.undated + row.overdue > row.unfinished or
                bool(row.oldest_due) != bool(row.overdue) and query.group_by not in ('period','task')):
            raise ValueError('Inconsistent aggregate counters')
        if (tasks is not None) != query.include_overdue_tasks:
            raise ValueError('Task projection does not match the request')
        if tasks is not None and (len(tasks) > row.overdue or len({task.task_id for task in tasks}) != len(tasks)):
            raise ValueError('Inconsistent overdue task rows')
        assignments = row.assignments
        if (assignments is not None) != query.include_assignments:
            raise ValueError('Assignment projection does not match the request')
        if assignments is not None and (row.assignment_total is None or len(assignments)>row.assignment_total or
                row.assignment_total != row.unfinished or len({item.task_id for item in assignments})!=len(assignments)):
            raise ValueError('Inconsistent assignment rows')
    return output


IDENTITY_KEYS = {'assignee':'user_id', 'equipment':'equipment_id', 'task':'task_id'}


def bound_arguments(binding, reference, as_of):
    args = {'path': {IDENTITY_KEYS[reference.kind]: str(reference.id)}}
    if binding.projection in ('latest_maintenance', 'maintenance_history'):
        args['query'] = dict(starts_on=_months_before(as_of, binding.months or 12).isoformat(),
                             ends_on=as_of.isoformat(), only_accepted=True,
                             latest_only=binding.projection=='latest_maintenance')
        if binding.projection == 'maintenance_history':
            args['query']['limit'] = MAX_COLLECTION_PAGE
    elif binding.projection=='maintenance_calendar':
        args['query'] = dict(starts_on=as_of.isoformat(),
                             ends_on=_months_before(as_of, -(binding.months or 12)).isoformat(),
                             approved_only=True, next_only=True)
    elif binding.projection=='task_materials':
        if reference.revision is None:
            raise ValueError('Task revision is missing')
        args['query'] = {'expected_revision': reference.revision}
        if reference.execution_id:
            args['query']['execution_id'] = str(reference.execution_id)
    if binding.window and binding.projection in ('latest_maintenance', 'maintenance_history', 'maintenance_calendar'):
        args['query'].update(binding.window.model_dump(mode='json'))
    return args


def resource_inputs(state, binding):
    selection, proof = read_selection(state, binding.source_goal)
    if selection is not None:
        kind = selection.query.group_by
        if kind=='period' or binding.resource and kind!=binding.resource:
            raise ValueError('Resource type does not match edge')
        if binding.first_only and selection.eligible_groups != 2:
            raise ValueError('Both equipment cards are required to select a winner')
        rows = selection.groups[:1] if binding.first_only else selection.groups
        return selection.as_of, [(ResourceRef(kind=kind,id=row.id), proof) for row in rows], False
    source = next((goal for goal in state['goals'] if goal['id']==binding.source_goal), None)
    if source is None or binding.resource is None or 'analysis_query' in source.get('semantic',{}):
        raise ValueError('No compatible source')
    proofs = {proof['id']:proof for proof in state['evidence'] if proof['goal_id']==binding.source_goal
              and proof['scope']==state['scope'] and proof['complete'] and proof['retained']}
    inputs = []
    for dependency in source.get('bindings', []):
        proof = proofs.get(dependency['evidence_id'])
        if proof and proof.get('resource_output'):
            ref = ResourceRef.model_validate(proof['resource_output'])
            if ref.kind!=binding.resource or str(ref.id)!=dependency['entity_id']:
                raise ValueError('Invalid reference returned by dependency')
            inputs.append((ref, proof))
    if not inputs and source['status']!='completed':
        raise ValueError('Dependency did not return references')
    return None, inputs, source['status']!='completed'


class DataflowRunner:
    def __init__(self, app, principal, state, tools, headers, trace, check, save, progress, budget):
        self.app, self.principal, self.state, self.tools = app, principal, state, tools
        self.headers, self.trace, self.check = headers, trace, check
        self.save, self.progress, self.budget = save, progress, budget
        self.calls = 0

    async def observe(self, goal, name, args, row_id=None, *, full=False):
        self.check()
        tool = self.tools.get(name)
        if tool is None or tool.mode != 'read' or tool.method != 'GET':
            raise HTTPException(403, 'Чтение недоступно текущей роли')
        if self.calls >= self.budget:
            raise HTTPException(413, 'Достигнут бюджет чтений')
        self.progress(name)
        started = time.monotonic()
        attempts = []
        try:
            if full:
                from .orchestrator import _read_pages
                arguments, value = await _read_pages(self.app, tool, args, self.headers, full=True, check=self.check,
                    trace=attempts, principal=self.principal, max_reads=self.budget-self.calls, retry_temporary=True)
            else:
                arguments, value = await read(self.app, tool, args, self.headers, attempts,
                                              retry_temporary=self.calls+1 < self.budget)
            return arguments, value, time.monotonic()-started
        finally:
            self.calls += len(attempts)
            self.trace.extend(dict(entry, goal_id=goal['id'], bound_id=row_id) for entry in attempts)

    async def select(self, goal):
        query = AggregateQuery.model_validate(goal['semantic']['analysis_query'])
        args = query_arguments(query)
        try:
            arguments, value, elapsed = await self.observe(goal, SOURCE, args)
            selection = validate_selection(value, query, self.principal)
        except HTTPException as exc:
            workflow.record_read_failure(self.state, goal, SOURCE, args, exc.status_code)
            goal.update(status='blocked', reason=f'tool_error_{exc.status_code}')
            return
        except ValueError:
            goal.update(status='blocked', reason='aggregate_output_invalid')
            self.trace.append(dict(tool='__dataflow_validation', status='denied', goal_id=goal['id'],
                                   reason='aggregate_output_invalid'))
            return
        output = selection.model_dump(mode='json')
        detail_sets = [{key:row.pop(key) for key in ('overdue_tasks','assignments')}
                       for row in output['groups']]
        proof = workflow.record_result(self.state, goal, SOURCE, arguments, output, elapsed=elapsed)
        proof['output_type'] = 'aggregate'
        if not proof['complete']:
            return
        for row, details in zip(selection.groups, detail_sets, strict=True):
            for key, items in details.items():
                if items is None:
                    continue
                name, count = ('overdue_tasks',row.overdue) if key=='overdue_tasks' else ('staff_assignments',row.assignment_total)
                detail_args = {**arguments, 'path': {IDENTITY_KEYS[query.group_by]: str(row.id)}}
                detail = workflow.record_result(self.state, {**goal,'tool':'','outcome':'other'}, SOURCE, detail_args,
                    dict(items=items,total=count,complete=len(items)==count), count_call=False)
                detail.update(output_type=name,source_evidence_id=proof['id'])
        if query.metric=='without_service' and (selection.unresolved_groups or selection.eligible_groups>query.limit):
            goal.update(status='partial',reason='service_registry_coverage_limited')
        if (goal['semantic'].get('all_groups') or (goal['semantic'].get('requested_limit') or 0) > query.limit) and selection.eligible_groups > query.limit:
            goal.update(status='partial', reason='aggregate_selection_limited')
        self.save()

    async def project(self, goal):
        binding = SelectedInput.model_validate(goal['semantic']['selected_input'])
        name, _ = TARGETS[binding.projection]
        if goal['depends_on'] != [binding.source_goal]:
            goal.update(status='blocked', reason='dependency_output_unavailable')
            return
        try:
            as_of, inputs, partial_input = resource_inputs(self.state, binding)
        except ValueError:
            goal.update(status='blocked', reason='dependency_output_unavailable')
            return
        links = []
        goal['bindings'] = links
        for reference, source in inputs:
            self.check()
            identity = str(reference.id)
            args = {}
            try:
                args = bound_arguments(binding, reference, as_of)
                if binding.projection in ('overdue_tasks','staff_assignments'):
                    proof = next(p for p in self.state['evidence'] if p.get('output_type')==binding.projection
                                 and p.get('source_evidence_id')==source['id']
                                 and p.get('entity')==args['path'])
                    result = proof.copy()
                    result.update(id=f'e{len(self.state["evidence"])+1}', goal_id=goal['id'])
                    self.state['evidence'].append(result)
                    goal['evidence_ids'].append(result['id'])
                else:
                    used_args, value, elapsed = await self.observe(goal, name, args, identity,
                                                                   full=binding.projection == 'maintenance_history')
                    selector = {**args['path'], **{k: v for k, v in args.get('query', {}).items()
                                                   if k in ('starts_on', 'ends_on')}}
                    child = {**goal, 'selector': selector, 'outcome':
                             'equipment_card' if name=='equipment_read' else 'other'}
                    if name in ('equipment_read','staff_read'):
                        key = next(iter(args['path']))
                        if not isinstance(value, dict) or str(value.get(key)) != identity:
                            raise HTTPException(502, 'Источник вернул другую карточку')
                        if name=='equipment_read' and str(value.get('site_id')) != self.state['scope']['site_id']:
                            raise HTTPException(502, 'Источник вернул оборудование другого объекта')
                    if name=='task_acceptance_evidence':
                        receipt = TaskAcceptanceReceipt.model_validate(value)
                        if (receipt.task_id!=reference.id or receipt.revision!=reference.revision or
                                receipt.execution_id!=reference.execution_id):
                            raise HTTPException(502, 'Материалы не соответствуют выбранной попытке')
                        if self.state.get('engineering_request', {}).get('kind') == 'acceptance_readiness' and (
                                'submission_ready' not in receipt.model_fields_set or receipt.submission_ready is None):
                            raise HTTPException(502, 'Источник не подтвердил готовность к передаче')
                    ref = None
                    if name=='task_read':
                        card = value.get('task') if isinstance(value,dict) else None
                        if not isinstance(card,dict) or card.get('id')!=identity or not isinstance(card.get('state'),str):
                            raise HTTPException(502, 'Источник вернул другое задание или непроверяемую карточку')
                        ref = ResourceRef(kind='task',id=card['id'],revision=card['revision'],
                                          execution_id=card.get('activeExecutionId'))
                    result = workflow.record_result(self.state, child, name, used_args, value, elapsed=elapsed)
                    if ref and result['complete']:
                        result['resource_output'] = ref.model_dump(mode='json')
            except HTTPException as exc:
                result = workflow.record_read_failure(self.state, goal, name, args, exc.status_code)
            except (ValueError, KeyError, StopIteration):
                result = workflow.record_read_failure(self.state, goal, name, args, 422)
            links.append(dict(entity_id=identity, evidence_id=result['id'], from_evidence=source['id'],
                              period=result['period'], status=result['status']))
            self.save()
        status = 'completed' if not partial_input and all(link['status'] in ('FOUND', 'EMPTY') for link in links) else 'partial'
        goal.update(status=status, reason=None if status=='completed' else 'selected_reads_incomplete')

    async def run(self, goal):
        if goal['status']=='completed' or goal['semantic'].get('block'):
            return
        goal.update(status='running', reason=None)
        self.save()
        if goal.get('depends_on'):
            await self.project(goal)
        else:
            await self.select(goal)
        self.save()
