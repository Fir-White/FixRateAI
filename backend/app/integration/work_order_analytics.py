"""Scoped work-order aggregation in a single PostgreSQL snapshot per analysis."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text

from app.assistant.analysis_contract import AggregateQuery, AggregateResult
from .management import _guard
from .task_analytics import UNFINISHED


OVERDUE_DETAILS_LIMIT = 100

LEDGER = '''
WITH ledger AS MATERIALIZED (
    SELECT w.work_order_id, w.site_id, w.status, w.operation_snapshot AS snapshot,
           w.status = ANY(:unfinished_states) AS is_unfinished,
           w.regulatory_deadline_at AS deadline_at,
           coalesce(s.regulatory_deadline_on,
                    timezone(:zone, w.regulatory_deadline_at - interval '1 microsecond')::date) AS deadline_on,
           timezone(:zone, w.planned_start_at)::date AS planned_on,
           coalesce(w.operation_snapshot->>'title', w.operation_snapshot->>'label', op.title, 'Работа') AS title
    FROM work_orders w
    LEFT JOIN schedule_entries s ON s.site_id=w.site_id AND s.schedule_entry_id=w.schedule_entry_id
    LEFT JOIN maintenance_rules r ON r.site_id=w.site_id AND r.maintenance_rule_id=w.maintenance_rule_id
    LEFT JOIN operation_templates op ON op.site_id=w.site_id AND op.operation_template_id=r.operation_template_id
    WHERE w.site_id=:site AND (:own_only=false OR EXISTS (
        SELECT 1 FROM work_assignments a
        WHERE a.site_id=w.site_id AND a.work_order_id=w.work_order_id AND a.user_id=:user_id
          AND a.status NOT IN ('cancelled','declined')
    ))
), work AS MATERIALIZED (
    SELECT *, is_unfinished AND coalesce(
        CASE WHEN :historical THEN deadline_at < :cutoff ELSE deadline_at <= :cutoff END,
        deadline_on < :as_of, false
    ) AS is_overdue
    FROM ledger
)
'''

EQUIPMENT_LINK = '''
    JOIN work_order_equipment l ON l.site_id=w.site_id AND l.work_order_id=w.work_order_id
    JOIN equipment e ON e.site_id=l.site_id AND e.equipment_id=l.equipment_id
'''
ASSIGNEE_LINK = '''
    JOIN work_assignments a ON a.site_id=w.site_id AND a.work_order_id=w.work_order_id
        AND a.status NOT IN ('cancelled','declined')
    JOIN site_memberships m ON m.site_id=a.site_id AND m.user_id=a.user_id
    JOIN users u ON u.user_id=m.user_id
'''

EQUIPMENT_COMPARISON = '''
SELECT e.equipment_id AS id, e.name AS label, e.asset_code AS code, e.status AS state,
       count(w.work_order_id) AS unfinished, count(w.work_order_id) FILTER (WHERE w.is_overdue) AS overdue,
       count(w.work_order_id) FILTER (WHERE w.deadline_on IS NULL AND w.deadline_at IS NULL) AS undated,
       min(w.deadline_on) FILTER (WHERE w.is_overdue) AS oldest_due
FROM equipment e
LEFT JOIN work_order_equipment l USING (site_id,equipment_id)
LEFT JOIN work w ON w.site_id=l.site_id AND w.work_order_id=l.work_order_id AND w.is_unfinished
WHERE e.site_id=:site AND upper(e.asset_code) IN (upper(:first_code),upper(:second_code))
  AND (NOT :own_only OR EXISTS (SELECT 1 FROM work lw JOIN work_order_equipment ll USING (site_id,work_order_id)
                                WHERE ll.site_id=e.site_id AND ll.equipment_id=e.equipment_id))
GROUP BY e.equipment_id,e.name,e.asset_code,e.status
ORDER BY overdue DESC,e.equipment_id
'''

GROUPING = '''
, linked AS MATERIALIZED (
    SELECT DISTINCT {identity} AS id, {label} AS label, {code} AS code, {state} AS state,
           w.work_order_id, w.status, w.title, w.deadline_at, w.deadline_on, w.is_overdue
    FROM work w {joins}
    WHERE w.is_unfinished AND (
        CAST(:starts_on AS date) IS NULL OR coalesce(w.planned_on,w.deadline_on) BETWEEN :starts_on AND :ends_on
    )
), counts AS (
    SELECT id, label, code, state, count(*) AS unfinished, count(*) FILTER (WHERE is_overdue) AS overdue,
           count(*) FILTER (WHERE deadline_on IS NULL AND deadline_at IS NULL) AS undated,
           min(deadline_on) FILTER (WHERE is_overdue) AS oldest_due
    FROM linked
    GROUP BY id,label,code,state
), ranked AS (
    SELECT *,
           row_number() OVER (ORDER BY {metric} DESC, {rank_tie}) AS position
    FROM counts
    WHERE {metric} > 0
    ORDER BY position LIMIT :limit OFFSET :offset
)
SELECT ranked.*, totals.eligible_groups, CASE WHEN :details AND ranked.id IS NOT NULL THEN (
    SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY d.deadline_on, d.deadline_at NULLS LAST, d.task_id), '[]')
    FROM (
        SELECT l.work_order_id AS task_id, l.title, l.status AS state, l.deadline_at, l.deadline_on
        FROM linked l WHERE l.id=ranked.id AND l.is_overdue
        ORDER BY l.deadline_on, l.deadline_at NULLS LAST, l.work_order_id LIMIT :details_limit
    ) d
) END AS overdue_tasks, CASE WHEN :assignments THEN (
    SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY d.start_at NULLS LAST, d.task_id), '[]')
    FROM (
        SELECT * FROM (
        SELECT DISTINCT ON (l.work_order_id) a.work_assignment_id AS assignment_id,
               l.work_order_id AS task_id,l.title,l.status AS state,a.status,a.start_at,a.end_at,l.deadline_on
        FROM linked l JOIN work_assignments a ON a.site_id=:site AND a.work_order_id=l.work_order_id
          AND a.user_id=ranked.id AND a.status NOT IN ('cancelled','declined')
        WHERE l.id=ranked.id
        ORDER BY l.work_order_id,a.work_assignment_id
        ) unique_tasks ORDER BY start_at NULLS LAST,task_id LIMIT :details_limit
    ) d
) END AS assignments, CASE WHEN :assignments THEN ranked.unfinished END AS assignment_total
FROM (SELECT count(*) AS eligible_groups FROM counts WHERE {metric} > 0) totals
LEFT JOIN ranked ON true ORDER BY position
'''

PERIODS = '''
SELECT w.slot, count(work.work_order_id) AS planned,
       count(*) FILTER (WHERE work.is_unfinished) AS unfinished,
       count(*) FILTER (WHERE work.is_overdue) AS overdue,
       count(*) FILTER (WHERE work.is_unfinished AND work.deadline_on IS NULL AND work.deadline_at IS NULL) AS undated
FROM (VALUES (1, CAST(:start_one AS date), CAST(:end_one AS date)),
             (2, CAST(:start_two AS date), CAST(:end_two AS date))) w(slot, starts_on, ends_on)
LEFT JOIN work ON work.planned_on BETWEEN w.starts_on AND w.ends_on AND work.status <> 'cancelled'
GROUP BY w.slot ORDER BY w.slot
'''


def performed_sql(value):
    return (f"CASE WHEN {value} ~ '[Tt].*(Z|[+-][0-9]{{2}}:[0-9]{{2}})$' "
            f"AND pg_input_is_valid({value},'timestamp with time zone') THEN ({value})::timestamptz END")


def service_gap_sql():
    reported = performed_sql("r.execution_context->>'performed_at'")
    accepted = performed_sql("a.decision_context->>'performed_at'")
    return f'''
    WITH facts AS (
        SELECT l.equipment_id, r.work_report_id, coalesce({accepted}, {reported}) actual, a.reviewed_at,
               ({accepted}) IS NOT NULL AND ({reported}) IS NOT NULL AND ({accepted})<>({reported}) AS conflict
        FROM work_order_equipment l
        JOIN work_reports r USING(site_id,work_order_id)
        JOIN LATERAL (
            SELECT ar.reviewed_at,ar.decision_context FROM acceptance_reviews ar
            WHERE ar.site_id=r.site_id AND ar.work_order_id=r.work_order_id
              AND ar.work_report_id=r.work_report_id AND ar.decision='accepted'
            ORDER BY ar.reviewed_at DESC,ar.acceptance_review_id DESC LIMIT 1
        ) a ON true
        WHERE l.site_id=:site AND (:own_only=false OR EXISTS (
            SELECT 1 FROM work_assignments w WHERE w.site_id=l.site_id AND w.work_order_id=l.work_order_id
              AND w.user_id=:user_id AND w.status NOT IN ('cancelled','declined')
        ))
    ), counts AS (
        SELECT equipment_id,
               bool_or(actual IS NOT NULL AND NOT conflict AND actual<=reviewed_at AND
                       timezone(:zone,actual)::date BETWEEN :starts_on AND :ends_on) AS found,
               bool_or(actual IS NULL OR conflict OR actual>reviewed_at) AS unresolved
        FROM facts GROUP BY equipment_id
    ), classified AS MATERIALIZED (
        SELECT e.equipment_id AS id,e.name AS label,e.asset_code AS code,e.status AS state,
               coalesce(c.found,false) AS found,coalesce(c.unresolved,false) AS unresolved
        FROM equipment e LEFT JOIN counts c USING(equipment_id)
        WHERE e.site_id=:site AND (:own_only=false OR EXISTS (
            SELECT 1 FROM work_order_equipment l JOIN work_assignments w USING(site_id,work_order_id)
            WHERE l.site_id=e.site_id AND l.equipment_id=e.equipment_id AND w.user_id=:user_id
              AND w.status NOT IN ('cancelled','declined')
        ))
    ), summary AS (
        SELECT count(*) FILTER (WHERE NOT found AND NOT unresolved) AS eligible_groups,
               count(*) FILTER (WHERE NOT found AND unresolved) AS unresolved_groups FROM classified
    )
    SELECT summary.*, selected.id, selected.label, selected.code, selected.state
    FROM summary LEFT JOIN LATERAL (
        SELECT * FROM classified WHERE NOT found AND NOT unresolved ORDER BY code,id LIMIT :limit
    ) selected ON true ORDER BY selected.code,selected.id
    '''


MATERIAL_FILTER = '''
    LEFT JOIN LATERAL (
        SELECT r.work_report_id,r.checklist_snapshot,r.execution_context
        FROM work_reports r WHERE r.site_id=w.site_id AND r.work_order_id=w.work_order_id
        ORDER BY r.revision_no DESC LIMIT 1
    ) report ON true
    WHERE w.is_unfinished AND (
        report.work_report_id IS NULL OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(report.checklist_snapshot) item
            WHERE (coalesce((item->>'required')::boolean,true) AND NOT EXISTS (
                SELECT 1 FROM checklist_results cr WHERE cr.site_id=w.site_id AND cr.work_report_id=report.work_report_id
                  AND cr.checklist_template_id::text=item->>'id' AND trim(coalesce(cr.response_value->>'answer',''))<>''
                  AND (item->>'answerKind'<>'boolean' OR cr.response_value->>'answer'='done')
            )) OR (coalesce((item->>'photoRequired')::boolean,false) AND NOT EXISTS (
                SELECT 1 FROM evidence_files b JOIN evidence_files a ON a.site_id=b.site_id
                  AND a.work_report_id=b.work_report_id AND a.checklist_item_id=b.checklist_item_id
                  AND a.view_key=b.view_key AND a.stage='after'
                WHERE b.site_id=w.site_id AND b.work_report_id=report.work_report_id
                  AND b.checklist_item_id::text=item->>'id' AND b.stage='before'
            ))
        ) OR EXISTS (
            SELECT 1 FROM jsonb_array_elements_text(coalesce(w.snapshot->'required_acts','[]')) required(kind)
            WHERE NOT EXISTS (SELECT 1 FROM evidence_files p WHERE p.site_id=w.site_id
                AND p.work_report_id=report.work_report_id AND p.stage='other'
                AND p.verification_context->>'kind'=required.kind)
        ) OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(w.snapshot->'measurement_requirements','[]')) req
            CROSS JOIN LATERAL jsonb_array_elements_text(coalesce(req->'phases','["before","after"]')) p(phase)
            WHERE coalesce((req->>'required')::boolean,true) AND NOT EXISTS (
                SELECT 1 FROM work_readings r WHERE r.site_id=w.site_id AND r.work_report_id=report.work_report_id
                  AND r.parameter_code=req->>'parameter_code' AND r.unit_code=req->>'unit' AND r.phase=p.phase
            )
        ) OR (w.snapshot->>'methodology_ref' IS NOT NULL AND (
            nullif(report.execution_context->>'started_at','') IS NULL OR
            nullif(report.execution_context->>'performed_at','') IS NULL OR
            nullif(report.execution_context->>'person_hours','') IS NULL
        ))
    )
'''


TASK_SELECTION = '''
, candidates AS (
    SELECT w.* FROM work w {predicate}
      AND (CAST(:starts_on AS date) IS NULL OR coalesce(w.planned_on,w.deadline_on) BETWEEN :starts_on AND :ends_on)
), ranked AS (
    SELECT work_order_id AS id,title AS label,status AS state,deadline_at,deadline_on,
           deadline_on AS oldest_due,1 AS unfinished, is_overdue::integer AS overdue,
           (deadline_on IS NULL)::integer AS undated,count(*) OVER () AS eligible_groups,
           count(*) OVER (PARTITION BY {tie_columns}) AS tied_groups,
           row_number() OVER (ORDER BY {rank_order}) AS position
    FROM candidates
)
SELECT * FROM ranked ORDER BY position LIMIT :limit
'''


def aggregate(views, query: AggregateQuery, *, now=None):
    principal = views.principal
    if query.group_by in ('assignee', 'period'):
        _guard(views, 'director', 'admin', 'dispatcher', 'engineer')
    zone = ZoneInfo(principal.timezone)
    instant = now or datetime.now(timezone.utc)
    local_day = instant.astimezone(zone).date()
    as_of = query.as_of or local_day
    if as_of > local_day:
        raise HTTPException(422, 'Будущий срез просрочек не подтверждается текущими состояниями заданий.')
    historical = as_of < local_day
    cutoff = (datetime.combine(as_of + timedelta(days=1), time.min, zone) if historical else instant)
    params = dict(site=principal.site_id, user_id=principal.user_id, zone=principal.timezone,
                  cutoff=cutoff, as_of=as_of, historical=historical, own_only=principal.role=='executor',
                  unfinished_states=list(UNFINISHED))
    extra = {}
    window = query.windows[0] if query.windows else None
    scope = dict(starts_on=window.starts_on if window else None, ends_on=window.ends_on if window else None,
                 limit=query.limit, offset=query.offset)
    if query.first_equipment_code:
        records = views.session.execute(text(LEDGER + EQUIPMENT_COMPARISON),
            {**params,'first_code':query.first_equipment_code,'second_code':query.second_equipment_code}).mappings().all()
        if len(records) != len({row['code'].casefold() for row in records}):
            raise HTTPException(409, 'Инвентарный код неоднозначен в пределах текущего объекта.')
        groups = [dict(row) for row in records]
        eligible = len(groups)
    elif query.group_by == 'period':
        first, second = query.windows
        records = views.session.execute(text(LEDGER + PERIODS), {
            **params, 'start_one': first.starts_on, 'end_one': first.ends_on,
            'start_two': second.starts_on, 'end_two': second.ends_on,
        }).mappings()
        groups = [dict(**{k: v for k, v in row.items() if k != 'slot'}, id=None,
                       label=f'Период {row["slot"]}', window=query.windows[row['slot'] - 1]) for row in records]
        eligible = 2
    elif query.group_by == 'task':
        predicate = MATERIAL_FILTER if query.metric=='missing_materials' else 'WHERE w.is_overdue'
        by_day = query.tie_breaker == 'uuid'
        rank_order = 'deadline_on NULLS LAST, work_order_id' if by_day else 'deadline_on NULLS LAST, deadline_at NULLS LAST, work_order_id'
        records = views.session.execute(text(LEDGER + TASK_SELECTION.format(predicate=predicate,
                                        tie_columns='deadline_on' if by_day else 'deadline_on,deadline_at',rank_order=rank_order)),
                                        {**params, **scope}).mappings().all()
        eligible = records[0]['eligible_groups'] if records else 0
        extra['tied_groups'] = records[0]['tied_groups'] if records else 0
        groups = [{k: v for k,v in row.items() if k not in ('position','eligible_groups','tied_groups')} for row in records]
    elif query.metric == 'without_service':
        records = views.session.execute(text(service_gap_sql()), {**params, **scope}).mappings().all()
        eligible = records[0]['eligible_groups']
        extra['unresolved_groups'] = records[0]['unresolved_groups']
        groups = [dict(id=row['id'], label=row['label'], code=row['code'], state=row['state'],
                       unfinished=0, overdue=0, undated=0) for row in records if row['id']]
    else:
        if query.group_by == 'equipment':
            columns = dict(identity='e.equipment_id', label='e.name', code='e.asset_code', state='e.status',
                           joins=EQUIPMENT_LINK)
        else:
            columns = dict(identity='u.user_id', label='u.full_name', code='NULL::text', state='NULL::text',
                           joins=ASSIGNEE_LINK)
        rank_tie = 'id' if query.tie_breaker == 'uuid' else 'oldest_due NULLS LAST, code NULLS LAST, id'
        sql = GROUPING.format(**columns, metric={'unfinished':'unfinished', 'overdue':'overdue'}[query.metric], rank_tie=rank_tie)
        records = views.session.execute(text(LEDGER + sql), {
            **params, **scope, 'details': query.include_overdue_tasks, 'details_limit': OVERDUE_DETAILS_LIMIT,
            'assignments': query.include_assignments,
        }).mappings().all()
        eligible = records[0]['eligible_groups'] if records else 0
        groups = [{k: v for k, v in row.items() if k not in ('eligible_groups', 'position')} for row in records if row['id']]
    return AggregateResult(site_id=principal.site_id, timezone=principal.timezone, as_of=as_of,
                           cutoff=cutoff.isoformat(), historical_cutoff=historical, query=query,
                           eligible_groups=eligible, groups=groups, complete=True, **extra)
