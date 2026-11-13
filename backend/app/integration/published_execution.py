"""Recheck the actual start of an approved finite catalog task."""
from datetime import datetime,timedelta,timezone
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import text
from app.schemas.draft_plans import WorkOccurrence,WorkSegment,DraftPolicy
from app.scheduling.draft_validator import validate
from .assignments import _lock_context,_lock
from .draft_resources import resources


def ensure_start(v,order):
    if not order.operation_snapshot.get('catalog_publication_id'):return
    links=v.rows('work_order_equipment',work_order_id=order.work_order_id)
    workers={a.user_id for a in v.rows('work_assignments',work_order_id=order.work_order_id) if a.status not in ('declined','cancelled')}
    _lock_context(v,order,workers,None)
    v.session.expire_all()
    row=v.session.execute(text('''SELECT p.input_snapshot,t.occurrence_id,t.segment_ids FROM published_catalog_tasks t
        JOIN draft_publications d USING(site_id,publication_id)
        JOIN draft_publication_proposals p ON p.site_id=d.site_id AND p.proposal_id=d.proposal_id
        WHERE t.site_id=:site AND t.work_order_id=:id AND p.state='published' AND d.publication_id=:pub'''),
        dict(site=v.principal.site_id,id=order.work_order_id,pub=UUID(order.operation_snapshot['catalog_publication_id']))).mappings().first()
    if not row:raise HTTPException(409,'Источник опубликованного задания не подтверждён')
    rule=order.rule
    if rule is None or rule.publication_status!='published' or not rule.edition.is_approved or not rule.operation.is_active:
        raise HTTPException(409,'Регламент опубликованного задания больше не подтверждён')
    if not v.one('engineering_systems',system_id=order.system_id).is_active:
        raise HTTPException(409,'Инженерная система отключена')
    snapshot=row['input_snapshot'];original=next(WorkOccurrence.model_validate(o) for o in snapshot['occurrences'] if o['occurrence_id']==str(row['occurrence_id']))
    if snapshot['source']['timezone']!=v.principal.timezone:raise HTTPException(409,'Часовой пояс изменился после утверждения; требуется пересогласование')
    deps=order.operation_snapshot.get('depends_on_task_ids',[])
    if deps:
        done=set(v.session.scalars(text('''SELECT o.work_order_id FROM work_orders o WHERE o.site_id=:site AND o.work_order_id=ANY(CAST(:ids AS uuid[]))
            AND o.status='completed' AND EXISTS(SELECT 1 FROM acceptance_reviews a WHERE a.site_id=o.site_id AND a.work_order_id=o.work_order_id AND a.decision='accepted')'''),dict(site=v.principal.site_id,ids=deps)))
        if done!=set(map(UUID,deps)):raise HTTPException(409,'Сначала должны быть выполнены и приняты предшествующие задания')
    now=datetime.now(timezone.utc)
    if order.planned_start_at is None or now<order.planned_start_at:raise HTTPException(409,'Назначенное время начала ещё не наступило')
    ends=now+timedelta(minutes=order.operation_snapshot['planning_duration_minutes'])
    people,equipment,unknown=resources(v,now-timedelta(days=1),ends+timedelta(days=1),now,{l.equipment_id for l in links},exclude_order_ids=[order.work_order_id])
    # Check only this task's actual execution; the original root and its exact
    # segment volume remain immutable in the approved proposal.
    root=original.model_copy(update=dict(total_person_hours=order.norm_hours_snapshot,equipment_ids=[l.equipment_id for l in links],
        interpretation='ALLOWED_WINDOW',norm_scope='whole_binding',splittable=False,min_segment_minutes=None))
    segment=WorkSegment(segment_id=UUID(row['segment_ids'][0]),occurrence_id=root.occurrence_id,equipment_ids=root.equipment_ids,
        person_hours=order.norm_hours_snapshot,start_at=now,end_at=ends,worker_ids=list(workers))
    report=validate([root],[segment],people,DraftPolicy.model_validate(snapshot['policy']),root.earliest_date,
        root.latest_date, v.principal.timezone,now,equipment_bookings=equipment,equipment_unknown=unknown,allow_legacy_policy=True)
    assets=_lock(v,'equipment',read=True,equipment_id=set(root.equipment_ids))
    if report.status!='valid' or any(a.status!='active' or a.commissioned_on and a.commissioned_on>now.astimezone(ZoneInfo(v.principal.timezone)).date() for a in assets):
        raise HTTPException(409,'Начало больше не обеспечено текущими ресурсами или допустимым окном: '+('; '.join(i.message for i in report.issues[:3]) or 'оборудование недоступно'))
