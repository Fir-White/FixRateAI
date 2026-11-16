"""Typed requested read results -> canonical sources and factual shape checks.

This module does not interpret request/title text, authorize requests, access a
database or certify a mutation. Caller must retain normal scope/selector checks,
complete-result checks and fresh authorized transport. Legacy outcome=None does
not opt into a new contract. Tool success alone never repairs a wrong outcome.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID
from app.schemas.assistant import READ_OUTCOME_TOOLS


READ_TARGETS = READ_OUTCOME_TOOLS
READ_EVIDENCE = {outcome: 'calendar_calculation' if outcome == 'calendar_obligations'
                 else 'file_content' if outcome == 'file_analysis' else 'saved_data'
                 for outcome in READ_TARGETS}
REQUIRED_SELECTORS = {
    'staff_profile': ('user_id',), 'staff_search': ('search',),
    'equipment_card': ('equipment_id_or_code',), 'equipment_components': ('equipment_id_or_code',),
    'maintenance_definition': ('operation_id',), 'calendar_obligations': ('equipment_id_or_code', 'starts_on', 'ends_on'),
    'accepted_history': ('equipment_id_or_code', 'starts_on', 'ends_on'), 'task_card': ('task_id',),
    'file_analysis': ('attachment_ids',), 'norm_readiness': ('attachment_ids',),
}
_ROLES = {'director', 'chief_engineer', 'engineer', 'dispatcher', 'admin', 'executor'}


def _mode(tool):
    return tool.get('mode') if isinstance(tool, Mapping) else getattr(tool, 'mode', None)


def resolve_read_contract(goal, authorized_tools):
    """Return routing metadata; this grants no authority and never changes goal.

    status is legacy, preserved, blocked or applied. A blocked canonical source
    must remain blocked; the previously chosen wrong source is not a fallback.
    """
    outcome = goal.get('outcome')
    result = dict(outcome=outcome, target=READ_TARGETS.get(outcome), status='legacy',
                  reason=None, required_evidence=READ_EVIDENCE.get(outcome),
                  required_selectors=list(REQUIRED_SELECTORS.get(outcome, ())))
    if outcome is None or outcome == 'other':
        return result
    if outcome not in READ_TARGETS:
        return {**result, 'status': 'blocked', 'reason': 'unknown_read_outcome'}
    chosen = authorized_tools.get(goal.get('tool'))
    # A forbidden known mutation does not become a read just because the actor's
    # filtered catalog omitted it. Registry metadata is not authorization.
    if chosen is None and goal.get('tool'):
        from .tools import TOOLS
        chosen = next((tool for tool in TOOLS if tool.name == goal['tool']), None)
    if (goal.get('kind') in ('change', 'conversation') or goal.get('mode') == 'write'
            or goal.get('changes') or goal.get('workflow_kind')
            or goal.get('required_evidence') in ('manufacturer_document', 'user_decision')
            or chosen is not None and _mode(chosen) != 'read'):
        return {**result, 'status': 'preserved', 'reason': 'non_read_objective_preserved'}
    target = authorized_tools.get(result['target'])
    if target is None or _mode(target) != 'read':
        return {**result, 'status': 'blocked', 'reason': 'read_outcome_source_not_authorized'}
    required=goal.get('required_evidence')
    expected=result['required_evidence']
    if required is not None and required!=expected and not (required=='saved_data' and expected=='calendar_calculation'):
        return {**result,'status':'blocked','reason':'read_outcome_evidence_mismatch'}
    return {**result, 'status': 'applied'}


def normalize_goal(goal, authorized_tools):
    """Return a copy with canonical read target/evidence and explicit metadata."""
    result = deepcopy(goal)
    contract = resolve_read_contract(goal, authorized_tools)
    if contract['status'] == 'legacy':
        return result
    result['outcome_contract'] = contract
    if contract['status'] == 'applied':
        result.update(tool=contract['target'], kind='read', required_evidence=goal.get('required_evidence') or contract['required_evidence'])
        if goal.get('kind')=='unavailable' and goal.get('reason') in (None,'clarification_or_capability_required'):
            result.update(status='planned',reason=None)
        if goal.get('outcome')=='equipment_inventory':result['requires_full_list']=True
        if goal.get('outcome')=='file_analysis':result.update(response_style='analysis',requires_full_list=True)
    elif contract['status'] == 'blocked':
        result.update(status='blocked', reason=contract['reason'])
    return result


def _uuid(value):
    try:
        return isinstance(value, (str, UUID)) and str(UUID(str(value))) == str(value).lower()
    except (ValueError, TypeError, AttributeError):
        return False


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value, *, nullable=False, positive=False):
    if value is None:
        return nullable
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return False
    try:
        number = Decimal(str(value))
        return number.is_finite() and (number > 0 if positive else number >= 0)
    except (InvalidOperation, ValueError):
        return False


def _date(value, *, nullable=False):
    if value is None:
        return nullable
    try:
        return isinstance(value, date) and not isinstance(value, datetime) or isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _instant(value, *, nullable=False):
    if value is None:
        return nullable
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        return instant.tzinfo is not None
    except (ValueError, TypeError, AttributeError):
        return False


def _list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get('items'), list):
        total = value.get('total', value.get('total_count'))
        if value.get('complete') is False or value.get('has_more') is True or value.get('truncated') is True or value.get('offset', 0) != 0:
            return None
        if total is not None and (type(total) is not int or total != len(value['items'])):
            return None
        return value['items']
    return None


def _all(value, predicate):
    items = _list(value)
    return items is not None and all(isinstance(item, dict) and predicate(item) for item in items)


def _staff(row, *, full=True):
    base = (_uuid(row.get('user_id')) and _text(row.get('full_name')) and _text(row.get('email'))
            and row.get('role') in _ROLES and type(row.get('is_active')) is bool
            and type(row.get('revision')) is int and row['revision'] > 0)
    if not base or not full:
        return bool(base)
    return (all(key in row for key in ('employed_from', 'employed_until'))
            and _date(row['employed_from'], nullable=True) and _date(row['employed_until'], nullable=True)
            and type(row.get('membership_is_active')) is bool and type(row.get('account_is_active')) is bool
            and row['is_active'] is (row['membership_is_active'] and row['account_is_active']))


def _equipment(row):
    return (_uuid(row.get('equipment_id')) and _text(row.get('name')) and _text(row.get('asset_code'))
            and row.get('status') in ('active', 'under_repair', 'retired')
            and type(row.get('revision')) is int and row['revision'] > 0)


def _component(row):
    fields = ('initial_usage', 'current_usage', 'resource_limit', 'remaining_usage', 'resource_basis', 'readings')
    return (all(key in row for key in fields) and _uuid(row.get('component_id')) and _uuid(row.get('equipment_id'))
            and _text(row.get('position_code')) and _text(row.get('name')) and _date(row.get('installed_on'))
            and row.get('usage_unit') in ('hour', 'cycle', 'km')
            and _number(row['initial_usage']) and _number(row['current_usage'])
            and _number(row['resource_limit'], nullable=True, positive=True) and _number(row['remaining_usage'], nullable=True)
            and (row['resource_limit'] is None or _text(row['resource_basis']))
            and row.get('resource_state') in ('available', 'exhausted', 'unknown', 'removed')
            and type(row.get('revision')) is int and row['revision'] > 0 and isinstance(row['readings'], list))


def _operation(row):
    fields = ('crew_size', 'raw_norm_value', 'norm_unit', 'planning_duration_minutes', 'instructions', 'checklist')
    return (all(key in row for key in fields) and _uuid(row.get('operation_id'))
            and all(_text(row.get(key)) for key in ('code', 'title', 'instructions'))
            and (row['crew_size'] is None or type(row['crew_size']) is int and row['crew_size'] > 0)
            and _number(row['raw_norm_value'], nullable=True) and row['norm_unit'] in ('unconfirmed', 'person_hour', 'elapsed_hour')
            and (row['planning_duration_minutes'] is None or type(row['planning_duration_minutes']) is int and row['planning_duration_minutes'] > 0)
            and isinstance(row['checklist'], list) and row.get('status') in ('approved', 'draft', 'retired'))


def _shape(outcome, value):
    if outcome=='equipment_inventory':
        def page(part):
            return (isinstance(part,dict) and isinstance(part.get('items'),list)
                and all(isinstance(row,dict) and _uuid(row.get('id')) and _text(row.get('asset_code'))
                        and _text(row.get('name')) and type(row.get('operations')) is int
                        and type(row.get('published_operations')) is int and isinstance(row.get('planning_gaps'),list)
                        for row in part['items']))
        return isinstance(value,dict) and (all(page(part) for part in value['sites']) if isinstance(value.get('sites'),list) else page(value))
    if outcome == 'current_profile':
        return isinstance(value, dict) and _uuid(value.get('userId')) and _uuid(value.get('siteId')) and value.get('role') in _ROLES and _text(value.get('name')) and _text(value.get('email'))
    if outcome == 'staff_profile':
        return isinstance(value, dict) and _staff(value)
    if outcome == 'staff_search':
        return _all(value, lambda row: _staff(row, full=False))
    if outcome == 'workforce':
        return isinstance(value, dict) and _all(value.get('staff'), _staff) and _all(value.get('crews'), lambda row: _uuid(row.get('id')) and _text(row.get('name')) and isinstance(row.get('members'), list)) and isinstance(value.get('skills'), list) and _text(value.get('timezone'))
    if outcome == 'equipment_card':
        return isinstance(value, dict) and _equipment(value)
    if outcome == 'equipment_search':
        return _all(value, _equipment)
    if outcome == 'equipment_components':
        return _all(value, _component)
    if outcome == 'maintenance_catalog':
        return _all(value, _operation)
    if outcome == 'maintenance_definition':
        return isinstance(value, dict) and _operation(value)
    if outcome == 'reference_catalog':
        return isinstance(value, dict) and all(isinstance(value.get(key), list) for key in ('systems', 'equipment_types', 'operations', 'skills')) and all(_uuid(row.get('id')) and _text(row.get('code')) and _text(row.get('name')) for key in ('systems', 'equipment_types', 'skills') for row in value[key] if isinstance(row, dict)) and all(isinstance(row, dict) for key in ('systems', 'equipment_types', 'operations', 'skills') for row in value[key]) and all(_uuid(row.get('id')) and _text(row.get('code')) and _text(row.get('title')) and _text(row.get('instructions')) for row in value['operations'])
    if outcome == 'personal_notifications':
        return _all(value, lambda row: _uuid(row.get('id')) and _text(row.get('message')) and _instant(row.get('createdAt')) and 'readAt' in row and _instant(row['readAt'], nullable=True))
    if outcome == 'protected_company_code':
        resource = value.get('resource') if isinstance(value, dict) else None
        return (isinstance(value, dict) and 'code' not in value and type(value.get('code_present')) is bool
                and set(value) <= {'code_present', 'protected_output', 'resource', 'note'}
                and value.get('protected_output') is True and isinstance(resource, dict)
                and resource.get('protected') is True and resource.get('url') == '/api/v1/maintenance/management/enrollment')
    if outcome == 'calendar_obligations':
        return isinstance(value, dict) and _uuid(value.get('equipment_id')) and isinstance(value.get('configurations'), list) and type(value.get('complete')) is bool and _text(value.get('timezone'))
    if outcome == 'accepted_history':
        return isinstance(value, dict) and _uuid(value.get('equipment_id')) and _date(value.get('starts_on')) and _date(value.get('ends_on')) and value.get('only_accepted') is True and _list(value) is not None and _text(value.get('source'))
    if outcome == 'task_card':
        task = value.get('task') if isinstance(value, dict) else None
        return isinstance(task, dict) and _uuid(task.get('id')) and type(task.get('revision')) is int and task['revision'] > 0 and _text(task.get('state')) and _text(task.get('summary'))
    if outcome == 'task_analysis':
        return isinstance(value, dict) and (isinstance(value.get('counters'), dict) and _text(value.get('snapshot_id')) or isinstance(value.get('summary'), dict) and isinstance(value.get('sections'), dict) and _text(value.get('snapshot_id')))
    if outcome == 'file_analysis':
        return isinstance(value,dict) and isinstance(value.get('workbook'),dict) and value['workbook'].get('status')=='read' and value['workbook'].get('complete') is True
    if outcome == 'norm_readiness':
        return isinstance(value, dict) and isinstance(value.get('fact'), dict) and value['fact'].get('source') == 'raw_workbook' and value['fact'].get('can_calculate_real_staffing') is False and isinstance(value.get('workbooks'), list) and _text(value.get('report'))
    return False


def validate_result(goal, tool_name, value):
    """Return (valid_shape, reason), separate from factual completeness/scope.

    A blocked/partial domain result may have a valid shape; caller must retain
    that explicit status. This validator never promotes it to completed.
    """
    outcome = goal.get('outcome')
    if outcome is None or outcome == 'other' or goal.get('kind') in ('change', 'conversation', 'unavailable'):
        return True, None
    if tool_name != READ_TARGETS.get(outcome):
        return False, 'read_outcome_source_mismatch'
    try:
        valid = bool(_shape(outcome, value))
    except (ValueError, TypeError, KeyError, AttributeError):
        valid = False
    return (True, None) if valid else (False, 'read_outcome_result_shape_mismatch')
