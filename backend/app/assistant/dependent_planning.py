"""Compile grouped analyses and reads over the resulting typed selection."""
from app.schemas.assistant import GoalSpec

from .analysis_contract import AggregateQuery, MAX_AGGREGATE_ROWS, SelectedInput, Window
from .analysis_selection import grounded_analysis, has, recommendation_count, requested_projections
from .intents import primary_document_requested


SOURCE = 'work_order_analytics'
TARGETS = {
    'equipment_details': ('equipment_read', 'Карточки выбранного оборудования'),
    'overdue_tasks': (SOURCE, 'Сроки просроченных работ выбранного оборудования'),
    'latest_maintenance': ('equipment_service_history', 'Фактическое ТО выбранного оборудования'),
    'maintenance_history': ('equipment_service_history', 'История принятого ТО выбранного оборудования'),
    'active_regulations': ('regulations_read', 'Регламенты выбранного оборудования'),
    'maintenance_calendar': ('calendar_evidence', 'Ближайшее ТО выбранного оборудования'),
    'staff_details': ('staff_read', 'Карточки выбранных исполнителей'),
    'staff_assignments': (SOURCE, 'Назначения выбранных исполнителей'),
    'task_details': ('task_read', 'Карточки выбранных заданий'),
    'task_materials': ('task_acceptance_evidence', 'Чек-лист, отчёт, фотографии и препятствия приёмке'),
}
ALLOWED = {
    'equipment': {'equipment_details', 'overdue_tasks', 'latest_maintenance', 'maintenance_history', 'active_regulations', 'maintenance_calendar'},
    'assignee': {'staff_details', 'staff_assignments'},
    'period': set(),
    'task': {'task_details', 'task_materials'},
}
RELATED = {'service_frequency': 'active_regulations',
           'equipment_tasks': 'overdue_tasks'}


def is_dataflow_goal(goal):
    semantic = goal.get('semantic', {})
    return 'analysis_query' in semantic or 'selected_input' in semantic


def compile_analysis(interpretation, question, tools, clock):
    try:
        request = grounded_analysis(question, interpretation, clock)
    except ValueError:
        request = None
    if not request:
        return [], {}, list(interpretation.results)
    requested, history_months = requested_projections(question, request)
    projections = {**dict.fromkeys(request.projections), **requested}
    if 'maintenance_history' in requested and not has(r'последн\w*\s+(?:(?:подтвержд|фактическ)\w*\s+)*(?:то\b|обслуживан\w*)', question):
        projections.pop('latest_maintenance', None)
    if 'task_materials' in projections and request.group_by=='task':
        projections = {'task_details': projections.get('task_details'), **projections}
    remaining = []
    recommendations = recommendation_count(question) or request.recommendations
    for result in interpretation.results:
        intent = result.intent
        projection = RELATED.get(intent, intent)
        if intent == 'aggregate_work':
            continue
        if not result.subjects and projection in ALLOWED[request.group_by]:
            if projection == 'latest_maintenance' and 'maintenance_history' in requested and projection not in projections:
                continue
            if intent != 'equipment_tasks' or result.period == 'overdue':
                projections.setdefault(projection, result.source_text)
            continue
        if intent == 'recommend_actions':
            recommendations = recommendations or result.recommendation_count or 3
            continue
        if not result.subjects and intent in ('explain_results', 'general_explanation', 'task_count', 'task_list'):
            continue
        if request.group_by=='task' and not result.subjects and intent in ('reference_details', 'equipment_tasks'):
            continue
        if intent == 'manufacturer_source' and not primary_document_requested(question):
            continue
        if intent=='other' and (not result.source_text or result.source_text not in question or
                                result.source_text in projections.values()):
            continue
        remaining.append(result)

    source = 'analysis-selection'
    problem = None
    try:
        limit = MAX_AGGREGATE_ROWS if request.all_groups else min(request.limit or 5, MAX_AGGREGATE_ROWS)
        query = AggregateQuery(group_by=request.group_by, metric=request.metric,
                               limit=limit, as_of=request.as_of, windows=request.windows,
                               first_equipment_code=request.first_equipment_code,
                               second_equipment_code=request.second_equipment_code,
                               tie_breaker=request.tie_breaker,
                               include_overdue_tasks='overdue_tasks' in projections and request.group_by=='equipment',
                               include_assignments='staff_assignments' in projections)
    except ValueError:
        query = None
        problem = ('Укажите начало и конец периода для проверки подтверждённого ТО.' if request.metric=='without_service' else
                   'Для отбора нужна поддерживаемая метрика и точные календарные периоды.')
    if SOURCE not in tools:
        problem = 'Сводка нарядов недоступна текущей роли.'
    goals = [GoalSpec(id=source, title='Сводка и отбор по нарядам',
                      tool='' if problem else SOURCE, kind='unavailable' if problem else 'read')]
    meta = {source: dict(intent='aggregate_work', subject=None, source_text=request.source_text,
                         analysis_query=query.model_dump(mode='json') if query else None,
                         all_groups=request.all_groups, requested_limit=request.limit,
                         compare=request.compare or request.group_by=='period' or bool(has(r'сравн\w*|compare',question)),
                         recommendations=recommendations, block=problem)}
    for projection in projections:
        tool, title = TARGETS[projection]
        identity = 'analysis-' + projection
        issue = None
        if projection not in ALLOWED[request.group_by]:
            issue = 'Эта проверка не поддерживается для выбранной группировки.'
        elif tool not in tools:
            issue = 'Источник недоступен текущей роли.'
        months = {'latest_maintenance': history_months or request.history_months,
                  'maintenance_history': history_months or request.history_months,
                  'maintenance_calendar': request.calendar_months}.get(projection)
        if months is not None and not 1 <= months <= 120:
            issue = 'Историю и календарь можно проверить в диапазоне от 1 до 120 месяцев.'
            months = None
        window = None
        if projection in ('latest_maintenance', 'maintenance_history', 'maintenance_calendar'):
            from .analysis_scope import selectors
            try:
                clause = projections[projection] or ''
                if projection == 'maintenance_calendar' and (anchor := has(r'календар\w*|ближайш\w*\s+то\b', clause)):
                    clause = clause[anchor.start():]
                scope = selectors(clause, clock, equipment_scoped=True)
                if {'starts_on', 'ends_on'} <= scope.keys():
                    window = Window(starts_on=scope['starts_on'], ends_on=scope['ends_on'])
            except ValueError:
                issue = 'Укажите допустимый календарный период для этого источника.'
        parent = 'analysis-task_details' if projection=='task_materials' and request.group_by=='task' else source
        binding = SelectedInput(source_goal=parent, projection=projection, months=months, window=window,
                                resource=request.group_by if request.group_by!='period' else None)
        goals.append(GoalSpec(id=identity, title=title, tool='' if issue else tool,
                              kind='unavailable' if issue else 'read', depends_on=[parent]))
        meta[identity] = dict(intent=projection, subject=None, source_text=projections[projection],
                              selected_input=binding.model_dump(),
                              block=issue, disposition='forbidden' if issue and tool not in tools else None)
    return goals, meta, remaining


def query_arguments(query: AggregateQuery):
    arguments = query.model_dump(mode='json', exclude={'windows'}, exclude_none=True)
    for prefix, window in zip(('', 'second_'), query.windows):
        arguments.update({prefix + key: value for key, value in window.model_dump(mode='json').items()})
    return {'query': arguments}
