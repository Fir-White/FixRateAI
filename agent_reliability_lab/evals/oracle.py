"""Expected facts from the synthetic ledger, independent of assistant code."""
from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import text


OPEN = {'draft', 'assigned', 'clarification', 'in_progress', 'in_review', 'rework'}
UUID = re.compile(r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', re.I)


def ledger(engine, site):
    def rows(sql):
        return [dict(row) for row in db.execute(text(sql), {'site': site}).mappings()]

    with engine.connect() as db:
        equipment = rows('''SELECT equipment_id::text AS id, asset_code AS code, name, status, location
                           FROM equipment WHERE site_id=:site''')
        work = rows('''SELECT work_order_id::text AS id, status, planned_start_at AS start,
                           regulatory_deadline_at AS deadline, operation_snapshot AS snapshot
                       FROM work_orders WHERE site_id=:site''')
        links = rows('''SELECT equipment_id::text AS equipment, work_order_id::text AS task
                        FROM work_order_equipment WHERE site_id=:site''')
        assignments = rows('''SELECT work_assignment_id::text AS id, work_order_id::text AS task,
                                  user_id::text AS worker, status
                              FROM work_assignments WHERE site_id=:site''')
        reports = rows('''SELECT r.work_report_id::text AS id, r.work_order_id::text AS task,
                              r.execution_context->>'performed_at' AS performed,
                              EXISTS(SELECT 1 FROM acceptance_reviews a WHERE a.site_id=r.site_id
                                     AND a.work_report_id=r.work_report_id AND a.decision='accepted') AS accepted
                          FROM work_reports r WHERE r.site_id=:site''')
        rules = rows('''SELECT b.binding_id::text AS id, b.equipment_id::text AS equipment,
                            b.valid_from, b.valid_to, m.maintenance_rule_id::text AS rule,
                            m.regulation_edition_id::text AS edition, e.regulation_document_id::text AS document,
                            m.publication_status, e.is_approved
                        FROM rule_equipment b JOIN maintenance_rules m USING (maintenance_rule_id)
                        JOIN regulation_editions e USING (regulation_edition_id) WHERE b.site_id=:site''')
    return dict(equipment={row['code']: row for row in equipment}, work={row['id']: row for row in work},
                links=links, assignments=assignments, reports=reports, rules=rules)


def expectations(kind, subjects, data, now, historical, worker, zone):
    cards = [data['equipment'][code] for code in subjects if code in data['equipment']]
    day = now.astimezone(zone).date()

    def linked(card):
        return {row['task'] for row in data['links'] if row['equipment'] == card['id']}

    def require_card(card):
        return [card['id'], card['code'], card['name'], card['location'],
                {'active': 'в эксплуатации', 'retired': 'выведено из эксплуатации'}[card['status']]]

    def accepted(card):
        return [row['id'] for row in data['reports'] if row['accepted'] and row['task'] in linked(card)]

    def bindings(card):
        return [row['id'] for row in data['rules'] if row['equipment'] == card['id'] and
                row['valid_from'] <= day and (row['valid_to'] is None or day <= row['valid_to']) and
                row['publication_status'] == 'published' and row['is_approved']]

    def compare(cutoff):
        results = []
        for card in cards:
            tasks = [data['work'][identity] for identity in linked(card) & unfinished.keys()]
            overdue = sum(row['deadline'] is not None and row['deadline'] < cutoff for row in tasks)
            results.append((card, len(tasks), overdue))
        return results

    unfinished = {key: row for key, row in data['work'].items() if row['status'] in OPEN}
    assignments = [row for row in data['assignments'] if row['task'] in unfinished and
                   row['status'] not in ('declined', 'cancelled')]
    expected, forbidden, receipts, dates = [], [], [], []
    recommendation_count = None
    empty = kind in ('absent', 'not_visible')
    if kind in ('card', 'card_source'):
        expected = require_card(cards[0])
        forbidden = [row['id'] for row in data['equipment'].values() if row != cards[0]]
        receipts = ['equipment_read']
        if kind == 'card_source':
            expected += ['источник', 'equipment_read']
    if empty:
        forbidden = [row['id'] for row in data['equipment'].values()]
        if cards:
            forbidden += [cards[0]['name'], cards[0]['location']]
    if kind in ('compare', 'historical_compare'):
        cutoff = (datetime.combine(historical + timedelta(days=1), datetime.min.time(), zone)
                  if kind == 'historical_compare' else now)
        rows = compare(cutoff)
        expected = [part for card, total, overdue in rows for part in
                    (card['id'], card['code'], f'незавершённых {total}', f'просроченных {overdue}')]
        if kind == 'historical_compare':
            expected += [str(historical), 'историческ', 'текущ']
        return dict(expected=expected, forbidden=forbidden, receipts=receipts, empty=empty,
                    counts={card['id']: (total, overdue) for card, total, overdue in rows})
    if kind == 'winner_history':
        ordered = sorted(compare(now), key=lambda row: (-row[2], row[0]['id']))
        winner = ordered[0][0]
        expected = [winner['id'], *accepted(winner), *bindings(winner)]
        forbidden = [value for other in data['equipment'].values() if other != winner
                     for value in (other['id'], *accepted(other), *bindings(other))]
        receipts = ['equipment_service_history', 'regulations_read']
    if kind in ('accepted_history', 'active_rule', 'equipment_report'):
        card = cards[0]
        if kind != 'active_rule':
            expected += accepted(card)
            forbidden += [row['id'] for row in data['reports'] if row['id'] not in accepted(card)]
            receipts.append('equipment_service_history')
        if kind != 'accepted_history':
            expected += bindings(card)
            receipts.append('regulations_read')
        if kind == 'equipment_report':
            expected += [card['code'], 'в эксплуатации', 'рекомендац']
            receipts.append('equipment_read')
            dates = [row['deadline'].astimezone(zone).date() for row in unfinished.values()
                     if row['id'] in linked(card) and row['deadline'] and row['deadline'] < now]
            forbidden += [row['id'] for row in unfinished.values()
                          if row['id'] not in linked(card) or not row['deadline'] or row['deadline'] >= now]
            recommendation_count = 2
    if kind in ('own_overdue', 'own_today'):
        own = {row['task'] for row in assignments if row['worker'] == worker}
        if kind == 'own_overdue':
            selected = {identity for identity in own if (row := unfinished[identity])['deadline'] and row['deadline'] < now}
        else:
            selected = {identity for identity in own if (row := unfinished[identity])['start'] and
                        row['start'].astimezone(zone).date() == day}
        expected = [data['work'][identity]['snapshot']['title'] for identity in sorted(selected)]
        forbidden = [identity for identity in data['work'] if identity not in own]
        forbidden += [row['snapshot']['title'] for identity, row in data['work'].items()
                      if identity not in selected and row['snapshot'].get('title')]
        receipts = ['tasks_find']
    if kind == 'oldest_readiness':
        order = min((row for row in unfinished.values() if row['deadline'] and row['deadline'] < now),
                    key=lambda row: (row['deadline'], row['id']))
        expected = [order['id'], 'отчёт', 'отсутств', 'Контроль сварного шва']
        receipts = ['work_order_analytics', 'task_read', 'task_acceptance_evidence']
    if kind == 'workload':
        by_user = {}
        for row in assignments:
            by_user.setdefault(row['worker'], set()).add(row['task'])
        identity, tasks = min(by_user.items(), key=lambda item: (-len(item[1]), item[0]))
        expected = [identity, *sorted(tasks), str(len(tasks)), 'нормативн']
        forbidden = [key for key in set(data['work']) - tasks]
        receipts = ['work_order_analytics']
    return dict(expected=expected, forbidden=forbidden, receipts=receipts, empty=empty,
                dates=[(date.isoformat(), date.strftime('%d.%m.%Y')) for date in dates],
                recommendation_count=recommendation_count)


def grade(expected, response, state, actions, known):
    answer = (response.get('answer') or '').casefold()
    failures = [f'Missing fact {value}' for value in expected['expected'] if str(value).casefold() not in answer]
    failures += [f'Unexpected fact {value}' for value in expected['forbidden'] if str(value).casefold() in answer]
    unexpected_uuids = sorted(set(UUID.findall(answer)) - known)
    failures += [f'Unknown UUID {value}' for value in unexpected_uuids]
    evidence = state.get('evidence', [])
    tools = {item['tool'] for item in evidence}
    failures += [f'Missing receipt {tool}' for tool in expected['receipts'] if tool not in tools]
    for iso, local in expected.get('dates', []):
        if iso not in answer and local not in answer:
            failures.append(f'Missing deadline {iso}')
    if count := expected.get('recommendation_count'):
        recommendations = re.findall(r'(?:^|\n| — )(\d+)\. [^\n]+\bисточник\s+e\d+\b', answer)
        if recommendations != [str(index) for index in range(1, count+1)]:
            failures.append(f'Missing {count} recommendations with receipts')
    counts = expected.get('counts', {})
    rows = sorted((answer.index(identity), identity) for identity in counts if identity in answer)
    for index, (start, identity) in enumerate(rows):
        end = rows[index+1][0] if index+1 < len(rows) else len(answer)
        unfinished, overdue = counts[identity]
        row = answer[start:end].split('\n\n', 1)[0]
        if not re.search(rf'незаверш[её]нн\w*\s+{unfinished}\b\s*[,:·;]?\s*просроч\w*\s+{overdue}\b', row):
            failures.append(f'Wrong or unpaired counts for {identity}: expected {unfinished}/{overdue}')
    if expected['empty']:
        if not re.search(r'не найд|недоступ|нет доступ|нет запис', answer):
            failures.append('Missing explicit unavailable result')
    elif state.get('outcome') != 'completed':
        failures.append(f"Incomplete workflow: {state.get('outcome')}")
    if response.get('status') != 'completed' or response.get('execution_engine') != 'v3':
        failures.append('No completed v3 turn via HTTP')
    if actions:
        failures.append('Unexpected action proposal')
    return failures
