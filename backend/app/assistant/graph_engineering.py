"""Ground typed engineering requests in the user's scope and saved tool receipts."""
from dataclasses import dataclass, field, replace
from datetime import date
import re

from .analysis_contract import AnalysisRequest
from .analysis_selection import anchored_date, has, ranked_clause, selection_clause, clauses, MATERIAL
from .analysis_scope import _months_before
from .dependent_execution import read_selection
from .graph_context import comparison_followup_plan, with_equipment
from .intents import mutation_command_requested, prohibits_changes, primary_document_requested
from .semantic_plan import AnalyticalRequestedResults, AnalyticalResult, RequestedResult, RequestedResults, asset_references


PAGE_SIZE = 20


@dataclass(frozen=True)
class EngineeringPlan:
    request: RequestedResults
    planning_text: str
    context: dict = field(default_factory=dict)


def dated_comparison(question):
    subjects = asset_references(question)
    if len(subjects) != 2 or not has(r'сравни\w*|сопоставь\w*', question):
        return None
    if not has(r'незаверш\w*', question) or not has(r'просроч\w*', question):
        return None
    return (subjects, day) if (day := anchored_date(question)) else None


def aggregate_plan(question, source, *, kind, **options):
    request = AnalyticalRequestedResults(read_only=True,
        results=[AnalyticalResult(intent='aggregate_work', source_text=source[:700])],
        analysis=AnalysisRequest(source_text=source[:700], **options))
    return EngineeringPlan(request, question, {'kind': kind})


def prior_comparison(history, scope):
    for entry in history:
        prior = entry.get('workflow')
        if entry['status'] != 'completed' or not prior or prior['scope'] != scope:
            continue
        if match := dated_comparison(prior['request']):
            return entry, match
    return None, None


def context_plan(question, history, scope, clock):
    if not (has(r'(?:предыдущ\w*|наш\w*)\s+сравнени\w*', question)
            and has(r'больше\s+просроч\w*', question) and not asset_references(question)
            and has(r'регламент\w*', question) and has(r'последн\w*\s+фактическ\w*\s+принят\w*\s+то', question)):
        return None
    entry, match = prior_comparison(history, scope)
    rule_day = anchored_date(question)
    if not entry:
        return EngineeringPlan(RequestedResults(read_only=True, results=[
            RequestedResult(intent='other', source_text=question[:700])]), question, {'kind':'missing_comparison'})
    codes, comparison_day = match
    prior = entry['workflow']
    selection, proof = read_selection(prior, 'analysis-selection')
    expected = {value.casefold() for value in codes}
    if (prior.get('outcome') == 'completed' and selection and len(selection.groups) == 2
            and selection.as_of == comparison_day and selection.query.first_equipment_code
            and {str(row.code or '').casefold() for row in selection.groups} == expected):
        winner, other = sorted(selection.groups, key=lambda row: (-row.overdue, row.id))
        plan, text = with_equipment(question, str(winner.id), ['latest_maintenance', 'active_regulations'], clock)
        return EngineeringPlan(plan, text, dict(kind='comparison_followup', equipment_id=str(winner.id),
            code=winner.code, counts=[winner.overdue, other.overdue], comparison_day=str(selection.as_of),
            historical=selection.historical_cutoff, source_turn=str(entry['turn_id']), source=proof['id'],
            rule_day=str(rule_day) if rule_day else clock['local_date']))
    # An older partial answer can identify the intended pair. Recompute counts
    # in the authorized registry before using its winner, instead of trusting prose.
    fresh = aggregate_plan(question, question, kind='comparison_recheck', group_by='equipment',
        metric='overdue', limit=2, as_of=comparison_day, first_equipment_code=codes[0],
        second_equipment_code=codes[1], tie_breaker='uuid',
        projections=['latest_maintenance','active_regulations'], history_months=12)
    return replace(fresh, planning_text=f'{question}\nКоды из сравнения: {codes[0]} и {codes[1]}.',
                   context={**fresh.context,'rule_day':str(rule_day) if rule_day else clock['local_date'],
                            'history_day':clock['local_date']})


def engineering_plan(question, history, scope, clock):
    if (mutation_command_requested(question) and not prohibits_changes(question)) or primary_document_requested(question):
        return None
    try:
        if match := dated_comparison(question):
            codes, day = match
            return aggregate_plan(question, question, kind='equipment_comparison', group_by='equipment',
                metric='overdue', limit=2, as_of=day, first_equipment_code=codes[0],
                second_equipment_code=codes[1], tie_breaker='uuid', compare=True)
        if context := context_plan(question, history, scope, clock):
            return context
        if followup := comparison_followup_plan(question, history, scope, clock):
            return EngineeringPlan(*followup)
        if ((selected := selection_clause(clauses(question))) and selected[1] == 'earliest_overdue'
                and has(MATERIAL, question) and has(r'готов\w*|препятств\w*', question)):
            tie = 'uuid' if has(r'равенств\w*|одинаков\w*', question) and has(r'uuid', question) else None
            return aggregate_plan(question, selected[2], kind='acceptance_readiness', group_by='task',
                metric='earliest_overdue', limit=1, as_of=anchored_date(question), tie_breaker=tie,
                projections=['task_details','task_materials'])
        if ((rank := ranked_clause(clauses(question))) and has(r'исполнител[ьяю]\s+(?:текущ\w*\s+объект\w*\s+)?с\s+наибольш', rank)
                and has(r'назначенн\w*\s+незаверш\w*', rank)
                and has(r'перечисли\w*|постраничн\w*', question) and not has(r'человеко-час\w*|трудозатрат\w*', rank)):
            tie = 'uuid' if has(r'равенств\w*|одинаков\w*', question) and has(r'uuid', question) else None
            return aggregate_plan(question, rank, kind='assigned_workload', group_by='assignee',
                metric='unfinished', limit=1, as_of=anchored_date(question), tie_breaker=tie,
                projections=['staff_assignments'])
    except ValueError:
        # Invalid literal dates still go through the typed planner's diagnostics.
        return None
    return None


