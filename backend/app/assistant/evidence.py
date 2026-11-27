"""Independent consistency gates for complete analytical evidence, before rendering prose."""
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
import re
from typing import Literal

class InconsistentEvidence(ValueError):
    """Reason is a constant field category; never contains source data or secrets."""

def require(condition,reason):
    if not condition:raise InconsistentEvidence(reason)

def integer(value):return isinstance(value,int) and not isinstance(value,bool) and value>=0

def number(value):
    try:result=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):raise InconsistentEvidence('invalid_effort') from None
    require(result.is_finite() and result>=0,'invalid_effort')
    return result

def counts(value,reason):
    require(isinstance(value,dict) and all(isinstance(k,str) and integer(v) for k,v in value.items()),reason)
    return sum(value.values())

def summary(data,principal=None,expected_clock=None):
    require(isinstance(data,dict) and data.get('complete') is True,'incomplete_snapshot')
    require(isinstance(data.get('snapshot_id'),str) and re.fullmatch('[0-9a-f]{64}',data['snapshot_id']),'snapshot_identity')
    try:
        instant=datetime.fromisoformat(data['checked_at']);zone=ZoneInfo(data['timezone']);day=date.fromisoformat(data['local_date'])
        require(instant.tzinfo is not None and instant.astimezone(zone).date()==day,'server_clock')
        if expected_clock is not None:
            require(abs((instant-datetime.fromisoformat(expected_clock['checked_at'])).total_seconds())<=60,'stale_server_clock')
    except (KeyError,ValueError,TypeError,ZoneInfoNotFoundError):raise InconsistentEvidence('server_clock') from None
    scope=data.get('scope');counters=data.get('counters')
    require(isinstance(scope,dict) and isinstance(counters,dict),'scope_or_counters')
    if principal is not None:
        for key,attribute in (('site_id','site_id'),('role','role')):
            expected=getattr(principal,attribute,None)
            if expected is not None:require(scope.get(key)==str(expected),'principal_scope')
        if getattr(principal,'timezone',None) is not None:require(data['timezone']==principal.timezone,'principal_timezone')
    for key in ('all_tasks','execution_pending','unfinished','scheduled_unfinished','completed','cancelled'):
        require(integer(counters.get(key)),'counter_types')
    states=counters.get('by_status');all_count=counts(states,'status_counts')
    require(integer(data.get('scanned_tasks')) and all_count==counters['all_tasks']==data['scanned_tasks'],'all_counter')
    require(counts(counters.get('by_origin'),'origin_counts')==all_count,'origin_counts')
    pending=('draft','assigned','clarification','rework')
    require(counters['execution_pending']==sum(states.get(s,0) for s in pending),'pending_counter')
    require(counters['unfinished']==sum(states.get(s,0) for s in (*pending,'in_progress','in_review')),'unfinished_counter')
    require(counters['completed']==states.get('completed',0) and counters['cancelled']==states.get('cancelled',0),'terminal_counter')
    selected=data.get('selected_tasks')
    require(integer(selected) and selected<=counters['unfinished']<=all_count,'selection_count')
    require(counters['scheduled_unfinished']<=counters['unfinished'],'scheduled_counter')
    if scope.get('origin')=='all' and scope.get('cohort','unfinished')=='unfinished' and not scope.get('starts_on') and not scope.get('ends_on'):
        require(selected==counters['unfinished'],'unfiltered_selection')
        require(counts(data.get('execution_pending_due'),'pending_due')==counters['execution_pending'],'pending_due')
    for key in ('due','scheduled','norm_checks'):require(counts(data.get(key),key)==selected,key+'_sum')
    number(data.get('known_person_hours'))
    require(integer(data.get('unknown_effort_tasks')) and data['unknown_effort_tasks']<=selected,'unknown_effort')
    duplicate=data.get('business_duplicates')
    require(isinstance(duplicate,dict),'duplicate_counts')
    require(all(integer(duplicate.get(k)) for k in ('candidate_groups','candidate_tasks','unchecked_tasks')),'duplicate_counts')
    require(duplicate['candidate_groups']*2<=duplicate['candidate_tasks']<=selected,'duplicate_counts')
    require(duplicate['candidate_tasks']+duplicate['unchecked_tasks']<=selected,'duplicate_coverage')
    if 'sample' in data:
        require(isinstance(data['sample'],list) and len(data['sample'])<=min(25,selected),'sample_count')
        require(data.get('sample_total')==selected and data.get('sample_truncated') is (len(data['sample'])<selected),'sample_scope')
    return data

