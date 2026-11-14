"""Bounded search over the whole authorized dataset, not just a model's first page."""
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
from fastapi import Depends,Query,HTTPException
from sqlalchemy import select,func,or_,and_
from app.security.sessions import has_role,SQL_ROLES
from .management import equipment_response

BASE='/api/v1/assistant/workspace'

def register_routes(app,views):
    @app.get(BASE+'/equipment')
    def equipment(q:str=Query('',max_length=200),offset:int=Query(0,ge=0),v=Depends(views)):
        cls=v.models['equipment'];filters=[cls.site_id==v.principal.site_id]
        if v.principal.role=='executor':filters.append(cls.equipment_id.in_(v.visible_equipment_ids()))
        if q.strip():filters.append(or_(cls.name.ilike('%'+q.strip()+'%'),cls.asset_code.ilike('%'+q.strip()+'%'),cls.location.ilike('%'+q.strip()+'%')))
        count=v.session.scalar(select(func.count()).select_from(cls).where(*filters))
        rows=v.session.scalars(select(cls).where(*filters).order_by(cls.asset_code,cls.equipment_id).offset(offset).limit(25)).all()
        return dict(items=[equipment_response(r) for r in rows],total=count,offset=offset,limit=25)

    @app.get(BASE+'/staff')
    def staff(q:str=Query('',max_length=200),offset:int=Query(0,ge=0),v=Depends(views)):
        if not has_role(v.principal.role,('director','admin','dispatcher','engineer')):raise HTTPException(403,'Нет доступа к команде')
        members=v.models['site_memberships'];users=v.models['users']
        filters=[members.site_id==v.principal.site_id]
        if q.strip():filters.append(or_(users.full_name.ilike('%'+q.strip()+'%'),users.email.ilike('%'+q.strip()+'%')))
        source=select(members.user_id,users.full_name,users.email,members.role,and_(members.is_active,users.is_active).label('is_active'),members.revision,members.employed_from,members.employed_until).join(users,users.user_id==members.user_id).where(*filters)
        count=v.session.scalar(select(func.count()).select_from(source.subquery()))
        rows=v.session.execute(source.order_by(users.full_name,members.user_id).offset(offset).limit(25)).mappings().all()
        return dict(items=[dict(r,role=SQL_ROLES.get(r['role'],r['role'])) for r in rows],total=count,offset=offset,limit=25)

    @app.get(BASE+'/staff/{user_id}')
    def person(user_id:UUID,v=Depends(views)):
        if not has_role(v.principal.role,('director','admin','dispatcher','engineer')):raise HTTPException(403,'Нет доступа к сотруднику')
        member=v.one('site_memberships',user_id=user_id);user=v.one('users',user_id=user_id)
        return dict(user_id=user_id,full_name=user.full_name,email=user.email,role=SQL_ROLES.get(member.role,member.role),is_active=member.is_active and user.is_active,revision=member.revision,
            employed_from=member.employed_from,employed_until=member.employed_until,
            qualifications=[dict(skill_id=r.skill_id,verified_at=r.verified_at,valid_until=r.valid_until,revision=r.revision) for r in v.rows('user_skills',user_id=user_id)],
            shifts=[dict(shift_rule_id=r.shift_rule_id,label=r.label,pattern=r.calendar_pattern,valid_from=r.valid_from,valid_until=r.valid_until,starts_local=r.starts_local,ends_local=r.ends_local,status=r.status,is_active=r.is_active,revision=r.revision) for r in v.rows('employee_shift_rules',user_id=user_id)],
            availability=[dict(availability_id=r.availability_id,starts_at=r.starts_at,ends_at=r.ends_at,status=r.status,reason=r.reason,revision=r.revision) for r in v.rows('availability_slots',user_id=user_id)])

    @app.get(BASE+'/tasks')
    def tasks(period:Literal['upcoming','overdue','undated','all']='upcoming',state:str|None=None,active_only:bool=True,q:str=Query('',max_length=200),offset:int=Query(0,ge=0),v=Depends(views)):
        orders=v.models['work_orders'];assignments=v.models['work_assignments'];rules=v.models['maintenance_rules'];operations=v.models['operation_templates']
        instant=func.coalesce(orders.planned_start_at,orders.regulatory_deadline_at);now=datetime.now(timezone.utc)
        filters=[orders.site_id==v.principal.site_id]
        if state:filters.append(orders.status==state)
        elif active_only:filters.append(orders.status.in_(('draft','assigned','clarification','rework')))
        if v.principal.role=='executor':filters.append(select(assignments.work_order_id).where(assignments.work_order_id==orders.work_order_id,assignments.user_id==v.principal.user_id,assignments.status.not_in(('cancelled','declined'))).exists())
        if period=='upcoming':filters.append(instant>=now)
        elif period=='overdue':filters.append(instant<now)
        elif period=='undated':filters.append(instant.is_(None))
        source=select(orders).outerjoin(rules,and_(rules.maintenance_rule_id==orders.maintenance_rule_id,rules.site_id==v.principal.site_id)).outerjoin(operations,operations.operation_template_id==rules.operation_template_id)
        if q.strip():filters.append(or_(orders.operation_snapshot['label'].astext.ilike('%'+q.strip()+'%'),operations.title.ilike('%'+q.strip()+'%'),operations.code.ilike('%'+q.strip()+'%')))
        source=source.where(*filters)
        count=v.session.scalar(select(func.count()).select_from(source.subquery()))
        selected=v.session.scalars(source.order_by(instant.asc().nulls_last() if period!='overdue' else instant.desc(),orders.work_order_id).offset(offset).limit(25)).all()
        v.prepare_task_views(selected)
        return dict(items=[v.task_view(o) for o in selected],total=count,period=period,timezone=v.principal.timezone,checked_at=now,offset=offset,limit=25)