def configure_plan(state, context):
    state['engineering_request'] = context
    kind = context['kind']
    for goal in state['goals']:
        meta = goal['semantic']
        if kind == 'comparison_recheck':
            if binding := meta.get('selected_input'):
                binding['first_only'] = True
                if meta['intent'] == 'latest_maintenance':
                    end = date.fromisoformat(context['history_day'])
                    binding['window'] = dict(starts_on=str(_months_before(end,12)),ends_on=str(end))
            elif meta.get('intent') == 'aggregate_work':
                meta['compare'] = False
        if kind in ('comparison_followup', 'comparison_recheck') and meta['intent'] == 'active_regulations':
            meta['local_date'] = context['rule_day']
            meta['show_regulation_cutoff'] = True
        if kind in ('comparison_followup', 'comparison_recheck') and meta['intent'] == 'latest_maintenance':
            meta['show_history_period'] = True
        if kind == 'missing_comparison':
            meta['block'] = 'В этом диалоге нет подтверждённого сравнения двух единиц. Сначала сравните их по кодам.'


def bind_engineering_requirements(state, context):
    requirements = state['request_spec']['requirements']
    audit_fields = {
        'equipment_comparison': {'analysis-selection': ['compared_equipment', 'unfinished_counts',
                                                        'overdue_counts', 'historical_basis']},
        'comparison_followup': {'regulations_read': ['dated_regulation_versions'],
                                'equipment_service_history': ['selected_equipment_and_criterion','last_accepted_service']},
        'comparison_recheck': {'analysis-selection': ['selected_equipment_and_criterion']},
        'assigned_workload': {'analysis-selection': ['ranked_assignee_and_count'],
                              'analysis-staff_assignments': ['assignment_task_fields_and_pages']},
        'acceptance_readiness': {'analysis-selection': ['earliest_overdue_task'],
                                 'analysis-task_details': ['selected_task_card'],
                                 'analysis-task_materials': ['linked_equipment', 'assigned_executors',
                                    'mandatory_checklist_and_answers', 'saved_execution_materials', 'submission_readiness']},
    }
    by_goal = audit_fields.get(context['kind'], {})
    for goal in state['goals']:
        meta = goal['semantic']
        for intent in by_goal.get(goal['id'], by_goal.get(goal['tool'], [])):
            requirements.append(dict(id=f'r{len(requirements)+1}', intent=intent, source_text=None,
                subjects=[], period=None, fields=[], goal_ids=[goal['id']], plan_status='planned',
                dependencies=goal['depends_on'], scope=[meta.get('analysis_query') or meta.get('selected_input') or {}]))


def assignment_page_request(question):
    match = re.fullmatch(r'\s*(?:покажи\s+)?страниц[ау]\s+([1-9]\d{0,2})\s+назначений[.!?]?\s*', question, re.I)
    return int(match[1]) if match else None


def comparison_context_intro(context):
    first, second = context['counts']
    criterion = (f'Равенство, по {first} просроченных заданий. Выбран меньший UUID.'
                 if first == second else f'Выбрано по числу просрочек: {first} против {second}.')
    basis = f" Дата среза {context['comparison_day']}." if context.get('comparison_day') else ''
    if context.get('historical'):
        basis += ' Нормативные сроки сопоставлены на эту дату по текущим состояниям заданий.'
    source_tool = context.get('source_tool', 'work_order_analytics')
    return (f"Выбрано {context['code']} · {context['equipment_id']}. {criterion}{basis} "
            f"Источник {context['source']} · {source_tool} · предыдущее сравнение.")


def saved_assignment_page(history, scope, page):
    from .dependent_report import assignment_page_lines, display, reference

    for entry in history:
        prior = entry.get('workflow')
        if (not prior or prior['scope'] != scope
                or prior.get('engineering_request', {}).get('kind') != 'assigned_workload'):
            continue
        aggregate, selection_proof = read_selection(prior, 'analysis-selection')
        if not aggregate or len(aggregate.groups) != 1:
            continue
        row = aggregate.groups[0]
        source = next((proof for proof in prior['evidence'] if proof['goal_id'] == 'analysis-staff_assignments'
                       and proof.get('output_type') == 'staff_assignments'
                       and proof['retained'] and proof['scope'] == scope
                       and proof.get('source_evidence_id') == selection_proof['id']
                       and proof.get('result', {}).get('total') == row.assignment_total
                       and proof.get('entity',{}).get('user_id') == str(row.id)), None)
        if source:
            return '\n'.join([f'{display(row.label)} · {row.id}. Снимок назначений на {aggregate.as_of}.',
                *assignment_page_lines(source['result'], reference(source), page)])
    return None
