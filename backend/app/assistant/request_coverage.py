"""Check compiled goals against independently identified request requirements."""
import re

from .semantic_plan import CHANGES, DISCUSSION, _subjects


def needs_review(question, interpretation):
    """Spend a second inference on compound requests, not routine lookups."""
    clauses = re.split(r'[.!?;\n]+\s+(?=\D)', question.strip().rstrip('.!?'))
    return len(interpretation.results) >= 3 or len(question) >= 160 or len(clauses) >= 3 or (
        len(interpretation.results) >= 2 and len(clauses) >= 2)


def _key(result):
    return result.intent, tuple(subject.casefold() for subject in result.subjects), result.period


def merge_review(request, interpretation, review):
    results = list(interpretation.results)
    for candidate in review.missing:
        if not candidate.source_text or candidate.source_text not in request:
            continue
        if candidate.intent in CHANGES:
            # A coverage reviewer cannot introduce a mutation during repair.
            candidate = candidate.model_copy(update={'intent': 'other'})
        if candidate.intent == 'recommend_actions':
            results = [prior for prior in results if not (
                prior.intent == 'general_explanation' and prior.source_text == candidate.source_text)]
        same = [index for index, prior in enumerate(results) if _key(prior) == _key(candidate)]
        if same:
            index = same[0]
            prior = results[index]
            fields = list(dict.fromkeys([*prior.fields, *candidate.fields]))
            results[index] = prior.model_copy(update={'fields': fields,
                'source_text': prior.source_text or candidate.source_text})
        elif len(results) < 12:
            results.append(candidate)
    constraints = list(dict.fromkeys([*interpretation.constraints, *review.constraints]))
    updates = dict(results=results, constraints=[value for value in constraints if value and value in request][:12])
    if hasattr(interpretation, 'analysis'):
        draft, supplemental = interpretation.analysis, getattr(review, 'analysis', None)
        updates['analysis'] = (draft if draft and draft.source_text in request else
                               supplemental if supplemental and supplemental.source_text in request else None)
    return interpretation.model_copy(update=updates)


def bind_requirements(state, interpretation, *, reviewed, review_required):
    request = state['request']
    requirements = []
    dataflow = {goal['semantic']['intent']:goal['id'] for goal in state['goals']
                if goal['id'].startswith('analysis-')}
    aggregate = dataflow.get('aggregate_work')
    aliases = {'equipment_tasks': 'overdue_tasks',
               'service_frequency': 'active_regulations', 'reference_details': 'task_details'}
    if 'maintenance_history' in dataflow and 'latest_maintenance' not in dataflow:
        aliases['latest_maintenance'] = 'maintenance_history'
    aggregate_facts = {'task_count', 'task_list', 'explain_results', 'general_explanation', 'recommend_actions'}
    for result in interpretation.results:
        source = result.source_text if result.source_text and result.source_text in request else None
        subjects = {subject.casefold() for subject in _subjects(result, request)}
        matching = []
        for goal in state['goals']:
            meta = goal.get('semantic', {})
            same_intent = meta.get('intent') == result.intent
            same_card = result.intent == 'equipment_exists' and meta.get('intent') == 'equipment_details' and bool(subjects)
            period = ((result.period or 'all') if result.intent == 'equipment_tasks' else
                      result.period if result.intent in ('task_list', 'assign_task') else None)
            compatible_period = period is None or meta.get('period') == period
            if ((same_intent or same_card) and compatible_period and
                    (not subjects or str(meta.get('subject') or '').casefold() in subjects)):
                matching.append(goal['id'])
        if aggregate and not matching and not subjects:
            if result.intent in aggregate_facts or result.intent=='equipment_tasks' and period=='all':
                matching.append(aggregate)
            elif dataflow.get(aliases.get(result.intent, result.intent)):
                matching.append(dataflow[aliases.get(result.intent, result.intent)])
            elif result.intent=='equipment_tasks' and dataflow.get('task_details'):
                matching.append(aggregate)
            elif result.intent=='other' and not source:
                continue
            elif result.intent=='manufacturer_source':
                from .intents import primary_document_requested
                if not primary_document_requested(request):
                    continue
        linked_goals = [goal for goal in state['goals'] if goal['id'] in matching]
        if source:
            same_source = [goal for goal in linked_goals if goal['semantic'].get('source_text') == source]
            if same_source:
                linked_goals = same_source
                matching = [goal['id'] for goal in linked_goals]
        # Compiler fields are grounded in literal request text, including fields
        # omitted by the interpreter. Default display fields aren't obligations.
        fields = list(dict.fromkeys(field for goal in linked_goals for field in
                                    goal.get('semantic', {}).get('requested_fields', [])))
        requirements.append(dict(id=f'r{len(requirements)+1}', intent=result.intent, source_text=source,
                                 subjects=sorted(subjects), period=period, fields=fields or (result.fields if not matching else []),
                                 goal_ids=matching))
    # Deterministic expansion can discover a second requested cohort during
    # compilation. Save that goal as a requirement as well.
    linked = {identity for requirement in requirements for identity in requirement['goal_ids']}
    for goal in state['goals']:
        meta = goal.get('semantic', {})
        if meta.get('intent') and goal['id'] not in linked:
            requirements.append(dict(id=f'r{len(requirements)+1}', intent=meta['intent'],
                source_text=meta.get('source_text'), subjects=[meta['subject']] if meta.get('subject') else [],
                period=meta.get('period'), fields=meta.get('requested_fields', []), goal_ids=[goal['id']]))
    if aggregate:
        criteria = next(goal['semantic'] for goal in state['goals'] if goal['id']==aggregate)
        for intent, key in (('aggregate_comparison', 'compare'), ('recommend_actions', 'recommendations')):
            if criteria[key] and not any(requirement['intent']==intent for requirement in requirements):
                requirements.append(dict(id=f'r{len(requirements)+1}', intent=intent, source_text=None,
                                         subjects=[], period=None, fields=[], goal_ids=[aggregate]))
    for requirement in requirements:
        bound = [goal for goal in state['goals'] if goal['id'] in requirement['goal_ids']]
        requirement['plan_status'] = 'planned' if bound else 'unplanned'
        requirement['dependencies'] = sorted({dep for goal in bound for dep in goal.get('depends_on', [])})
        requirement['scope'] = [goal.get('semantic', {}).get('query') or goal.get('semantic', {}).get('selected_input')
                                or goal.get('semantic', {}).get('analysis_query') or {} for goal in bound]
    state['request_spec'] = dict(version=2, requirements=requirements, reviewed=reviewed, review_required=review_required,
                                read_only=state.get('read_only', False),
                                constraints=[value for value in interpretation.constraints if value and value in request],
                                response_format=(interpretation.response_format
                                                 if interpretation.response_format and interpretation.response_format in request else None))