def page(data,offset):
    require(isinstance(data,dict) and integer(data.get('total')) and integer(data.get('offset')) and data['offset']==offset and data.get('limit')==25,'page_scope')
    items=data.get('items')
    require(isinstance(items,list) and len(items)<=25 and offset+len(items)<=data['total'],'page_cardinality')
    require(bool(items) or offset>=data['total'],'empty_partial_page')
    return items

def details(data,equipment,dates,groups):
    selected=data['selected_tasks']
    require(all(isinstance(row,dict) for row in [*equipment,*dates,*groups]),'detail_rows')
    require(all(isinstance(row,dict) and integer(row.get('tasks')) for row in dates),'date_rows')
    require(sum(row['tasks'] for row in dates)==selected,'date_sum')
    require(len({row.get('date') for row in dates})==len(dates),'duplicate_date_rows')
    for row in dates:
        require(integer(row.get('planned_tasks')) and integer(row.get('deadline_only_tasks')),'date_scope')
        require(row['planned_tasks']+row['deadline_only_tasks']==row['tasks'],'date_scope')
    require(sum((number(row.get('known_person_hours')) for row in dates),Decimal(0))==number(data['known_person_hours']),'date_effort')
    require(all(integer(row.get('unknown_effort_tasks')) for row in dates),'date_effort')
    require(sum(row['unknown_effort_tasks'] for row in dates)==data['unknown_effort_tasks'],'date_effort')
    require(len({row.get('id') for row in equipment})==len(equipment),'duplicate_equipment_rows')
    require(all(integer(row.get('tasks')) and row['tasks']<=selected for row in equipment),'equipment_counts')
    # A multi-asset task appears in each asset; never equate this sum to task count.
    require(sum(row['tasks'] for row in equipment)>=selected,'missing_equipment_coverage')
    for row in equipment:
        ops=row.get('operations');total=row.get('operations_total')
        require(isinstance(ops,list) and integer(total) and len(ops)<=min(25,total),'operation_scope')
        require(row.get('operations_truncated') is (len(ops)<total),'operation_scope')
        require(all(isinstance(op,dict) and integer(op.get('tasks')) and op['tasks']<=row['tasks'] for op in ops),'operation_counts')
        if not row['operations_truncated']:require(sum(op['tasks'] for op in ops)==row['tasks'],'operation_sum')
        for op in ops:require(counts(op.get('norm_checks'),'operation_norm')==op['tasks'],'operation_norm')
    dup=data['business_duplicates']
    require(len(groups)==dup['candidate_groups'],'duplicate_group_count')
    require(all(integer(row.get('count')) and row['count']>=2 for row in groups),'duplicate_group_size')
    require(sum(row['count'] for row in groups)==dup['candidate_tasks'],'duplicate_task_count')


EvidenceStatus = Literal['FOUND', 'EMPTY', 'PARTIAL', 'MISSING_INPUT', 'FORBIDDEN',
                         'UNAVAILABLE', 'ERROR', 'STALE']


def failure_status(http_status: int) -> EvidenceStatus:
    if http_status in (401, 403):
        return 'FORBIDDEN'
    if http_status in (404, 502, 503, 504):
        # A concealed access denial and a missing selected entity share a 404.
        # Neither proves an empty, authorized collection.
        return 'UNAVAILABLE'
    if http_status == 422:
        return 'MISSING_INPUT'
    return 'ERROR'


def result_status(value, complete, limitations) -> EvidenceStatus:
    if isinstance(value, dict):
        upstream = value.get('status')
        if upstream in ('forbidden', 'access_denied'):
            return 'FORBIDDEN'
        if upstream in ('needs_input', 'missing_input'):
            return 'MISSING_INPUT'
        if upstream == 'stale':
            return 'STALE'
        if upstream in ('unavailable', 'blocked'):
            return 'UNAVAILABLE'
        if upstream in ('error', 'failed', 'invalid_configuration'):
            return 'ERROR'
    if 'read_outcome_result_shape_mismatch' in limitations:
        return 'ERROR'
    if not complete:
        return 'PARTIAL'
    if value == []:
        return 'EMPTY'
    if isinstance(value, dict):
        if value.get('items') == [] and (value.get('total') == 0 or value.get('matched_reports') == 0):
            return 'EMPTY'
        if value.get('configurations') == []:
            return 'EMPTY'
    return 'FOUND'


def provenance(arguments, kind):
    path = arguments.get('path') or {}
    query = arguments.get('query') or {}
    keys = ('equipment_id', 'task_id', 'user_id', 'operation_id', 'attachment_id', 'binding_id')
    return dict(source_type=kind, entity={key: path.get(key, query.get(key)) for key in keys
                if key in path or key in query},
                period={key: query[key] for key in ('starts_on', 'ends_on') if key in query})
