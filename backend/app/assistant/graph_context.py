"""Deterministic plans and reference binding for an equipment comparison."""
from datetime import date
import re

from sqlalchemy import text

from .analysis_scope import _months_before
from .intents import mutation_command_requested
from .inventory_report import label
from .semantic_plan import ASSET, NAMED_ASSET, QUOTED, RequestedResult, RequestedResults, asset_references


COMPARE_FIELD = (r'(?:состояни\w*|статус\w*|количеств\w*|числ\w*|незаверш[её]н\w*|'
                 r'открыт\w*|задани\w*|работ\w*|просроч\w*|и)')
COMPARISON = re.compile(
    rf'\s*(?:сравни|сопоставь)(?:те)?\s+(?:оборудование\s+)?'
    rf'{ASSET}\s+(?:и|с)\s+{ASSET}'
    rf'(?:\s+по\s+{COMPARE_FIELD}(?:[, ]+{COMPARE_FIELD})*)?[.!?]?\s*',
    re.I,
)
COMPARE_FOLLOWUP = re.compile(
    r'\b(?:оборудован\w*|агрегат\w*)\s+(?:с\s+(?:(?:больш\w*|наибольш\w*|максимальн\w*)\s+'
    r'(?:числ\w*|количеств\w*)\s+просроч\w*)|у\s+котор\w*\s+больше\s+просроч\w*)',
    re.I,
)
COMPARISON_REFERENCE = re.compile(
    r'\b(?:предыдущ\w*\s+сравнен\w*|сравниваем\w*\s+пар\w*|вернись\s+к\s+сравнен\w*)\b', re.I)
FOLLOWUP_FIELDS = (r'(?:(?:действующ\w*\s+)?регламент\w*|истори\w*\s+(?:то\b|обслуживани\w*)|'
                   r'(?:выбранн\w*\s+)?uuid|и)')
EXECUTOR_TODAY = re.compile(r'\s*(?:какие у меня сегодня задания|покажи мои задания на сегодня)[.!?]?\s*', re.I)
EXECUTOR_OVERDUE = re.compile(r'\s*(?:что из моих работ просрочено|покажи мои просроченные задания)[.!?]?\s*', re.I)
PRONOUN = re.compile(
    r'\s*(?:а\s+)?(?:теперь\s+)?(?:проверь|покажи|прочитай|перечисли)\s+(?:все\s+)?(?:его|е[её])\s+'
    r'(?:(?P<rules>(?:действующ\w*\s+)?регламент\w*)|(?P<tasks>задани\w*)|'
    r'(?P<history>истори\w*\s+(?:то\b|обслуживани\w*)))[.!?]?\s*', re.I,
)
NAMED_LOOKUP = re.compile(
    r'\s*(?:найди|отыщи|покажи|открой)(?:те)?\s+(?:оборудовани\w*|агрегат\w*)\s+' +
    NAMED_ASSET + rf'(?:{QUOTED.pattern})[.!?]?\s*'
    r'(?:если\s+(?:(?:вариантов|записей)\s+)?(?:несколько|больше\s+одной)\s*,\s*'
    r'(?:покажи|перечисли|укажи)\s+(?:их\s+)?(?:инвентарные\s+)?коды'
    r'(?:\s+и\s+(?:попроси\s+выбрать|уточни\s+выбор))?[.!?]?\s*)?', re.I)


def comparison_request(question):
    codes = asset_references(question)
    return codes if len(codes) == 2 and COMPARISON.fullmatch(question) else []


def saved_comparison(session, conversation_id, turn_id, question):
    if not COMPARISON_REFERENCE.search(question):
        return None
    return session.execute(text('''
        SELECT turn_id,status,workflow FROM assistant_turns
         WHERE conversation_id=:chat AND turn_id<>:turn AND status='completed'
           AND (workflow->'engineering_request'->>'kind'='equipment_comparison'
             OR workflow->'request_spec'->'requirements' @> '[{"intent":"equipment_comparison"}]'::jsonb)
         ORDER BY created_at DESC,turn_id DESC LIMIT 1
    '''), dict(chat=conversation_id, turn=turn_id)).mappings().first()