def update_coverage(state):
    goals = {goal['id']: goal for goal in state['goals']}
    spec = state.get('request_spec', {})
    for requirement in spec.get('requirements', []):
        linked = [goals[identity] for identity in requirement['goal_ids'] if identity in goals]
        statuses = {goal['status'] for goal in linked}
        if linked and statuses <= {'completed', 'answered'}:
            status = 'no_tool_required' if requirement['intent'] in DISCUSSION else 'completed'
        elif not linked:
            status = 'unplanned'
        elif statuses & {'planned', 'running', 'awaiting_confirmation'}:
            status = 'planned'
        elif statuses & {'awaiting_input'}:
            status = 'missing_input'
        else:
            status = next((goal.get('semantic', {}).get('disposition') for goal in linked
                           if goal.get('semantic', {}).get('disposition')), None)
            if status is None:
                failed_reads = {proof.get('status') for proof in state['evidence']
                                if proof.get('goal_id') in requirement['goal_ids']}
                status = ('forbidden' if 'FORBIDDEN' in failed_reads else
                          'missing_input' if 'MISSING_INPUT' in failed_reads else
                          'unavailable' if 'UNAVAILABLE' in failed_reads else
                          'failed' if 'ERROR' in failed_reads else 'incomplete')
        if any(goal['id']=='analysis-selection' for goal in linked):
            facet = {'aggregate_comparison': 'compare', 'recommend_actions': 'recommendations'}.get(requirement['intent'])
            if facet and status in ('completed', 'no_tool_required'):
                status = state.get('analytical_delivery', {}).get(facet, 'planned')
        if spec.get('version') == 2:
            evidence = [proof for proof in state['evidence'] if proof.get('goal_id') in requirement['goal_ids']]
            requirement['evidence_ids'] = [proof['id'] for proof in evidence]
            requirement['evidence_statuses'] = sorted({proof['status'] for proof in evidence if 'status' in proof})
            requirement['execution_status'] = {'completed': 'SATISFIED', 'no_tool_required': 'SATISFIED',
                'missing_input': 'MISSING_INPUT', 'unavailable': 'UNAVAILABLE', 'forbidden': 'FORBIDDEN',
                'unsupported': 'NOT_SUPPORTED', 'failed': 'FAILED', 'incomplete': 'PARTIAL',
                'unplanned': 'NOT_SUPPORTED'}.get(status)
            receipts = [goal.get('answer_delivery') for goal in linked]
            if status in ('completed', 'no_tool_required'):
                if not all(receipts):
                    requirement['delivery_status'] = 'pending'
                    status = 'planned'
                elif not all(receipt['complete'] for receipt in receipts):
                    requirement['delivery_status'] = 'partial'
                    status = 'incomplete'
                else:
                    requirement['delivery_status'] = 'delivered'
            else:
                requirement['delivery_status'] = 'limitation' if any(receipts) else 'pending'
        requirement['status'] = status
