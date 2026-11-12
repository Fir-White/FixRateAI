"""Restart-safe daily tick. Approved versions only, advisory lock, no paid AI loop."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
import asyncio
import logging
from sqlalchemy import select,text
from app.security.sessions import Principal
from .projections import Views
from .analyst import notify_event,audit
log=logging.getLogger(__name__)

def skipped_ai(snapshot):
    from app.schemas.maintenance import ForecastResult
    return ForecastResult(schema_version=snapshot.schema_version,data_origin=snapshot.data_origin,result_id=uuid4(),run_id=uuid4(),
        snapshot_id=snapshot.snapshot_id,snapshot_sha256=snapshot.content_sha256,equipment_id=snapshot.equipment.equipment_id,
        binding_id=snapshot.binding_id,as_of=snapshot.as_of,method='ai',method_version='automatic-rule-only-v1',model_ref=None,
        status='unavailable',recommended_date=None,mandatory_due_date=snapshot.mandatory_due_date,runtime_due_at_hours=None,
        overdue=False,uncertainty=dict(kind='unknown',lower_date=None,upper_date=None,calibrated=False,note='AI не вызывается фоновым календарём'),
        explanation='Автоматический календарь выполняет утверждённый регламент. AI запускается отдельным пользовательским запросом.',
        warnings=['AI_NOT_REQUESTED_AUTOMATIC_RUN'],error_code='AI_NOT_REQUESTED_AUTOMATIC_RUN',elapsed_ms=0)

def tick(app):
    from .planning import generate_tasks,source_token,catalog_token
    with app.state.factory() as session:
        sites=app.state.models['sites'];members=app.state.models['site_memberships'];users=app.state.models['users']
        for site in session.scalars(select(sites).where(sites.is_active)).all():
            now=datetime.now(timezone.utc);day=now.astimezone(ZoneInfo(site.timezone)).date()
            actor=session.execute(select(users,members).join(members,members.user_id==users.user_id).where(
                members.site_id==site.site_id,members.is_active,users.is_active).order_by((members.role=='chief_engineer').desc(),users.user_id)).first()
            if not actor:continue
            user,member=actor
            v=Views(session,app.state.models,Principal(user.user_id,site.site_id,member.role,user.full_name,user.email,site.name,site.timezone))
            # A transaction lock serializes downtime catch-up/overdue events across app instances.
            session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'overdue:{site.site_id}'})
            for order in v.rows('work_orders'):
                if order.status not in ('completed','cancelled') and order.regulatory_deadline_at and order.regulatory_deadline_at<now and order.overdue_since_at is None:
                    order.overdue_since_at=order.regulatory_deadline_at
                    audit(v,order,'overdue',dict(overdue_since=order.overdue_since_at),actor_type='system')
                    notify_event(v,order,'overdue',('director','engineer','chief_engineer','dispatcher','technician','executor'))
            session.commit()
            for report in v.rows('work_reports',status='submitted'):
                order=v.one('work_orders',work_order_id=report.work_order_id)
                if order.status!='in_review' or not report.execution_context.get('photo_analysis_requested_at') or not report.submitted_at or now-report.submitted_at<timedelta(seconds=60):continue
                if v.rows('ai_quality_checks',work_report_id=report.work_report_id):continue
                cls=v.models['work_orders']
                available=session.scalar(select(cls).where(cls.work_order_id==order.work_order_id).with_for_update(skip_locked=True))
                if available is None:continue
                author=v.one('users',user_id=report.submitted_by)
                who=Principal(author.user_id,site.site_id,'executor',author.full_name,author.email,site.name,site.timezone)
                revision=order.revision;task_id=order.work_order_id;session.commit()
                app.state.automatic_photo_review(task_id,revision,who)
            if member.role!='chief_engineer':continue
            plans=[p for p in v.rows('schedule_plans',period_year=day.year,period_month=day.month) if p.status=='approved']
            if not plans:continue
            approved=max(plans,key=lambda p:p.revision)
            allowed=approved.source_snapshot.get('approved_rule_versions')
            current=sorted(str(b.maintenance_rule_id) for b in v.rows('rule_equipment') if b.rule.publication_status=='published' and not b.rule.schedule_parameters.get('superseded_binding'))
            if allowed!=current or approved.source_snapshot.get('approved_catalog_token')!=catalog_token(v) or approved.source_snapshot.get('last_generation_day')==str(day):continue
            # One durable idempotency key for each local day and approved plan.
            from uuid import uuid5,NAMESPACE_URL
            key=uuid5(NAMESPACE_URL,f'fixrate:{site.site_id}:{approved.schedule_plan_id}:{day}')
            try:
                generate_tasks(v,day.year,day.month,key,source_token(v,day.year,day.month,now),None,forecast_provider=skipped_ai,approved_plan=approved)
                approved.source_snapshot=dict(approved.source_snapshot,last_generation_day=str(day));session.commit()
            except Exception as exc:
                session.rollback();log.error('scheduler_tick_failed site=%s type=%s',site.site_id,type(exc).__name__)

async def run(app):
    while True:
        try:await asyncio.to_thread(tick,app)
        except asyncio.CancelledError:raise
        except Exception as exc:log.error('scheduler_failed type=%s',type(exc).__name__)
        await asyncio.sleep(30)
