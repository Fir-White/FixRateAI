"""Read-only task ledger analysis. One SQL snapshot; arithmetic never delegated to LLM."""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
import hashlib, json
from fastapi import HTTPException
from sqlalchemy import text

PENDING = ('draft', 'assigned', 'clarification', 'rework')
UNFINISHED = (*PENDING, 'in_progress', 'in_review')
MAX_ROWS = 20000


def server_time(zone):
    instant = datetime.now(timezone.utc)
    return dict(checked_at=instant.isoformat(), timezone=zone,
                local_date=instant.astimezone(ZoneInfo(zone)).date().isoformat())


def timing(row, instant, zone):
    """Deadline is exclusive. A missed planned start alone is not a breached deadline."""
    today = instant.astimezone(zone).date()
    deadline = row['regulatory_deadline_at']
    day = row['regulatory_deadline_on'] or ((deadline-timedelta(microseconds=1)).astimezone(zone).date() if deadline else None)
    if deadline and deadline <= instant or not deadline and day and day < today:
        due = 'overdue'
    elif day is None: due = 'undated'
    elif day < today: due = 'within_window'  # inconsistent day/cutoff: never silently discard
    elif day == today: due = 'today'
    else: due = 'future'
    start = row['planned_start_at']
    start_day = start.astimezone(zone).date() if start else None
    planned = 'unscheduled' if start_day is None else 'past' if start_day < today else 'today' if start_day == today else 'future'
    return due, planned, day, start_day


def effort(row):
    snapshot = row['operation_snapshot']
    # Use the frozen execution norm, never today's potentially changed regulation.
    unit = snapshot.get('norm_unit')
    if unit is None and row['norm_hours_basis_snapshot'] == 'total_person_hours': unit = 'person_hour'
    try:raw = Decimal(str(row['norm_hours_snapshot']));crew = int(row['required_people_snapshot'])
    except (InvalidOperation,TypeError,ValueError):return dict(status='invalid_norm',person_hours=None)
    if not raw.is_finite() or raw <= 0:return dict(status='missing_norm',person_hours=None)
    if unit not in ('person_hour','elapsed_hour'):return dict(status='unknown_unit',person_hours=None)
    if (unit,row['norm_hours_basis_snapshot']) in (('person_hour','per_person'),('elapsed_hour','total_person_hours')):
        return dict(status='basis_unit_conflict',person_hours=None)
    hours = raw if unit == 'person_hour' else raw * crew
    try:duration = Decimal(str(snapshot.get('planning_duration_minutes')))
    except (InvalidOperation,TypeError,ValueError):return dict(status='missing_duration',person_hours=str(hours))
    if not duration.is_finite() or duration <= 0:return dict(status='missing_duration',person_hours=str(hours))
    expected = duration / Decimal(60) * crew
    return dict(status='consistent' if abs(hours-expected)<=Decimal('.01') else 'mismatch',person_hours=str(hours),
                elapsed_minutes=str(duration),crew_size=crew,norm_value=str(raw),norm_unit=unit,duration_person_hours=str(expected))


def business_key(row, due_day, start_day):
    occurrence_day=row['source_date'] or due_day or start_day
    operation=str(row['operation_template_id']) if row['operation_template_id'] else (row['operation_snapshot'].get('code') or row['operation_code'] or '').strip().casefold()
    if not row['equipment'] or not occurrence_day or not operation:return None
    return (tuple(sorted(a['id'] for a in row['equipment'])),operation,occurrence_day.isoformat(),row['sequence_no'] or 1)


