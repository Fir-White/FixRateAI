"""Check compiled goals against independently identified request requirements."""
import re

from .semantic_plan import CHANGES, DISCUSSION, RequestedResults


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
    return RequestedResults(results=results, read_only=interpretation.read_only,
                            constraints=[value for value in constraints if value and value in request][:12],
                            response_format=interpretation.response_format)


def bind_requirements(state, interpretation, *, reviewed, review_required):
    request = state['request']
    requirements = []
    for result in interpretation.results:
        source = result.source_text if result.source_text and result.source_text in request else None
        subjects = {subject.casefold() for subject in result.subjects if subject.casefold() in request.casefold()}
        matching = []
        for goal in state['goals']:
            meta = goal.get('semantic', {})
            same_intent = meta.get('intent') == result.intent
            same_source = source and meta.get('source_text') == source and meta.get('intent') not in DISCUSSION
            period = result.period or ('all' if result.intent == 'equipment_tasks' else None)
            compatible_period = period is None or meta.get('period') == period
            if ((same_intent or same_source and result.intent != 'other') and compatible_period and
                    (not subjects or str(meta.get('subject') or '').casefold() in subjects)):
                matching.append(goal['id'])
        requirements.append(dict(id=f'r{len(requirements)+1}', intent=result.intent, source_text=source,
                                 subjects=sorted(subjects), period=result.period, fields=result.fields,
                                 goal_ids=matching))
    # Deterministic expansion can discover a second requested cohort during
    # compilation. Save that goal as a requirement as well.
    linked = {identity for requirement in requirements for identity in requirement['goal_ids']}
    for goal in state['goals']:
        meta = goal.get('semantic', {})
        if meta.get('intent') == 'equipment_tasks' and goal['id'] not in linked:
            requirements.append(dict(id=f'r{len(requirements)+1}', intent=meta['intent'],
                source_text=meta.get('source_text'), subjects=[meta['subject']] if meta.get('subject') else [],
                period=meta.get('period'), fields=meta['fields'], goal_ids=[goal['id']]))
    state['request_spec'] = dict(requirements=requirements, reviewed=reviewed, review_required=review_required,
                                read_only=state.get('read_only', False),
                                constraints=[value for value in interpretation.constraints if value and value in request],
                                response_format=(interpretation.response_format
                                                 if interpretation.response_format and interpretation.response_format in request else None))


def update_coverage(state):
    goals = {goal['id']: goal for goal in state['goals']}
    for requirement in state.get('request_spec', {}).get('requirements', []):
        linked = [goals[identity] for identity in requirement['goal_ids']]
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
                          'missing_input' if 'MISSING_INPUT' in failed_reads else 'incomplete')
        requirement['status'] = status
