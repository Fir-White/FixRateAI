"""Conservative business postconditions, independent of model and HTTP success.

Verification never dispatches a mutation. Unknown operations and unreadable or
concurrently changed resources remain unverified. Public evidence contains only
hashes of resource identities, revisions, states and comparison outcomes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text

EQUIPMENT = {'equipment_create', 'equipment_edit'}
TASKS = {'task_assign', 'task_cancel', 'task_start', 'report_save', 'report_submit', 'report_review', 'report_attach_and_submit'}
SUPPORTED = EQUIPMENT | TASKS | {'staff_edit', 'catalog_decision'}
_SUMMARIES = {
    'confirmed': 'Изменение проверено по сохранённому состоянию.',
    'failed': 'Сохранённое состояние не подтверждает запрошенное изменение.',
    'unverified': 'Результат записи требует дополнительной проверки; повторять запись автоматически нельзя.',
}


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _revision(value):
    return value if type(value) is int and value > 0 else None


def _instant(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def _equal(left, right, field=''):
    if field.endswith('_at') or field in ('scheduledStart', 'scheduledEnd'):
        return left is None and right is None or _instant(left) is not None and _instant(left) == _instant(right)
    if field in ('value', 'person_hours'):
        if left is None or right is None:
            return left is right
        try:
            return Decimal(str(left)).is_finite() and Decimal(str(left)) == Decimal(str(right))
        except InvalidOperation:
            return False
    if isinstance(left, (UUID, date, datetime)):
        left = str(left)
    if isinstance(right, (UUID, date, datetime)):
        right = str(right)
    return left == right


def _unwrap(value):
    # Only the two explicit assistant result envelopes are accepted. Arbitrary
    # nested objects, tool text and model-generated success flags are not receipts.
    for _ in range(2):
        if not isinstance(value, dict):
            return None
        if 'data' in value and set(value) <= {'data', 'navigate_to', 'verification'}:
            value = value['data']
        else:
            return value
    return value if isinstance(value, dict) and 'data' not in value else None


def _facts(value):
    value = _unwrap(value)
    if not isinstance(value, dict):
        return {'shape': 'missing'}
    task = value.get('task') if isinstance(value.get('task'), dict) else value
    execution = value.get('execution') if isinstance(value.get('execution'), dict) else {}
    decision = value.get('decision') if isinstance(value.get('decision'), dict) else {}
    facts = {'id': _uuid(task.get('equipment_id') or task.get('id') or task.get('user_id')),
             'revision': _revision(task.get('revision'))}
    states = {'active', 'under_repair', 'retired', 'draft', 'assigned', 'in_progress',
              'submitted', 'accepted', 'rework_required', 'cancelled'}
    state = task.get('state', task.get('status'))
    if isinstance(state, str) and state in states:
        facts['state'] = state
    facts['execution_id'] = _uuid(execution.get('id'))
    facts['decision_id'] = _uuid(decision.get('id'))
    if decision.get('verdict') in ('accepted', 'rejected'):
        facts['verdict'] = decision['verdict']
    return facts


def _outcome(status, reason, before, receipt, after, checks=()):
    evidence = {}
    for label, value in (('before', before), ('receipt', receipt), ('after', after)):
        if value is not None:
            payload = json.dumps(_facts(value), sort_keys=True, separators=(',', ':')).encode()
            evidence[label + '_sha256'] = sha256(payload).hexdigest()
    if checks:
        evidence['checks_sha256'] = sha256(json.dumps(list(checks), separators=(',', ':')).encode()).hexdigest()
    return {'status': status, 'reason': reason, 'summary': _SUMMARIES[status], 'evidence': evidence}


def _equipment_checks(name, body, before, value):
    from app.schemas.management import EquipmentCreate
    checks = []
    wanted = {key: val for key, val in body.items() if key != 'expected_revision'}
    if name == 'equipment_create':
        wanted = EquipmentCreate.model_validate_json(json.dumps(body, default=str)).model_dump(mode='json')
    for field, requested in wanted.items():
        if field == 'data_origin':
            actual = value.get('properties', {}).get('data_origin') if isinstance(value.get('properties'), dict) else None
        elif field == 'properties':
            actual = value.get('properties')
            requested = dict(requested)
            requested['data_origin'] = body.get('data_origin', requested.get('data_origin',
                before.get('properties', {}).get('data_origin', 'customer') if before else 'customer'))
        else:
            actual = value.get(field)
        checks.append(field in value or field == 'data_origin')
        checks.append(_equal(actual, requested, field))
    if name == 'equipment_edit' and before:
        for field in ('system_id', 'equipment_type_id', 'parent_equipment_id', 'asset_code', 'name',
                      'serial_number', 'commissioned_on', 'location', 'status', 'properties'):
            if field not in body and field in before:
                if field == 'properties' and 'data_origin' in body:
                    expected = dict(before[field], data_origin=body['data_origin'])
                else:
                    expected = before[field]
                checks.append(field in value and _equal(expected, value[field], field))
    return checks


def _report_checks(body, before, value):
    execution = value.get('execution')
    if not isinstance(execution, dict):
        return [False]
    checks = [execution.get('state') == 'draft', execution.get('narrative') == body.get('narrative')]
    checklist = execution.get('checklist')
    if not isinstance(checklist, list) or not all(isinstance(item, dict) for item in checklist):
        return [False]
    answers = {str(item.get('id')): item.get('answer') for item in checklist}
    requested = body.get('answers')
    if not isinstance(requested, dict):
        return [False]
    checks.extend(str(key) in answers and answers[str(key)] == val for key, val in requested.items())
    previous = before.get('execution') if isinstance(before, dict) else None
    if isinstance(previous, dict):
        checks.append(execution.get('id') == previous.get('id'))
        checks.extend(answers.get(str(item.get('id'))) == item.get('answer')
                      for item in previous.get('checklist', []) if str(item.get('id')) not in requested)
        checks.append(execution.get('photos') == previous.get('photos'))
    actual = execution.get('actual')
    desired = body.get('actual')
    if desired is None:
        checks.append(actual == {})
    elif isinstance(actual, dict) and isinstance(desired, dict):
        checks.extend(_equal(actual.get(key), desired.get(key), key)
                      for key in ('started_at', 'performed_at', 'person_hours'))
    else:
        checks.append(False)
    readings = execution.get('readings')
    desired_readings = body.get('readings', [])
    if not isinstance(readings, list) or not isinstance(desired_readings, list) or len(readings) != len(desired_readings):
        checks.append(False)
    else:
        for wanted in desired_readings:
            checks.append(isinstance(wanted, dict) and any(isinstance(row, dict) and all(
                field in row and _equal(row[field], wanted.get(field), field)
                for field in ('equipment_id', 'parameter_code', 'value', 'unit', 'measured_at', 'phase')) for row in readings))
    return checks


def _task_checks(name, body, before, value):
    task = value.get('task')
    if not isinstance(task, dict):
        return [False]
    execution = value.get('execution')
    states = {'task_cancel': 'cancelled', 'task_start': 'in_progress', 'report_save': 'in_progress',
              'report_submit': 'submitted', 'report_review': 'accepted' if body.get('verdict') == 'accepted' else 'rework_required'}
    checks = []
    if name == 'task_assign':
        expected_state = 'rework_required' if before and before.get('task', {}).get('state') in ('in_progress', 'rework_required') else 'assigned'
        checks.append(task.get('state') == expected_state)
        wanted = body.get('executor_ids')
        found = task.get('assignees')
        checks.append(isinstance(wanted, list) and bool(wanted) and isinstance(found, list)
                      and all(isinstance(item, dict) for item in found)
                      and {_uuid(item.get('executorId')) for item in found} == {_uuid(item) for item in wanted}
                      and None not in {_uuid(item) for item in wanted})
        checks.extend(_equal(task.get(field), body.get(key), key)
                      for field, key in (('scheduledStart', 'start_at'), ('scheduledEnd', 'end_at')))
    else:
        checks.append(task.get('state') == states[name])
    if name in ('task_start', 'report_save', 'report_submit', 'report_review'):
        if not isinstance(execution, dict):
            return [False]
        checks.extend((_uuid(execution.get('id')) is not None,
                       execution.get('taskId') == task.get('id'), task.get('activeExecutionId') == execution.get('id')))
    previous = before.get('execution') if isinstance(before, dict) else None
    if name == 'task_start':
        checks.append(execution.get('state') == 'draft')
        if isinstance(previous, dict):
            checks.append(execution.get('id') != previous.get('id'))
    if name == 'report_save':
        checks.extend(_report_checks(body, before, value))
    if name == 'report_submit':
        checks.extend((execution.get('state') == 'submitted', _instant(execution.get('submittedAt')) is not None))
        if isinstance(previous, dict):
            checks.append(execution.get('id') == previous.get('id'))
            checks.extend(execution.get(field) == previous.get(field) for field in ('narrative', 'checklist', 'photos', 'readings'))
    if name == 'report_review':
        decision = value.get('decision')
        if not isinstance(decision, dict) or body.get('verdict') not in ('accepted', 'rejected'):
            return [False]
        checks.extend((_uuid(decision.get('id')) is not None, decision.get('taskId') == task.get('id'),
                       decision.get('executionId') == str(body.get('execution_id')),
                       execution.get('id') == str(body.get('execution_id')), decision.get('verdict') == body['verdict'],
                       decision.get('reason') == str(body.get('reason', '')).strip(),
                       _instant(decision.get('decidedAt')) is not None))
    if name == 'task_cancel':
        checks.append(task.get('assignees') == [])
    return checks


def _staff_postcondition(arguments, receipt, before, after):
    """Membership PUT has a revision-only receipt, never a resource identity.

    Bind the actual scoped read to the validated path and preflight snapshot.
    The account flag and the membership flag are independent server facts.
    """
    def result(status, reason, checks=()):
        return _outcome(status, reason, before, receipt, after, checks)
    body = arguments['body']
    path = arguments.get('path', {})
    identity = _uuid(path.get('user_id')) if isinstance(path, dict) else None
    if not identity:
        return result('unverified', 'command_identity_missing')
    if not isinstance(before, dict):
        return result('unverified', 'before_snapshot_required')
    if _uuid(before.get('user_id')) != identity:
        return result('unverified', 'before_identity_missing_or_mismatched')
    if _uuid(after.get('user_id')) != identity:
        return result('unverified', 'readback_identity_missing_or_mismatched')
    revision = _revision(body.get('expected_revision'))
    if revision is None:
        return result('unverified', 'expected_revision_missing')
    if _revision(before.get('revision')) != revision:
        return result('unverified', 'before_revision_mismatch')
    if _revision(receipt.get('revision')) != revision + 1:
        return result('unverified', 'receipt_revision_mismatch')
    if _revision(after.get('revision')) != revision + 1:
        return result('unverified', 'readback_revision_changed')
    from app.schemas.management import EmploymentEdit
    try:
        wanted = EmploymentEdit.model_validate_json(json.dumps(body, default=str)).model_dump(mode='json', exclude_unset=True)
    except (ValueError, TypeError):
        return result('unverified', 'invalid_command')
    fields = ('role', 'membership_is_active', 'account_is_active', 'is_active',
              'employed_from', 'employed_until', 'full_name', 'email')
    flags = ('membership_is_active', 'account_is_active', 'is_active')
    if any(field not in value for value in (before, after) for field in fields) or any(
            type(value[field]) is not bool for value in (before, after) for field in flags):
        return result('unverified', 'unsupported_result_shape')
    checks = [after['role'] == wanted['role'],
              after['membership_is_active'] is wanted['is_active'],
              after['is_active'] is (after['membership_is_active'] and after['account_is_active']),
              before['is_active'] is (before['membership_is_active'] and before['account_is_active'])]
    for field in ('employed_from', 'employed_until'):
        checks.append(_equal(after[field], wanted[field] if field in wanted else before[field], field))
    checks.extend(_equal(after[field], before[field], field)
                  for field in ('full_name', 'email', 'account_is_active'))
    if not all(checks):
        return result('failed', 'postcondition_mismatch', checks)
    return result('confirmed', 'postcondition_verified', checks)


def verify_postcondition(tool_name, arguments, receipt, before=None, after=None):
    """Verify known operation semantics from validated server data, never text.

    A fresh authorized readback is required. A matching receipt alone does not
    prove the resource is still in that state. A newer read revision is reported
    as unverified, because a concurrent legitimate edit may explain it.
    """
    def result(status, reason, checks=()):
        return _outcome(status, reason, before, receipt, after, checks)
    if tool_name not in SUPPORTED:
        return result('unverified', 'unsupported_postcondition')
    receipt, after, before = _unwrap(receipt), _unwrap(after), _unwrap(before)
    if not isinstance(arguments, dict) or not isinstance(arguments.get('body'), dict):
        return result('unverified', 'invalid_command')
    if not receipt or not after:
        return result('unverified', 'readback_or_receipt_missing')
    if tool_name == 'staff_edit':
        return _staff_postcondition(arguments, receipt, before, after)
    body = arguments['body']
    if tool_name == 'catalog_decision':
        from app.schemas.catalog_decisions import DecisionCommand

        try:
            expected = DecisionCommand.model_validate(body).model_dump(mode='json')
        except ValidationError:
            return result('unverified', 'invalid_command')
        revision = expected['expected_revision']
        row = arguments.get('path', {}).get('number')
        if type(row) is not int or row < 1:
            return result('unverified', 'invalid_command')
        if after.get('revision') != revision + 1:
            return result('unverified', 'readback_revision_changed')
        checks = [bool(before) and before.get('revision') == revision]
        for value in (receipt, after):
            checks.extend((value.get('row_number') == row, value.get('revision') == revision + 1,
                           value.get('confirmed') is expected['confirm'],
                           value.get('decision') == expected['decision'],
                           value.get('reason') == expected['reason']))
        return result('confirmed' if all(checks) else 'failed',
                      'postcondition_verified' if all(checks) else 'postcondition_mismatch', checks)
    equipment = tool_name in EQUIPMENT
    key = 'equipment_id' if equipment else 'task_id'
    identity = receipt.get(key) if equipment else receipt.get('task', {}).get('id') if isinstance(receipt.get('task'), dict) else None
    expected_id = arguments.get('path', {}).get(key) if isinstance(arguments.get('path', {}), dict) else None
    if tool_name == 'equipment_create':
        expected_id = identity
    if not _uuid(expected_id) or _uuid(identity) != _uuid(expected_id):
        return result('unverified', 'receipt_identity_missing_or_mismatched')
    latest = after if equipment else after.get('task')
    saved = receipt if equipment else receipt['task']
    old = before if equipment else before.get('task') if before else None
    if not isinstance(latest, dict) or _uuid(latest.get('equipment_id' if equipment else 'id')) != _uuid(expected_id):
        return result('unverified', 'readback_identity_missing_or_mismatched')
    expected_revision = 1 if tool_name == 'equipment_create' else (_revision(body.get('expected_revision')) or 0) + 1
    if expected_revision <= 1 and tool_name != 'equipment_create':
        return result('unverified', 'expected_revision_missing')
    if _revision(saved.get('revision')) != expected_revision:
        return result('unverified', 'receipt_revision_mismatch')
    if _revision(latest.get('revision')) != expected_revision:
        return result('unverified', 'readback_revision_changed')
    if old and _revision(old.get('revision')) != expected_revision - 1:
        return result('unverified', 'before_revision_mismatch')
    try:
        if tool_name == 'report_attach_and_submit':
            ids = receipt['attached_photo_ids']
            outcome = receipt['submission']
            state = {'submitted':'submitted', 'draft_incomplete':'in_progress'}[outcome]
            old_photos = {p['id'] for p in before['execution']['photos']}
            checks = [len(set(ids)) == len(body['photos']) == len(ids), not set(ids) & old_photos,
                      all(_uuid(identity) for identity in ids)]
            for value in (receipt, after):
                report = value['execution']
                photos = {p['id']: p for p in report['photos']}
                checks += [value['task']['state'] == state, report['id'] == body['execution_id'],
                           value['task']['activeExecutionId'] == report['id'],
                           set(photos) == old_photos | set(ids),
                           (_instant(report['submittedAt']) is not None) == (outcome == 'submitted')]
                for identity, binding in zip(ids, body['photos'], strict=True):
                    photo = photos.get(identity, {})
                    checks += [photo.get('phase') == binding['phase'],
                               photo.get('viewKey') == binding['view_key'],
                               photo.get('checklistItemId') == binding['checklist_item_id']]
        else:
            check = _equipment_checks if equipment else _task_checks
            checks = check(tool_name, body, before, receipt) + check(tool_name, body, before, after)
    except (ValueError, TypeError, KeyError, AttributeError):
        return result('unverified', 'unsupported_result_shape')
    if not checks or not all(checks):
        return result('failed', 'postcondition_mismatch', checks)
    verified = result('confirmed', 'postcondition_verified', checks)
    if tool_name == 'report_attach_and_submit':
        if receipt['submission'] == 'submitted':
            verified['summary'] = 'Фото прикреплены. Отчёт передан инженеру на проверку.'
        else:
            details = '; '.join(receipt.get('missing_materials', [])[:12]) or receipt.get('submission_block')
            verified['summary'] = ('Фото сохранены в черновике. Отчёт не отправлен: '
                                   + (details or 'комплект неполный.'))[:1800]
    return verified


async def verify_action(app, tool, arguments, receipt, headers, before=None):
    """Read only through the same scoped API transport as execution."""
    if tool.name not in SUPPORTED:
        return verify_postcondition(tool.name, arguments, receipt, before)
    from .tools import invoke, validate_arguments
    # The caller pins EXPECTED_PRINCIPAL; the downstream authenticated endpoint
    # rechecks it. A tool descriptor does not confer authorization.
    from .tools import TOOLS
    try:
        if tool.name in EQUIPMENT:
            value = _unwrap(receipt)
            identity = arguments.get('path', {}).get('equipment_id') if tool.name == 'equipment_edit' else value.get('equipment_id') if value else None
            name, path = 'equipment_read', {'equipment_id': identity}
        elif tool.name == 'staff_edit':
            name, path = 'staff_read', arguments.get('path', {})
        elif tool.name == 'catalog_decision':
            name, path = 'catalog_decision_read', arguments.get('path', {})
        else:
            name, path = 'task_read', arguments.get('path', {})
        read = next(item for item in TOOLS if item.name == name)
        after = await invoke(app, read, validate_arguments(app, read, {'path': path}), headers)
    except Exception:
        # Never publish exception messages: backend failures may contain inputs.
        return _outcome('unverified', 'authorized_readback_failed', before, receipt, None)
    return verify_postcondition(tool.name, arguments, receipt, before, after)


def mark_interrupted_actions(session, *, conversation_id, cutoff):
    """CAS stale dispatch claims to uncertain; caller authorizes scope/commits.

    No mutation is dispatched or retried. A late original response can still
    replace this diagnostic state with its actual result.
    """
    if not _uuid(conversation_id) or not isinstance(cutoff, datetime) or cutoff.tzinfo is None:
        raise ValueError('An authorized conversation and timezone-aware cutoff are required')
    outcome = _outcome('unverified', 'dispatch_interrupted', None, None, None)
    result = session.execute(text("""UPDATE assistant_actions
        SET status='uncertain', finished_at=now(), result=CAST(:result AS jsonb)
        WHERE conversation_id=:conversation AND status='executing'
          AND started_at IS NOT NULL AND started_at<:cutoff"""),
        {'conversation': conversation_id, 'cutoff': cutoff,
         'result': json.dumps({'message': _SUMMARIES['unverified'], 'verification': outcome}, ensure_ascii=False)})
    return result.rowcount