def analyze(v, section='summary', offset=0, origin='all', starts_on=None, ends_on=None, cohort='unfinished'):
    if starts_on and ends_on and ends_on < starts_on:
        raise HTTPException(422, 'Конец периода раньше начала')
    clock = server_time(v.principal.timezone)
    instant = datetime.fromisoformat(clock['checked_at']); zone = ZoneInfo(clock['timezone'])
    # All joins are tenant-pinned, including links and assignments. A single SELECT
    # gives a coherent snapshot even if another user completes a task concurrently.
    rows = v.session.execute(text('''SELECT w.work_order_id,w.revision,w.status,w.origin,w.maintenance_rule_id,
        w.planned_start_at,w.regulatory_deadline_at,w.norm_hours_snapshot,w.norm_hours_basis_snapshot,w.required_people_snapshot,
        jsonb_build_object('code',w.operation_snapshot->'code','norm_unit',w.operation_snapshot->'norm_unit',
            'planning_duration_minutes',w.operation_snapshot->'planning_duration_minutes') AS operation_snapshot,
        e.regulatory_deadline_on,e.source_date,e.sequence_no,
        p.period_year,p.period_month,r.operation_template_id,r.period_unit,r.period_count,r.occurrences_per_period,
        jsonb_build_object('calendar_pattern',r.schedule_parameters->'calendar_pattern') AS schedule_parameters,r.active_from,r.active_until,r.rule_version,
        coalesce(op.code,w.operation_snapshot->>'code') AS operation_code,
        coalesce(w.operation_snapshot->>'title',w.operation_snapshot->>'label',op.title,'Работа') AS title,
        coalesce(assets.items,'[]'::jsonb) AS equipment
        FROM work_orders w
        LEFT JOIN schedule_entries e ON e.site_id=w.site_id AND e.schedule_entry_id=w.schedule_entry_id
        LEFT JOIN schedule_plans p ON p.site_id=e.site_id AND p.schedule_plan_id=e.schedule_plan_id
        LEFT JOIN maintenance_rules r ON r.site_id=w.site_id AND r.maintenance_rule_id=w.maintenance_rule_id
        LEFT JOIN operation_templates op ON op.site_id=w.site_id AND op.operation_template_id=r.operation_template_id
        LEFT JOIN LATERAL (SELECT jsonb_agg(jsonb_build_object('id',a.equipment_id,'asset_code',a.asset_code,'name',a.name)
            ORDER BY a.equipment_id) AS items FROM work_order_equipment l
            JOIN equipment a ON a.site_id=l.site_id AND a.equipment_id=l.equipment_id
            WHERE l.site_id=w.site_id AND l.work_order_id=w.work_order_id) assets ON true
        WHERE w.site_id=:site AND (:executor=false OR EXISTS(SELECT 1 FROM work_assignments a
            WHERE a.site_id=w.site_id AND a.work_order_id=w.work_order_id AND a.user_id=:user AND a.status NOT IN ('cancelled','declined')))
        ORDER BY w.work_order_id LIMIT :maximum'''),
        dict(site=v.principal.site_id,user=v.principal.user_id,executor=v.principal.role=='executor',maximum=MAX_ROWS+1)).mappings().all()
    if len(rows) > MAX_ROWS:
        raise HTTPException(413, 'Анализ не выполнен: превышен предел полного снимка заданий объекта. Частичный результат не выдан.')
    counts = Counter(r['status'] for r in rows)
    total = len(rows)
    selection=[]
    for row in rows:
        if row['status'] not in UNFINISHED: continue
        if cohort=='execution_pending' and row['status'] not in PENDING:continue
        if cohort=='in_review' and row['status']!='in_review':continue
        if origin != 'all' and row['origin'] != origin: continue
        due, planned, due_day, start_day = timing(row,instant,zone)
        ledger_day = start_day or due_day
        if starts_on and (ledger_day is None or ledger_day < starts_on): continue
        if ends_on and (ledger_day is None or ledger_day > ends_on): continue
        selection.append((row,due,planned,due_day,start_day,effort(row)))
    dates={}; equipment={}; duplicates=defaultdict(list); duplicate_labels={}; unchecked=0; norms=Counter(); due_counts=Counter(); planned_counts=Counter()
    known_hours=Decimal(0); unknown_hours=0; sample=[]; pending_due=Counter()
    for row,due,planned,due_day,start_day,norm in selection:
        due_counts[due]+=1;planned_counts[planned]+=1;norms[norm['status']]+=1
        if row['status'] in PENDING:pending_due[due]+=1
        if norm['person_hours'] is None:unknown_hours+=1
        else:known_hours+=Decimal(norm['person_hours'])
        day=(start_day or due_day); key=day.isoformat() if day else 'undated'
        daily=dates.setdefault(key,dict(date=key,tasks=0,known_person_hours=Decimal(0),unknown_effort_tasks=0,planned_tasks=0,deadline_only_tasks=0))
        daily['tasks']+=1;daily['planned_tasks' if start_day else 'deadline_only_tasks']+=1
        if norm['person_hours'] is None:daily['unknown_effort_tasks']+=1
        else:daily['known_person_hours']+=Decimal(norm['person_hours'])
        assets=row['equipment']
        # Independent obligations shifted from a weekend may share a Monday.
        # Preserve source date and sequence before flagging a business duplicate.
        occurrence_day=row['source_date'] or due_day or start_day
        operation=str(row['operation_template_id']) if row['operation_template_id'] else (row['operation_snapshot'].get('code') or row['operation_code'] or '').strip().casefold()
        duplicate_key=business_key(row,due_day,start_day)
        if duplicate_key:
            duplicates[duplicate_key].append(str(row['work_order_id']))
            duplicate_labels[duplicate_key]=row['title']
        else:unchecked+=1
        for asset in assets or [dict(id='unlinked',asset_code='Не привязано',name='Оборудование не указано')]:
            item=equipment.setdefault(asset['id'],dict(**asset,tasks=0,execution_pending=0,in_review=0,known_person_hours=Decimal(0),unknown_effort_tasks=0,operations={}))
            item['tasks']+=1;item['execution_pending']+=int(row['status'] in PENDING);item['in_review']+=int(row['status']=='in_review')
            if norm['person_hours'] is None:item['unknown_effort_tasks']+=1
            else:item['known_person_hours']+=Decimal(norm['person_hours'])
            rule_key=str(row['maintenance_rule_id'] or operation or row['work_order_id'])
            op=item['operations'].setdefault(rule_key,dict(rule_id=str(row['maintenance_rule_id']) if row['maintenance_rule_id'] else None,
                title=row['title'],code=row['operation_code'],tasks=0,execution_pending=0,in_review=0,
                period_unit=row['period_unit'],period_count=row['period_count'],occurrences_per_period=row['occurrences_per_period'],
                calendar_pattern=(row['schedule_parameters'] or {}).get('calendar_pattern'),
                first_source_date=None,last_source_date=None,plan_periods=set(),norm_checks=Counter()))
            op['tasks']+=1;op['execution_pending']+=int(row['status'] in PENDING);op['in_review']+=int(row['status']=='in_review')
            op['norm_checks'][norm['status']]+=1
            if occurrence_day:
                d=occurrence_day.isoformat()
                op['first_source_date']=min(op['first_source_date'] or d,d);op['last_source_date']=max(op['last_source_date'] or d,d)
            if row['period_year']:op['plan_periods'].add(f"{row['period_year']:04d}-{row['period_month']:02d}")
        if len(sample)<25:sample.append(dict(id=str(row['work_order_id']),title=row['title'],state=row['status'],due=due,
            due_on=due_day.isoformat() if due_day else None,scheduled_on=start_day.isoformat() if start_day else None,effort=norm))
    groups=[dict(equipment_ids=list(k[0]),operation=k[1],operation_title=duplicate_labels[k],source_or_due_date=k[2],sequence=k[3],task_ids=ids[:25],count=len(ids),task_ids_truncated=len(ids)>25) for k,ids in sorted(duplicates.items()) if len(ids)>1]
    scope=dict(site_id=str(v.principal.site_id),site_name=v.principal.site_name,role=v.principal.role,
        visibility='assigned_to_user' if v.principal.role=='executor' else 'whole_site',origin=origin,
        starts_on=starts_on,ends_on=ends_on,cohort=cohort,date_filter_basis='planned_start_else_normative_due_day')
    common=dict(**clock,scope=scope,complete=True,scanned_tasks=total,selected_tasks=len(selection),
        snapshot_id=hashlib.sha256(json.dumps([dict(r) for r in rows]+[scope,clock['local_date'],dict(due_counts)],sort_keys=True,default=str).encode()).hexdigest(),
        counters=dict(all_tasks=total,by_status=dict(sorted(counts.items())),
            by_origin=dict(Counter(r['origin'] for r in rows)),
            execution_pending=sum(counts[s] for s in PENDING),unfinished=sum(counts[s] for s in UNFINISHED),
            scheduled_unfinished=sum(r['origin']=='scheduled' and r['status'] in UNFINISHED for r in rows),
            completed=counts['completed'],cancelled=counts['cancelled']),
        due=dict(due_counts),execution_pending_due=dict(pending_due),scheduled=dict(planned_counts),norm_checks=dict(norms),known_person_hours=str(known_hours),unknown_effort_tasks=unknown_hours,
        business_duplicates=dict(candidate_groups=len(groups),candidate_tasks=sum(g['count'] for g in groups),unchecked_tasks=unchecked,
            key='equipment set + operation identity (code fallback) + source date (else normative due date) + sequence; candidates require review'),
        limitations=['Счётчик оборудования считает связи: одно задание может относиться к нескольким единицам.',
            'Нагрузка по нормативному дню без времени начала не является назначенной сменой.',
            'Совпадение нормы и длительности проверяет арифметику, а не достоверность методики.',
            'Периоды и частота описывают сохранённые задания, но не доказывают полноту генерации календаря.'])
    if section=='summary':return dict(**common,sample=sample,sample_total=len(selection),sample_truncated=len(selection)>len(sample))
    if section=='dates':items=[dates[k] for k in sorted(dates)]
    elif section=='equipment':
        items=[]
        for k in sorted(equipment,key=lambda k:(equipment[k]['asset_code'],k)):
            item=equipment[k];ops=list(item['operations'].values())
            for op in ops:op['plan_periods']=sorted(op['plan_periods'])
            item['operations']=ops[:25];item['operations_total']=len(ops);item['operations_truncated']=len(ops)>25;items.append(item)
    else:items=groups
    return dict(**common,items=items[offset:offset+25],total=len(items),offset=offset,limit=25)