def fast_plan(question, history, scope, clock):
    if scope['role'] == 'executor' and (period := executor_period(question)):
        return RequestedResults(read_only=True, results=[
            RequestedResult(intent='task_list', period=period)
        ]), question
    lookup = re.fullmatch(rf'\s*(?:найди|покажи|открой)(?:те)?\s+(?:карточку\s+)?'
                          rf'(?:оборудования?\s+)?({ASSET})[.!?]?\s*', question, re.I)
    subject = lookup[1] if lookup else None
    if not subject and (named := NAMED_LOOKUP.fullmatch(question)):
        subject = (named[1] or named[2]).strip()
    if subject:
        return RequestedResults(read_only=True, results=[
            RequestedResult(intent='equipment_details', subjects=[subject],
                            fields=['id', 'code', 'name', 'state', 'location'])
        ]), question
    if codes := comparison_request(question):
        return RequestedResults(read_only=True, results=[
            RequestedResult(intent='equipment_details', subjects=codes, fields=['id', 'code', 'name', 'state', 'location']),
            *[RequestedResult(intent='equipment_tasks', subjects=codes, period=period)
              for period in ('all', 'overdue')],
        ]), question
    if pronoun := PRONOUN.fullmatch(question):
        previous = previous_workflow(history, scope)
        if not previous:
            return None, question
        references = {str(proof['entity']['equipment_id']) for proof in previous['evidence']
                      if proof.get('tool') in ('equipment_read', 'regulations_read', 'equipment_service_history')
                      and proof.get('complete') and proof.get('retained') and proof['scope'] == scope
                      and proof.get('entity', {}).get('equipment_id')}
        if len(references) == 1:
            intent = {'rules': 'active_regulations', 'tasks': 'equipment_tasks',
                      'history': 'maintenance_history'}[pronoun.lastgroup]
            return with_equipment(question, references.pop(), [intent], clock)
        return None, question
    return None, question


def comparison_followup_plan(question, history, scope, clock):
    match = COMPARE_FOLLOWUP.search(question)
    if not match or mutation_command_requested(question) or asset_references(question):
        return None
    intents = []
    if re.search(r'\bрегламент\w*', question, re.I):
        intents.append('active_regulations')
    if re.search(r'\bистори\w*\s+(?:то\b|обслуживани\w*)', question, re.I):
        intents.append('maintenance_history')
    explicit = bool(COMPARISON_REFERENCE.search(question))
    if not intents or not supported_followup(question, match, explicit):
        return None
    previous = previous_workflow(history, scope)
    comparison = comparison_result(previous) if previous else []
    if not comparison:
        kind = (previous or {}).get('engineering_request', {}).get('kind')
        if explicit and kind == 'equipment_comparison':
            from .dependent_execution import read_selection
            selection, proof = read_selection(previous, 'analysis-selection')
            if selection and selection.query.first_equipment_code and len(selection.groups) == 2:
                winner, other = sorted(selection.groups, key=lambda row: (-row.overdue, row.id))
                plan, planning_text = with_equipment(question, str(winner.id), intents, clock)
                return plan, planning_text, dict(kind='current_comparison_followup', equipment_id=str(winner.id),
                    code=winner.code, counts=[winner.overdue, other.overdue], source=proof['id'],
                    comparison_day=selection.as_of.isoformat(), historical=selection.historical_cutoff)
        if explicit:
            missing = RequestedResults(read_only=True, results=[RequestedResult(intent=intent) for intent in intents])
            return missing, question, {'kind': 'missing_comparison'}
        return None
    winner, other = sorted(comparison, key=lambda row: (-row['overdue']['total'], row['id']))
    plan, planning_text = with_equipment(question, winner['id'], intents, clock)
    return plan, planning_text, dict(kind='current_comparison_followup', equipment_id=winner['id'],
        code=winner['code'], counts=[winner['overdue']['total'], other['overdue']['total']],
        source=f"{winner['overdue']['proof']}, {other['overdue']['proof']}", source_tool='tasks_find')


