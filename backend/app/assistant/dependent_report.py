"""Deliver analytical conclusions exclusively from verified result receipts."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

from .dependent_execution import read_selection
from .dependent_planning import is_dataflow_goal, query_arguments
from .semantic_execution import TASK_STATES, collection_lines


def display(value):
    return re.sub(r'[\[\]<>`*\\]', '', ' '.join(str(value).split()))[:240]


def reference(proof):
    return f'Источник {proof["id"]} · {proof["tool"]}.'


def missing(goal, proof):
    title = goal['title']
    if proof and proof.get('limitations'):
        detail = next((reason.removeprefix('tool_error_') for reason in proof['limitations']
                       if reason.startswith('tool_error_')), None)
        if detail:
            return f'{title} · чтение не выполнено (HTTP {detail}). {reference(proof)}'
    cause = goal['semantic'].get('block')
    if goal.get('reason')=='aggregate_output_invalid':
        cause = 'Источник вернул несогласованные данные. Рейтинг не подтверждён.'
    elif goal.get('reason')=='dependency_output_unavailable':
        cause = 'Подтверждённой выборки ID для чтения нет.'
    return f'{title} · {cause or "результат не подтверждён."}'


def row_detail(goal, proof, selection):
    if not proof or not proof['retained'] or proof['status'] not in ('FOUND','EMPTY','PARTIAL'):
        return [missing(goal, proof)], None
    if set(proof['limitations']) - {'partial_result', 'undated_facts', 'conflicting_facts', 'page_only', 'blocked_result'}:
        return [missing(goal, proof)], None
    value = proof['result']
    projection = goal['semantic']['selected_input']['projection']
    complete = proof['complete']
    source = reference(proof)
    if projection == 'overdue_tasks':
        rows = value['items']
        lines = [f'Просроченные работы · показано {len(rows)} из {value["total"]}. {source}']
        lines.extend(f'- {display(row["title"])} · нормативный срок {row["deadline_on"]} · '
                     f'задание `{row["task_id"]}`.' for row in rows)
        if not complete:
            lines.append('Показана часть работ. Число просрочек посчитано по всей выборке.')
        return lines, None
    if projection in ('latest_maintenance', 'maintenance_history'):
        period = f'{value["starts_on"]} — {value["ends_on"]}'
        verified = [item for item in value['items'] if item['actual_date_verified'] and not item['actual_date_conflict']]
        if projection == 'maintenance_history':
            lines = [f'История принятого ТО ({period}). {source}']
            rows = [f'- {datetime.fromisoformat(item["performed_at"]).astimezone(ZoneInfo(value["timezone"])).date()}'
                    f' · отчёт `{item["report_id"]}`.' for item in verified]
            if not rows and complete:
                return [*lines, 'В источнике принятых отчётов в периоде нет.'], source
            lines.extend(collection_lines(rows, total=value['total'], complete=complete, location='карточку оборудования'))
            return lines, source if complete else None
        if verified:
            item = verified[0]
            day = datetime.fromisoformat(item['performed_at']).astimezone(ZoneInfo(value['timezone'])).date()
            label = 'Последнее подтверждённое ТО' if complete else 'Подтверждённая дата ТО в доступной части истории'
            suffix = '' if complete else ' Полнота фактических дат не подтверждена.'
            return [f'{label} · {day}, отчёт `{item["report_id"]}` ({period}). {source}{suffix}'], source
        result = ('принятых отчётов в периоде нет' if complete else
                  'по доступным отчётам фактическая дата не подтверждена')
        return [f'Фактическое ТО ({period}) · {result}. {source}'], source
    if projection == 'active_regulations':
        day = selection.as_of.isoformat()
        active = [item for item in value if item['enabled'] and item['valid_from']<=day and
                  (item['valid_until'] is None or item['valid_until']>=day)]
        lines = [f'Действующие регламенты на {day}. {source}']
        lines.extend(f'- {display(item["title"])} · версия {item["rule_version"]}, '
                     f'привязка `{item["binding_id"]}`.' for item in active)
        if not active and complete:
            lines.append('В прочитанной конфигурации действующих регламентов нет.')
        if not complete:
            lines.append('Полнота перечня регламентов не подтверждена.')
        return lines, source if complete else None
    if projection == 'maintenance_calendar':
        configs = value['configurations']
        scheduled = [(item['effective_date'], config['source']['binding_id'])
                     for config in configs for item in config['occurrences']]
        period = f'{value["starts_on"]} — {value["ends_on"]}'
        if scheduled:
            day, binding = min(scheduled)
            name = 'Ближайший нормативный срок ТО' if complete else 'Первая дата в доступной части расчёта ТО'
            return [f'{name} · {day}, привязка `{binding}` ({period}). {source}'], source
        result = ('в проверенном горизонте нормативная дата отсутствует' if complete else
                  'календарный расчёт недоступен для одной или нескольких действующих конфигураций')
        return [f'Ближайший нормативный срок ТО ({period}) · {result}. {source}'], source
    if projection == 'staff_details':
        return [f'Профиль исполнителя · {display(value["full_name"])}. {source}'], source
    if projection == 'staff_assignments':
        lines = [f'Открытые назначения · показано {len(value["items"])} из {value["total"]}. {source}']
        lines.extend(f'- {display(row["title"])} · задание `{row["task_id"]}` · назначение `{row["assignment_id"]}`'
                     + (f' · {row["start_at"]} — {row["end_at"]}.' if row['start_at'] else ' · время начала не задано.')
                     for row in value['items'])
        return lines, None
    if projection == 'task_details':
        task = value['task']
        return [f'Карточка `{task["id"]}` · {display(TASK_STATES.get(task["state"],task["state"]))}. {source}'], None
    if projection == 'task_materials':
        report_status = {None:'отсутствует','draft':'черновик','submitted':'отправлен'}
        lines = [f'Отчёт · {report_status[value["report_state"]]}' +
                 (f' · попытка `{value["execution_id"]}`' if value['execution_id'] else '') + f'. {source}',
                 f'Чек-лист · {len(value["checklist"])} пунктов.']
        lines.extend(f'- {display(item["text"])} · ' +
                     (f'ответ: {display(item["answer"])}.' if item.get('answer') is not None else 'ответ отсутствует.')
                     for item in value['checklist'])
        lines.append(f'Доступные файлы фото · {len(value["photos"])}. Состояние сохранённого анализа · '
                     + display({'ready':'доступен','pending':'в ожидании','failed':'недоступен',
                                'not_requested':'отсутствует'}.get(value['saved_photo_analysis'],value['saved_photo_analysis'])) + '.')
        lines.extend(f'- Фото `{p["id"]}` · {"до" if p["phase"]=="before" else "после"} · {display(p["view"])}.'
                     for p in value['photos'])
        if value['photo_classification']:
            lines.append(f'Оценка сохранённого анализа фото · {display(value["photo_classification"])}.')
        blocks = [*value['missing_materials'], *value['acceptance_blocks']]
        lines.append('Готовность к приёмке · препятствия по доступным данным:' if blocks else
                     'Готовность к приёмке · по проверенным материалам препятствий не найдено. Решение принимает контролёр.')
        lines.extend(f'- {display(item)}.' for item in blocks)
        return lines, None
    status = TASK_STATES.get(value['status'], value['status'])
    return [f'Карточка оборудования · {display(status)}. {source}'], source


def render(state):
    goals = [goal for goal in state['goals'] if is_dataflow_goal(goal)]
    root = next((goal for goal in goals if goal['id']=='analysis-selection'), None)
    if root is None:
        return None
    for goal in goals:
        goal['answer_delivery'] = {'complete': False}
    selection, proof = read_selection(state, root['id'])
    if selection is None:
        failed = next((item for item in reversed(state['evidence']) if item['goal_id']==root['id']), None)
        return '## Подтверждённые факты\n\n' + missing(root, failed)
    main_ref = reference(proof)
    root['answer_delivery'] = {'complete': True}
    meta = root['semantic']
    groups = selection.groups
    projections = [goal for goal in goals if goal['id']!=root['id']]
    evidence = {proof['id']: proof for proof in state['evidence']}
    bindings = {goal['id']: {link['entity_id']: link for link in goal.get('bindings', [])} for goal in projections}
    delivered = {goal['id']: set() for goal in projections}
    facts = [f'Объект `{selection.site_id}` · {selection.timezone} · срез на {selection.as_of}. {main_ref}']
    conclusions = []
    observations = []
    if selection.historical_cutoff:
        facts.append('Нормативные сроки сопоставлены с запрошенной датой. Состояния заданий взяты из текущего реестра.')
    if selection.query.group_by=='period':
        for row in groups:
            facts.append(f'- {row.window.starts_on} — {row.window.ends_on}: запланировано {row.planned}, '
                         f'незавершённых {row.unfinished}, просроченных {row.overdue}.')
        delta = groups[1].planned - groups[0].planned
        conclusions.append(f'Изменение числа запланированных работ во втором периоде · {delta:+d}. {main_ref}')
        conclusions.append('Сравнение построено по сохранённому плановому началу работ в часовом поясе объекта.')
    else:
        requested_count = selection.eligible_groups if meta.get('all_groups') else meta.get('requested_limit') or selection.query.limit
        facts.append(f'Подходящих записей {selection.eligible_groups}, выбрано {len(groups)} из запрошенных {requested_count}.')
        if root.get('reason') == 'aggregate_selection_limited':
            query = query_arguments(selection.query)['query']
            if selection.query.metric in ('overdue', 'unfinished'):
                query.update(offset=len(groups))
                facts.append('[Открыть следующую страницу рейтинга](/api/v1/assistant/workspace/work-order-analytics?'
                             + urlencode(query) + ').')
        if selection.query.metric=='without_service':
            window = selection.query.windows[0]
            facts.append(f'Период принятого фактического ТО · {window.starts_on} — {window.ends_on}.')
            if selection.unresolved_groups:
                facts.append(f'По {selection.unresolved_groups} единицам факт нельзя проверить из-за спорных или неизвестных дат.')
            if len(groups)<selection.eligible_groups:
                facts.append(f'Перечень частичный. Показано {len(groups)} из {selection.eligible_groups}.')
        if selection.query.group_by=='task' and selection.tied_groups>1:
            facts.append(f'Одинаковый нормативный срок имеют {selection.tied_groups} заданий. '
                         'Для чтения порядок определяет UUID. Это правило не задаёт приоритет приёмки.')
        for index, row in enumerate(groups, 1):
            state_text = f' · {display(TASK_STATES.get(row.state, row.state))}' if row.state else ''
            code = f' · {display(row.code)}' if row.code else ''
            facts.extend(['', f'**{index}. {display(row.label)}{code} · `{row.id}`{state_text}**'])
            if selection.query.group_by=='task':
                facts.append(f'Нормативный срок · {row.deadline_on or "не указан"}.')
            elif selection.query.metric=='without_service':
                facts.append('В указанном периоде подтверждённое ТО отсутствует.')
            else:
                facts.append(f'Незавершённых {row.unfinished}, просроченных {row.overdue}, '
                             f'без нормативной даты {row.undated}.' +
                             (f' Самый ранний нарушенный срок {row.oldest_due}.' if row.oldest_due else ''))
            for goal in projections:
                bound = bindings[goal['id']].get(str(row.id))
                observed = evidence.get(bound['evidence_id']) if bound else None
                lines, source = row_detail(goal, observed, selection)
                facts.extend(lines)
                if (observed and observed.get('complete') and lines and any(reference(observed) in line for line in lines)
                        and lines != [missing(goal, observed)]):
                    delivered[goal['id']].add(str(row.id))
                if source and goal['semantic']['selected_input']['projection'] != 'equipment_details':
                    observations.append((row, goal['semantic']['selected_input']['projection'], source,
                                         evidence[bound['evidence_id']]['result']))
        if not groups:
            conclusions.append('По указанной метрике нет объектов для проверки. ' + main_ref)
        elif meta['compare'] and len(groups)>1 and selection.query.metric in ('overdue','unfinished'):
            first, second = groups[:2]
            metric = selection.query.metric
            attribute = {'overdue':'просроченных', 'unfinished':'незавершённых'}[metric]
            if getattr(first, metric) > getattr(second, metric):
                conclusions.append(f'Первым проверьте {display(first.label)} · {getattr(first, metric)} '
                                   f'{attribute} против {getattr(second, metric)} у {display(second.label)}. {main_ref}')
            elif first.oldest_due and (not second.oldest_due or first.oldest_due < second.oldest_due):
                conclusions.append(f'При равном числе {attribute} первым проверьте {display(first.label)} · '
                                   f'самый ранний нарушенный срок {first.oldest_due}. {main_ref}')
            else:
                conclusions.append(f'По числу {attribute} и возрасту просрочки сравниваемые записи равны. {main_ref}')
            history = [(row, data, src) for row, projection, src, data in observations
                       if row in groups[:2] and projection in ('latest_maintenance', 'maintenance_history')
                       and data['items'] and data['complete']]
            if len(history)==2:
                dates = [datetime.fromisoformat(data['items'][0]['performed_at']).astimezone(
                         ZoneInfo(data['timezone'])).date() for _, data, _ in history]
                dates_label = ('совпадает' if dates[0]==dates[1] else
                               f'для первой записи {dates[0]}, для второй {dates[1]}')
                conclusions.append(f'Дата последнего подтверждённого ТО {dates_label}. '
                                   + ' '.join(src for _, _, src in history))
            regulations = [(value, src) for row, projection, src, value in observations
                           if row in groups[:2] and projection=='active_regulations']
            if len(regulations)==2:
                day = selection.as_of.isoformat()
                counts = [sum(item['enabled'] and item['valid_from']<=day and
                              (item['valid_until'] is None or item['valid_until']>=day) for item in value)
                          for value, _ in regulations]
                conclusions.append(f'Действующих сохранённых регламентов у первой записи {counts[0]}, '
                                   f'у второй {counts[1]}. ' + ' '.join(src for _, src in regulations))
        elif meta['compare'] and len(groups)==1:
            conclusions.append('Для сравнения найдена только одна подходящая запись. ' + main_ref)
        if selection.query.group_by=='equipment' and meta['compare'] and any(row.overdue for row in groups):
            conclusions.append('Просрочки обосновывают приоритет проверки. Аварийное состояние требует отдельных фактических признаков.')
    if any(goal['status']!='completed' for goal in projections):
        conclusions.append('Выводы по недоступным или неполным источникам ограничены показанными фактами.')
    recommendations = []
    count = meta.get('recommendations')
    if count and groups and selection.query.group_by!='period':
        for row in groups[:2]:
            if row.overdue:
                recommendations.append(f'Разберите просроченные работы {display(row.label)}, начав со срока '
                                       f'{row.oldest_due}. В реестре {row.overdue} просроченных работ. {main_ref}')
            else:
                recommendations.append(f'Проверьте очередь {display(row.label)} · открыто {row.unfinished} работ. {main_ref}')
        rules = next(((row, src, value) for row, projection, src, value in observations
                      if projection=='active_regulations'), None)
        if rules:
            row, src, value = rules
            day = selection.as_of.isoformat()
            active = any(item['enabled'] and item['valid_from']<=day and
                         (item['valid_until'] is None or item['valid_until']>=day) for item in value)
            action = ('Сверьте применимость действующих регламентов перед назначением ТО'
                      if active else 'Проверьте публикацию применимого регламента. Действующей конфигурации в источнике нет')
            recommendations.append(f'{action} для «{display(row.label)}». {src}')
        elif observations:
            row, projection, src, _ = observations[0]
            action = {'latest_maintenance': 'сверьте фактическое ТО по принятым отчётам',
                      'maintenance_history': 'сверьте фактическое ТО по принятым отчётам',
                      'maintenance_calendar': 'сверьте следующий нормативный срок по календарю',
                      'staff_details': 'сверьте распределение работ по найденному профилю'}[projection]
            recommendations.append(f'Для «{display(row.label)}» {action}. {src}')
    for goal in projections:
        goal['answer_delivery'] = dict(complete=len(delivered[goal['id']]) == len(groups), rows=len(delivered[goal['id']]))
    comparable = selection.query.group_by == 'period' or len(groups) >= 2 and selection.query.metric in ('overdue', 'unfinished')
    state['analytical_delivery'] = dict(compare='completed' if meta['compare'] and comparable else 'incomplete',
                                        recommendations='completed' if count and len(recommendations)>=count else 'incomplete')
    sections = ['## Подтверждённые факты', '\n'.join(facts)]
    if conclusions:
        sections.extend(['## Инженерные выводы', '\n\n'.join(conclusions)])
    if count:
        actions = [f'{i}. {action}' for i, action in enumerate(recommendations[:count], 1)]
        if len(actions)<count:
            actions.append(f'Подтверждённых фактов хватило для {len(actions)} из {count} действий.')
        sections.extend(['## Рекомендуемые действия', '\n'.join(actions)])
    return '\n\n'.join(sections)