def supported_followup(question, match, explicit):
    action = r'(?:проверь|покажи|возьми|выбери)'
    fields = rf'{FOLLOWUP_FIELDS}(?:[, ]+{FOLLOWUP_FIELDS})*'
    if not explicit:
        prefix = re.fullmatch(rf'\s*(?:а\s+)?(?:теперь\s+)?{action}\s+', question[:match.start()], re.I)
        suffix = re.fullmatch(rf'\s*[,.:]?\s*(?:(?:проверь|покажи|прочитай|укажи)\s+)?{fields}[.!?]?\s*',
                              question[match.end():], re.I)
        return bool(prefix and suffix)
    supported = (
        r'(?:теперь\s+)?вернись\s+к\s+(?:предыдущ\w*\s+)?сравнен\w*',
        rf'из\s+(?:предыдущ\w*\s+сравнен\w*|сравниваем\w*\s+пар\w*)\s+{action}\s+{COMPARE_FOLLOWUP.pattern}',
        r'при\s+равенств\w*\s+(?:используй|выбери|возьми)\s+(?:меньш\w*|наименьш\w*|минимальн\w*)\s+uuid',
        rf'(?:покажи|укажи|проверь|прочитай)\s+{fields}',
    )
    clauses = [part.strip() for part in re.split(r'[.!?;\n]+', question) if part.strip()]
    return all(any(re.fullmatch(pattern, part, re.I) for pattern in supported) for part in clauses)


def previous_workflow(history, scope):
    previous = next((row['workflow'] for row in history
                     if row['status'] == 'completed' and row.get('workflow')), None)
    return previous if previous and previous['scope'] == scope else None


def with_equipment(question, identity, intents, clock):
    grounded = f'{question}\nВыбранное оборудование {identity}'
    if {'maintenance_history','latest_maintenance'}.intersection(intents):
        end = date.fromisoformat(clock['local_date'])
        grounded += f'\nПериод истории ТО с {_months_before(end, 12)} по {end}'
    return RequestedResults(read_only=True, results=[
        RequestedResult(intent=intent, subjects=[identity]) for intent in intents
    ]), grounded


def executor_period(question):
    if EXECUTOR_TODAY.fullmatch(question):
        return 'all'
    if EXECUTOR_OVERDUE.fullmatch(question):
        return 'overdue'
    return None


def comparison_result(state):
    codes = comparison_request(state['request'])
    if not codes:
        return []
    rows = {code.casefold(): {} for code in codes}
    evidence = {item['id']: item for item in state['evidence']}
    for goal in state['goals']:
        meta = goal.get('semantic', {})
        subject = str(meta.get('subject') or '').casefold()
        if goal['status'] != 'completed' or subject not in rows:
            continue
        sources = [evidence[item] for item in goal['evidence_ids'] if item in evidence
                   and evidence[item]['tool'] == goal['tool'] and evidence[item]['scope'] == state['scope']]
        if not sources:
            continue
        proof = sources[-1]
        value = proof['result']
        if meta['intent'] == 'equipment_details' and proof['complete']:
            if value.get('asset_code', '').casefold() == subject and value.get('equipment_id'):
                rows[subject].update(id=value['equipment_id'], code=value['asset_code'], name=value['name'],
                                     card=value, card_proof=proof['id'])
        if meta['intent'] == 'equipment_tasks' and (proof['complete'] or proof['limitations'] == ['page_only']):
            selected = value.get('filters', {}).get('equipment_id')
            total = value.get('total')
            if selected and type(total) is int and total >= 0 and value.get('timezone') == state['scope']['timezone']:
                rows[subject][meta['period']] = dict(total=total, id=selected, proof=proof['id'])
    result = list(rows.values())
    if len({row.get('id') for row in result}) != 2 or any(
        not row.get('id') or not row.get('all') or not row.get('overdue')
        or row['id'] != row['all']['id'] or row['id'] != row['overdue']['id']
        or row['overdue']['total'] > row['all']['total'] for row in result
    ):
        return []
    return result


def comparison_answer(state):
    rows = comparison_result(state)
    if not rows:
        return None
    leading, other = sorted(rows, key=lambda row: (-row['overdue']['total'], row['id']))
    from .semantic_execution import _row
    totals = []
    for row in rows:
        card = _row(row['card'], ['name', 'state'], 'equipment_id')
        totals.append(f'- {label(row["code"])} · {row["id"]} · незавершённых {row["all"]["total"]} · '
                      f'просроченных {row["overdue"]["total"]}. {card}. '
                      f'Источники {row["card_proof"]}, {row["all"]["proof"]}, {row["overdue"]["proof"]}.')
    conclusion = (
        f'Одинаковое число просрочек. При выборе используется меньший UUID, {leading["id"]}.'
        if leading['overdue']['total'] == other['overdue']['total']
        else f'Больше просрочек у {label(leading["code"])}. Разница — {leading["overdue"]["total"] - other["overdue"]["total"]}.'
    )
    return '\n'.join([*totals, conclusion])
