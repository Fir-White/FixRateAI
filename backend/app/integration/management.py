from app.security.sessions import has_role
"""Authenticated catalog, equipment and staff administration on the shared schema.

Equipment CRUD and user/profile/role capabilities adapt new_backend c559d27.
The existing opaque session, site scope, CSRF and revision protocol remain shared.
"""
from contextlib import contextmanager
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from pydantic import ValidationError

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select, text, delete

from app.db.session import service_transaction
from app.schemas.maintenance import CalendarPattern
from app.schemas.management import (ApplicationDecision,AvailabilityInput,CrewInput,CrewEdit,
    EmploymentEdit,EquipmentCreate,EquipmentEdit,NamedReference,QualificationInput,
    Registration,ServiceConfiguration,ShiftInput,ShiftEdit,SkillInput,Revision,PatternPreview)
from app.security.sessions import SQL_ROLES,hash_password
from app.scheduling.recurrence import pattern_description,occurrence_dates,occurrence_pairs
from app.scheduling.shifts import expand_shift,employment_availability
from .assignments import _lock
from .calendar import _json_value, configured_pattern, checklist_for_rule

PREFIX='/api/v1/maintenance'


def _guard(v,*roles):
    if not has_role(v.principal.role,roles):
        raise HTTPException(403,'Действие недоступно для текущей роли')


@contextmanager
def _edit(v,workers=(),roles=('admin','dispatcher')):
    """Use the same global user → membership → metadata lock order as BE05."""
    _guard(v,*roles)
    with service_transaction(v.session):
        identifiers=set(workers)|{v.principal.user_id}
        for table in ('users','site_memberships'):
            for identity in sorted(identifiers,key=lambda x:x.int):
                _lock(v,table,user_id=identity,read=identity not in workers)
        v.session.expire_all()
        actor=v.one('users',user_id=v.principal.user_id)
        member=v.one('site_memberships',user_id=v.principal.user_id)
        if not actor.is_active or not member.is_active or not has_role(SQL_ROLES.get(member.role),roles):
            raise HTTPException(403,'Права пользователя изменились; обновите сессию')
        yield


def _revision(row,expected):
    if row.revision!=expected:
        raise HTTPException(409,'REVISION_CONFLICT: данные изменились; обновите форму')


def _audit(v,table,identity,action,after):
    v.repo.add('audit_events',site_id=v.principal.site_id,actor_type='user',actor_user_id=v.principal.user_id,
        entity_type=table,entity_id=identity,action=action,after_snapshot=json.loads(json.dumps(after,default=_json_value)))


def _equipment(v,identity,lock=False):
    rows=_lock(v,'equipment',equipment_id=identity) if lock else v.rows('equipment',equipment_id=identity)
    if not rows:
        raise HTTPException(404,'Оборудование не найдено')
    return rows[0]


def equipment_response(row):
    return {key:getattr(row,key) for key in ('equipment_id','site_id','system_id','parent_equipment_id',
        'equipment_type_id','asset_code','name','serial_number','commissioned_on','location','properties','status','revision')}


def save_equipment(v,data,identity=None):
    with _edit(v):
        # Serializes hierarchy changes and uniqueness checks for this site's catalog.
        v.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),{'key':f'catalog:{v.principal.site_id}'})
        row=_equipment(v,identity,True) if identity else None
        if row:
            _revision(row,data.expected_revision)
            current={key:getattr(row,key) for key in ('system_id','equipment_type_id','parent_equipment_id','asset_code','name','serial_number','commissioned_on','location','status')}
            current['data_origin']=row.properties.get('data_origin','customer')
            current['properties']=row.properties
            supplied=data.model_dump(exclude={'expected_revision'},exclude_unset=True)
            if supplied.get('properties',{}).get('data_origin') is not None:
                current['data_origin']=supplied['properties']['data_origin']
            if 'data_origin' in supplied and 'properties' not in supplied:
                current['properties']=dict(row.properties,data_origin=supplied['data_origin'])
            try:
                data=EquipmentCreate.model_validate({**current,**supplied})
            except ValidationError:
                raise HTTPException(422,'Проверьте сохранённые параметры оборудования') from None
        system=v.one('engineering_systems',system_id=data.system_id)
        if not system.is_active:
            raise HTTPException(422,'Система выведена из эксплуатации')
        if data.equipment_type_id is not None:
            v.one('equipment_types',equipment_type_id=data.equipment_type_id)
        parent_id=data.parent_equipment_id
        seen={identity} if identity else set()
        while parent_id:
            if parent_id in seen:
                raise HTTPException(422,'Циклическая иерархия оборудования')
            seen.add(parent_id)
            parent=_equipment(v,parent_id)
            if parent.system_id!=data.system_id:
                raise HTTPException(422,'Родительское оборудование должно относиться к той же системе')
            parent_id=parent.parent_equipment_id
        if row and data.system_id!=row.system_id and v.rows('rule_equipment',equipment_id=identity):
            raise HTTPException(409,'Оборудование с регламентами нельзя переносить в другую систему')
        if row and data.status!='active':
            _ensure_equipment_idle(v,identity)
        values=data.model_dump(exclude={'expected_revision','data_origin'})
        values['properties']=dict(data.properties,data_origin=data.data_origin)
        if row:
            if row.properties.get('data_origin')!=data.data_origin and v.rows('rule_equipment',equipment_id=identity):
                raise HTTPException(409,'Происхождение оборудования с регламентами изменить нельзя')
            for key,value in values.items(): setattr(row,key,value)
            row.revision+=1
        else:
            row=v.repo.add('equipment',site_id=v.principal.site_id,**values)
        v.session.flush()
        _audit(v,'equipment',row.equipment_id,'update' if identity else 'create',dict(revision=row.revision,status=row.status))
        return equipment_response(row)


def _ensure_equipment_idle(v,equipment_id):
    for link in v.rows('work_order_equipment',equipment_id=equipment_id):
        order=v.one('work_orders',work_order_id=link.work_order_id)
        if order.status not in ('completed','cancelled'):
            raise HTTPException(409,'У оборудования есть незавершённые задания; сначала завершите или отмените их')


def exposed_pattern(rule):
    raw=configured_pattern(rule)
    if raw is None:return None
    try:return CalendarPattern.model_validate_json(json.dumps(raw,default=str)).model_dump(mode="json")
    except ValidationError:return None


def service_configurations(v,equipment_id):
    _equipment(v,equipment_id)
    rows=[]
    for binding in v.rows('rule_equipment',equipment_id=equipment_id):
        rule=binding.rule
        parameters=rule.schedule_parameters
        if parameters.get('superseded_binding'):
            continue
        op=rule.operation
        metadata=parameters.get('operation_metadata',{})
        rows.append(dict(binding_id=binding.binding_id,operation_id=op.operation_template_id,
            revision=binding.revision,rule_version=rule.rule_version,code=metadata.get('code',op.code),
            title=metadata.get('title',op.title),instructions=metadata.get('instructions',op.description or op.title),
            maintenance_type=v.one('maintenance_types',maintenance_type_id=op.maintenance_type_id).name,
            pattern=exposed_pattern(rule),basis=parameters.get('calendar_basis',parameters.get('basis')) or 'fixed_calendar',valid_from=binding.valid_from,valid_until=binding.valid_to,
            crew_size=rule.required_people,norm_value=str(rule.norm_hours) if rule.norm_hours is not None else None,norm_unit=parameters.get('norm_unit','unconfirmed'),
            duration_minutes=parameters.get('planning_duration_minutes'),allowed_lead_days=parameters.get('allowed_lead_days',0),
            qualification_ids=[r.skill_id for r in v.rows('rule_required_skills',maintenance_rule_id=rule.maintenance_rule_id)],
            checklist=[dict(source_item_key=parameters.get('checklist_metadata',{}).get(str(r.checklist_template_id),{}).get('source_item_key'),source_refs=parameters.get('checklist_metadata',{}).get(str(r.checklist_template_id),{}).get('source_refs',[]),text=r.prompt,answer_kind={'checkbox':'boolean','number':'number','text':'text','photo':'boolean'}[r.input_kind],
                unit=r.unit_code,required=r.is_required,
                visual_verifiability=parameters.get('checklist_metadata',{}).get(str(r.checklist_template_id),{}).get('visual_verifiability','not_verifiable'),
                photo_required=parameters.get('checklist_metadata',{}).get(str(r.checklist_template_id),{}).get('photo_required',r.input_kind=='photo'))
                for r in checklist_for_rule(v,op.operation_template_id,parameters)],
            enabled=rule.publication_status=='published',source_text=rule.source_text,methodology_ref=parameters.get('methodology_ref'),measurement_requirements=parameters.get('measurement_requirements',[]),required_acts=parameters.get('required_acts',[])))
    return rows


def save_service(v,equipment_id,data,binding_id=None):
    if v.principal.role not in ("chief_engineer","admin"):
        raise HTTPException(403,"Регламент изменяет главный инженер")
    if data.enabled and v.principal.role!="chief_engineer":
        raise HTTPException(403,"Публикацию утверждает главный инженер")
    with _edit(v,roles=("chief_engineer","admin")):
        v.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),{'key':f'catalog:{v.principal.site_id}'})
        eq=_equipment(v,equipment_id,True)
        if data.enabled and data.pattern.frequency=="yearly_count" and data.pattern.annual_policy=="from_anchor" and (not eq.commissioned_on or data.pattern.anchor_date!=eq.commissioned_on):
            raise HTTPException(422,"Для отсчёта от ввода нужна подтверждённая дата ввода, совпадающая с опорной датой")
        old=None
        if binding_id:
            old=v.one('rule_equipment',binding_id=binding_id,equipment_id=equipment_id)
            _lock(v,'rule_equipment',binding_id=binding_id)
            if data.expected_revision is None:
                raise HTTPException(422,'Для изменения нужна ревизия настройки')
            _revision(old,data.expected_revision)
            # Version changes never silently invalidate already generated work.
            for entry in v.rows('schedule_entries',binding_id=binding_id):
                if entry.regulatory_deadline_on>=data.valid_from and any(o.status!='cancelled' for o in v.rows('work_orders',schedule_entry_id=entry.schedule_entry_id)):
                    raise HTTPException(409,'С этой даты уже есть задания. Выберите более позднюю дату или отмените будущие задания')
            op=old.rule.operation
            if data.operation_id is not None and data.operation_id!=op.operation_template_id:
                raise HTTPException(422,'Нельзя подменить операцию существующей настройки')
            if data.code!=op.code:
                raise HTTPException(422,'Код операции постоянен. Для другого кода создайте отдельное обслуживание')
            _lock(v,'operation_templates',operation_template_id=op.operation_template_id)
            version=max(r.rule_version for r in v.rows('maintenance_rules',operation_template_id=op.operation_template_id))+1
        else:
            typ=next((t for t in v.rows('maintenance_types') if t.name==data.maintenance_type),None)
            if not typ: raise HTTPException(422,'Не задан вид обслуживания')
            if data.operation_id:
                op=v.one('operation_templates',operation_template_id=data.operation_id)
                _lock(v,'operation_templates',operation_template_id=data.operation_id)
                if op.system_id!=eq.system_id or not op.is_active or data.code!=op.code:
                    raise HTTPException(422,'Выберите активную операцию той же инженерной системы и сохраните её код')
                version=max((r.rule_version for r in v.rows('maintenance_rules',operation_template_id=op.operation_template_id)),default=0)+1
            else:
                op=v.repo.add('operation_templates',site_id=eq.site_id,system_id=eq.system_id,code=data.code,
                    title=data.title,description=data.instructions,maintenance_type_id=typ.maintenance_type_id)
                version=1
        if old and 'checklist_ids' not in old.rule.schedule_parameters:
            checks={}
            for check in v.rows('checklist_templates',operation_template_id=op.operation_template_id):
                if check.item_code not in checks or checks[check.item_code].template_version<check.template_version:
                    checks[check.item_code]=check
            old.rule.schedule_parameters=dict(old.rule.schedule_parameters,checklist_ids=[str(c.checklist_template_id) for c in checks.values()])
        if v.one('maintenance_types',maintenance_type_id=op.maintenance_type_id).name!=data.maintenance_type:
            raise HTTPException(422,'Для изменения вида ТО создайте отдельную операцию')
        for skill in data.qualification_ids: v.one('skills',skill_id=skill)
        document=v.repo.add('regulation_documents',site_id=eq.site_id,title=data.title,
            source_kind='demo' if eq.properties.get('data_origin')=='synthetic_demo' else 'internal')
        edition=v.repo.add('regulation_editions',site_id=eq.site_id,regulation_document_id=document.regulation_document_id,
            edition_code=f'v{version}',effective_from=data.valid_from,effective_to=data.valid_until,is_approved=data.enabled,approved_by=v.principal.user_id if data.enabled else None)
        checks=[];check_metadata={}
        for index,item in enumerate(data.checklist,1):
            check=v.repo.add('checklist_templates',site_id=eq.site_id,operation_template_id=op.operation_template_id,
                item_code=f'web-{index}',template_version=version,prompt=item.text,input_kind={'boolean':'checkbox','number':'number','text':'text'}[item.answer_kind],
                unit_code=item.unit,is_required=item.required,position=index)
            checks.append(str(check.checklist_template_id))
            check_metadata[str(check.checklist_template_id)]=dict(visual_verifiability=item.visual_verifiability,photo_required=item.photo_required,source_item_key=item.source_item_key,source_refs=item.source_refs)
        parameters=dict(methodology_ref=data.methodology_ref,measurement_requirements=[json.loads(r.model_dump_json()) for r in data.measurement_requirements],required_acts=data.required_acts,calendar_pattern=json.loads(data.pattern.model_dump_json()),norm_unit=data.norm_unit,
            calendar_basis=data.basis,
            planning_duration_minutes=data.duration_minutes,duration_basis='configured:explicit-duration',
            allowed_lead_days=data.allowed_lead_days,checklist_ids=checks,checklist_metadata=check_metadata,
            operation_metadata=dict(code=data.code,title=data.title,instructions=data.instructions))
        frequency=data.pattern.frequency
        rule=v.repo.add('maintenance_rules',site_id=eq.site_id,system_id=eq.system_id,operation_template_id=op.operation_template_id,
            regulation_edition_id=edition.regulation_edition_id,supersedes_rule_id=old.maintenance_rule_id if old else None,rule_version=version,
            period_unit=frequency if frequency in ('day','month','quarter','year') else 'year' if frequency in ('dates','yearly_count') else 'day',
            period_count=data.pattern.interval,occurrences_per_period=data.pattern.count_per_year or 1,scheduling_mode='calendar_window',
            source_text=pattern_description(data.pattern),source_ref=f'configured:{document.regulation_document_id}',schedule_parameters=parameters,
            required_people=data.crew_size,norm_hours=data.norm_value,norm_hours_basis='total_person_hours' if data.norm_unit=='person_hour' else 'per_person',
            active_from=data.valid_from,active_until=data.valid_until,publication_status='published' if data.enabled else 'draft',
            data_origin=eq.properties.get('data_origin','customer'))
        for skill in data.qualification_ids:
            v.repo.add('rule_required_skills',site_id=eq.site_id,maintenance_rule_id=rule.maintenance_rule_id,
                skill_id=skill,minimum_holders=data.crew_size)
        new=v.repo.add('rule_equipment',site_id=eq.site_id,system_id=eq.system_id,maintenance_rule_id=rule.maintenance_rule_id,
            equipment_id=eq.equipment_id,valid_from=data.valid_from,valid_to=data.valid_until)
        if old:
            if data.valid_from<=old.valid_from:
                old.rule.publication_status='archived'
            else:
                old.valid_to=data.valid_from-timedelta(days=1)
            old.revision+=1
            old.rule.schedule_parameters=dict(old.rule.schedule_parameters,superseded_binding=str(new.binding_id))
        eq.revision+=1
        v.session.flush()
        _audit(v,'rule_equipment',new.binding_id,'configure',dict(equipment_id=equipment_id,version=version,previous_binding_id=binding_id))
        return next(r for r in service_configurations(v,equipment_id) if r['binding_id']==new.binding_id)


def register_routes(app,views,db):
    @app.post(PREFIX+'/management/calendar-pattern/preview')
    def pattern_preview(command:PatternPreview,v=Depends(views)):
        _guard(v,'executive','admin','dispatcher','engineer')
        try:
            pairs=occurrence_pairs(command.pattern,date(command.year,command.month,1),date(command.year,command.month,monthrange(command.year,command.month)[1]))
            days=[day for _,day in pairs]
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
        return dict(dates=days,occurrences=[dict(source_date=source,date=day) for source,day in pairs],explanation=pattern_description(command.pattern),timezone=v.principal.timezone)

    @app.get(PREFIX+'/management/catalog')
    def catalog(v=Depends(views)):
        _guard(v,'executive','admin','dispatcher','engineer')
        return dict(systems=[dict(id=r.system_id,code=r.code,name=r.name) for r in v.rows('engineering_systems') if r.is_active],
            equipment_types=[dict(id=r.equipment_type_id,code=r.code,name=r.name) for r in v.rows('equipment_types')],
            operations=[dict(id=r.operation_template_id,system_id=r.system_id,code=r.code,title=r.title,instructions=r.description or r.title,
                maintenance_type=v.one('maintenance_types',maintenance_type_id=r.maintenance_type_id).name) for r in v.rows('operation_templates') if r.is_active],
            skills=[dict(id=r.skill_id,code=r.code,name=r.name,validity_required=r.validity_required) for r in v.rows('skills')])

    @app.post(PREFIX+'/management/systems',status_code=201)
    def system_create(command:NamedReference,v=Depends(views)):
        with _edit(v):
            row=v.repo.add('engineering_systems',site_id=v.principal.site_id,**command.model_dump())
            return dict(id=row.system_id,name=row.name,code=row.code)

    @app.post(PREFIX+'/management/equipment-types',status_code=201)
    def type_create(command:NamedReference,v=Depends(views)):
        with _edit(v,roles=('admin',)):
            row=v.repo.add('equipment_types',**command.model_dump())
            return dict(id=row.equipment_type_id,name=row.name,code=row.code)

    @app.get(PREFIX+'/equipment')
    def equipment_list(limit:int=100,offset:int=0,status:str|None=None,v=Depends(views)):
        if not 1<=limit<=100 or offset<0: raise HTTPException(422,'Некорректная пагинация')
        visible=v.visible_equipment_ids() if v.principal.role=='executor' else None
        rows=[r for r in v.rows('equipment') if (visible is None or r.equipment_id in visible) and (status is None or r.status==status)]
        rows.sort(key=lambda r:(r.asset_code,r.equipment_id.int))
        return dict(items=[equipment_response(r) for r in rows[offset:offset+limit]],total=len(rows),limit=limit,offset=offset)

    @app.get(PREFIX+'/equipment/{equipment_id}')
    def equipment_get(equipment_id:UUID,v=Depends(views)):
        if v.principal.role=='executor' and equipment_id not in v.visible_equipment_ids(): raise HTTPException(404,'Оборудование не найдено')
        return equipment_response(_equipment(v,equipment_id))

    @app.post(PREFIX+'/equipment',status_code=201)
    def equipment_create(command:EquipmentCreate,v=Depends(views)):
        return save_equipment(v,command)

    @app.patch(PREFIX+'/equipment/{equipment_id}')
    def equipment_update(equipment_id:UUID,command:EquipmentEdit,v=Depends(views)):
        return save_equipment(v,command,equipment_id)

    @app.delete(PREFIX+'/equipment/{equipment_id}',status_code=204)
    def equipment_retire(equipment_id:UUID,expected_revision:int,v=Depends(views)):
        with _edit(v):
            row=_equipment(v,equipment_id,True)
            _revision(row,expected_revision)
            _ensure_equipment_idle(v,equipment_id)
            row.status='retired';row.revision+=1
            _audit(v,'equipment',equipment_id,'retire',dict(revision=row.revision))

    @app.get(PREFIX+'/equipment/{equipment_id}/service-configurations')
    def configs(equipment_id:UUID,v=Depends(views)):
        _guard(v,'executive','admin','dispatcher','engineer','executor')
        if v.principal.role=='executor' and equipment_id not in v.visible_equipment_ids():raise HTTPException(404,'Оборудование не найдено')
        return service_configurations(v,equipment_id)

    @app.post(PREFIX+'/equipment/{equipment_id}/service-configurations',status_code=201)
    def config_create(equipment_id:UUID,command:ServiceConfiguration,v=Depends(views)):
        return save_service(v,equipment_id,command)

    @app.put(PREFIX+'/equipment/{equipment_id}/service-configurations/{binding_id}')
    def config_update(equipment_id:UUID,binding_id:UUID,command:ServiceConfiguration,v=Depends(views)):
        return save_service(v,equipment_id,command,binding_id)

    register_workforce_routes(app,views,db)


def worker_intervals(v,member,start,end):
    tz=v.principal.timezone
    intervals=[dict(start_at=r.starts_at,end_at=r.ends_at,status=r.status) for r in v.rows('availability_slots',user_id=member.user_id) if r.is_active]
    diagnostics=[]
    for rule in v.rows('employee_shift_rules',user_id=member.user_id):
        rows,issues=expand_shift(rule,start,end,tz)
        intervals.extend(rows);diagnostics.extend(issues)
    return employment_availability(intervals,member.employed_from,member.employed_until,tz),diagnostics


def _validate_bookings(v,user_ids):
    """Editing availability/role cannot silently invalidate an existing reservation."""
    from app.assignment.selection import _merge,_subtract
    now=datetime.now(timezone.utc)
    for user_id in user_ids:
        member=v.one('site_memberships',user_id=user_id)
        for row in v.rows('work_assignments',user_id=user_id):
            order=v.one('work_orders',work_order_id=row.work_order_id)
            if row.status in ('cancelled','declined','finished') or order.status in ('completed','cancelled'):
                continue
            if not member.is_active or SQL_ROLES.get(member.role)!='executor':
                raise HTTPException(409,'У работника есть активные назначения; сначала измените их состав')
            if not row.start_at or not row.end_at:
                raise HTTPException(409,'У работника есть назначение без точного времени; сначала уточните его')
            if row.end_at<=now: continue
            tz=ZoneInfo(v.principal.timezone)
            intervals,_=worker_intervals(v,member,row.start_at.astimezone(tz).date(),row.end_at.astimezone(tz).date())
            available=_merge([(r['start_at'].astimezone(timezone.utc),r['end_at'].astimezone(timezone.utc)) for r in intervals if r['status']=='available'])
            free=_subtract(available,[(r['start_at'].astimezone(timezone.utc),r['end_at'].astimezone(timezone.utc)) for r in intervals if r['status']=='unavailable'])
            if not any(a<=row.start_at.astimezone(timezone.utc) and row.end_at.astimezone(timezone.utc)<=b for a,b in free):
                raise HTTPException(409,'Изменение пересекает подтверждённое назначение; сначала переназначьте работу')
            required=order.operation_snapshot.get('qualification_ids',[])
            facts={str(r.skill_id):r for r in v.rows('user_skills',user_id=user_id)}
            for identity in required:
                fact=facts.get(str(identity))
                skill=v.one('skills',skill_id=UUID(str(identity)))
                if not fact or not fact.verified_at or fact.verified_at>now or (skill.validity_required and not fact.valid_until) or (fact.valid_until and fact.valid_until<(row.end_at-timedelta(microseconds=1)).astimezone(tz).date()):
                    raise HTTPException(409,'Изменение допуска затрагивает подтверждённую работу; сначала переназначьте её')


def workforce_view(v):
    _guard(v,'executive','admin','dispatcher','engineer')
    staff=[]
    for member in v.rows('site_memberships'):
        user=v.one('users',user_id=member.user_id)
        staff.append(dict(user_id=user.user_id,full_name=user.full_name,email=user.email,
            role=SQL_ROLES.get(member.role,member.role),is_active=member.is_active and user.is_active,revision=member.revision,
            employed_from=member.employed_from,employed_until=member.employed_until,
            qualifications=[dict(skill_id=r.skill_id,verified_at=r.verified_at,valid_until=r.valid_until,revision=r.revision) for r in v.rows('user_skills',user_id=user.user_id)],
            shifts=[dict(shift_rule_id=r.shift_rule_id,label=r.label,pattern=r.calendar_pattern,valid_from=r.valid_from,
                valid_until=r.valid_until,starts_local=r.starts_local,ends_local=r.ends_local,status=r.status,is_active=r.is_active,revision=r.revision)
                for r in v.rows('employee_shift_rules',user_id=user.user_id)],
            exceptions=[dict(id=r.availability_id,start_at=r.starts_at,end_at=r.ends_at,status=r.status,reason=r.reason,revision=r.revision)
                for r in v.rows('availability_slots',user_id=user.user_id) if r.is_active]))
    applications=[]
    if v.principal.role=='admin':
        for row in v.rows('employment_applications',status='pending'):
            user=v.one('users',user_id=row.user_id)
            applications.append(dict(application_id=row.application_id,user_id=row.user_id,full_name=user.full_name,email=user.email,revision=row.revision))
    return dict(staff=sorted(staff,key=lambda r:(r['full_name'],str(r['user_id']))),applications=applications,
        crews=[dict(id=r.crew_id,name=r.name,is_active=r.is_active,revision=r.revision,
            members=[dict(user_id=m.user_id,valid_from=m.valid_from,valid_to=m.valid_to) for m in v.rows('crew_members',crew_id=r.crew_id)]) for r in v.rows('crews')],
        skills=[dict(id=r.skill_id,code=r.code,name=r.name,validity_required=r.validity_required) for r in v.rows('skills')],timezone=v.principal.timezone)


def register_workforce_routes(app,views,db):
    @app.post('/api/v1/auth/register',status_code=201)
    def register(command:Registration,request:Request,session=Depends(db)):
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'Недопустимый origin')
        site=session.execute(text('SELECT j.site_id FROM site_join_codes j JOIN sites s USING(site_id) WHERE j.code=:code AND s.is_active'),{'code':command.company_code}).scalar()
        if site is None: raise HTTPException(422,'Неверный код компании')
        identity=uuid4()
        with service_transaction(session):
            session.execute(text('INSERT INTO users(user_id,full_name,email,password_hash) VALUES (:id,:name,:email,:password)'),
                dict(id=identity,name=command.full_name,email=command.email.lower(),password=hash_password(command.password)))
            session.execute(text('INSERT INTO employment_applications(site_id,user_id) VALUES (:site,:user)'),dict(site=site,user=identity))
        return dict(status='pending',message='Учётная запись создана. Администратор компании должен выдать роль и доступ к объекту.')

    @app.get(PREFIX+'/users/me')
    def me(v=Depends(views)):
        return v.principal.profile()

    @app.get(PREFIX+'/users')
    def users(v=Depends(views)):
        _guard(v,'admin')
        return workforce_view(v)['staff']

    @app.get(PREFIX+'/users/roles')
    def roles(v=Depends(views)):
        return [dict(role=role,label=label) for role,label in [('executive','Руководитель: просмотр и SLA'),('chief_engineer','Главный инженер: нормативы, планы и исключения'),('admin','Администратор: сотрудники, роли, справочники'),
            ('dispatcher','Диспетчер: обслуживание, смены, предложения и подтверждение назначений'),
            ('engineer','Инженер: прогнозы и приёмка'),('executor','Исполнитель: только назначенные работы')]]

    @app.get(PREFIX+'/users/{user_id}/roles')
    def user_roles(user_id:UUID,v=Depends(views)):
        if user_id!=v.principal.user_id: _guard(v,'admin')
        row=v.one('site_memberships',user_id=user_id)
        return [dict(site_id=row.site_id,user_id=user_id,role=SQL_ROLES.get(row.role),is_active=row.is_active)]

    @app.get(PREFIX+'/management/workforce')
    def workforce(v=Depends(views)):
        return workforce_view(v)

    @app.get(PREFIX+'/management/enrollment')
    def enrollment(v=Depends(views)):
        _guard(v,'admin')
        rows=v.rows('site_join_codes')
        return dict(code=rows[0].code if rows else None)

    @app.post(PREFIX+'/management/enrollment')
    def enrollment_create(v=Depends(views)):
        from sqlalchemy.dialects.postgresql import insert
        with _edit(v,roles=('admin',)):
            table=v.models['site_join_codes'].__table__
            v.session.execute(insert(table).values(site_id=v.principal.site_id).on_conflict_do_nothing())
            return dict(code=v.one('site_join_codes').code)

    @app.post(PREFIX+'/management/applications/{application_id}/decision')
    def application_decision(application_id:UUID,command:ApplicationDecision,v=Depends(views)):
        row=v.one('employment_applications',application_id=application_id)
        with _edit(v,{row.user_id},roles=('admin',)):
            row=_lock(v,'employment_applications',application_id=application_id)[0]
            _revision(row,command.expected_revision)
            if row.status!='pending': raise HTTPException(409,'Заявка уже рассмотрена')
            if command.decision=='accepted':
                if v.rows('site_memberships',user_id=row.user_id): raise HTTPException(409,'Сотрудник уже добавлен')
                v.repo.add('site_memberships',site_id=row.site_id,user_id=row.user_id,role=command.role,is_active=command.is_active,
                    employed_from=command.employed_from,employed_until=command.employed_until)
            row.status=command.decision;row.revision+=1;row.decided_at=datetime.now(timezone.utc);row.decided_by=v.principal.user_id
            _audit(v,'employment_applications',application_id,'decide',dict(status=row.status,role=command.role if command.decision=='accepted' else None))
            return dict(status=row.status)

    @app.put(PREFIX+'/management/staff/{user_id}')
    def staff_edit(user_id:UUID,command:EmploymentEdit,v=Depends(views)):
        with _edit(v,{user_id},roles=('admin',)):
            row=v.one('site_memberships',user_id=user_id)
            _revision(row,command.expected_revision)
            if SQL_ROLES.get(row.role)=='admin' and (command.role!='admin' or not command.is_active):
                others=[m for m in v.rows('site_memberships') if m.user_id!=user_id and m.is_active and SQL_ROLES.get(m.role)=='admin' and v.one('users',user_id=m.user_id).is_active]
                if not others: raise HTTPException(409,'Нельзя отозвать доступ последнего администратора объекта')
            for key,value in command.model_dump(exclude={'expected_revision'}).items(): setattr(row,key,value)
            row.revision+=1;v.session.flush();_validate_bookings(v,{user_id})
            _audit(v,'site_memberships',user_id,'update',dict(role=row.role,is_active=row.is_active,revision=row.revision))
            return dict(revision=row.revision)

    @app.post(PREFIX+'/management/staff/{user_id}/shifts',status_code=201)
    def shift_create(user_id:UUID,command:ShiftInput,v=Depends(views)):
        with _edit(v,{user_id}):
            member=v.one('site_memberships',user_id=user_id)
            if SQL_ROLES.get(member.role)!='executor': raise HTTPException(422,'Смены назначаются сотруднику с ролью исполнителя')
            values=command.model_dump(exclude={'pattern'});values['calendar_pattern']=json.loads(command.pattern.model_dump_json())
            row=v.repo.add('employee_shift_rules',site_id=v.principal.site_id,user_id=user_id,**values)
            _validate_bookings(v,{user_id})
            _audit(v,'employee_shift_rules',row.shift_rule_id,'create',dict(user_id=user_id,label=row.label))
            return dict(id=row.shift_rule_id,revision=row.revision)

    @app.put(PREFIX+'/management/staff/{user_id}/shifts/{shift_id}')
    def shift_update(user_id:UUID,shift_id:UUID,command:ShiftEdit,v=Depends(views)):
        with _edit(v,{user_id}):
            rows=_lock(v,'employee_shift_rules',user_id=user_id,shift_rule_id=shift_id)
            if not rows: raise HTTPException(404,'Смена не найдена')
            row=rows[0];_revision(row,command.expected_revision)
            for key,value in command.model_dump(exclude={'pattern','expected_revision'}).items(): setattr(row,key,value)
            row.calendar_pattern=json.loads(command.pattern.model_dump_json());row.revision+=1
            v.session.flush();_validate_bookings(v,{user_id})
            _audit(v,'employee_shift_rules',shift_id,'update',dict(revision=row.revision))
            return dict(revision=row.revision)

    @app.post(PREFIX+'/management/staff/{user_id}/availability',status_code=201)
    def availability(user_id:UUID,command:AvailabilityInput,v=Depends(views)):
        from .assignment import local_time
        tz=ZoneInfo(v.principal.timezone)
        start,end=local_time(command.start_local,tz),local_time(command.end_local,tz)
        if end<=start or end-start>timedelta(days=366): raise HTTPException(422,'Нужен положительный интервал до 366 дней')
        with _edit(v,{user_id}):
            v.one('site_memberships',user_id=user_id)
            row=v.repo.add('availability_slots',site_id=v.principal.site_id,user_id=user_id,starts_at=start,ends_at=end,status=command.status,reason=command.reason)
            _validate_bookings(v,{user_id})
            _audit(v,'availability_slots',row.availability_id,'create',dict(status=row.status,user_id=user_id))
            return dict(id=row.availability_id)

    @app.get(PREFIX+'/management/staff/{user_id}/calendar')
    def employee_calendar(user_id:UUID,start:date,end:date,v=Depends(views)):
        if user_id!=v.principal.user_id: _guard(v,'executive','admin','dispatcher','engineer')
        if end<start or end-start>timedelta(days=366) or start.year<2000 or end.year>2100: raise HTTPException(422,'Диапазон календаря до 366 дней, 2000–2100 годы')
        intervals,issues=worker_intervals(v,v.one('site_memberships',user_id=user_id),start,end)
        tz=ZoneInfo(v.principal.timezone)
        left=datetime.combine(start,time.min,tz);right=datetime.combine(end+timedelta(days=1),time.min,tz)
        return dict(intervals=[r for r in intervals if r['end_at']>left and r['start_at']<right],diagnostics=issues,timezone=str(tz))

    @app.post(PREFIX+'/management/staff/{user_id}/availability/{availability_id}/cancel')
    def cancel_availability(user_id:UUID,availability_id:UUID,expected_revision:int,v=Depends(views)):
        with _edit(v,{user_id}):
            rows=_lock(v,'availability_slots',user_id=user_id,availability_id=availability_id)
            if not rows: raise HTTPException(404,'Исключение не найдено')
            row=rows[0];_revision(row,expected_revision)
            row.is_active=False;row.revision+=1;v.session.flush();_validate_bookings(v,{user_id})
            _audit(v,'availability_slots',availability_id,'cancel',dict(revision=row.revision))
            return dict(revision=row.revision)

    @app.post(PREFIX+'/management/skills',status_code=201)
    def skill_create(command:SkillInput,v=Depends(views)):
        with _edit(v):
            row=v.repo.add('skills',**command.model_dump())
            return dict(id=row.skill_id,name=row.name)

    @app.put(PREFIX+'/management/staff/{user_id}/qualifications/{skill_id}')
    def qualification(user_id:UUID,skill_id:UUID,command:QualificationInput,v=Depends(views)):
        from .assignment import local_time
        verified=local_time(command.verified_local,ZoneInfo(v.principal.timezone)) if command.verified_local else command.verified_at
        if verified>datetime.now(timezone.utc): raise HTTPException(422,'Дата проверки допуска не может быть в будущем')
        with _edit(v,{user_id}):
            v.one('site_memberships',user_id=user_id)
            skill=v.one('skills',skill_id=skill_id)
            if skill.validity_required and not command.valid_until: raise HTTPException(422,'У допуска требуется срок действия')
            if command.valid_until and command.valid_until<verified.astimezone(ZoneInfo(v.principal.timezone)).date(): raise HTTPException(422,'Допуск истекает раньше проверки')
            rows=v.rows('user_skills',user_id=user_id,skill_id=skill_id)
            if rows:
                if command.expected_revision is None: raise HTTPException(409,'Для изменения допуска нужна его текущая ревизия')
                _revision(rows[0],command.expected_revision)
                rows[0].verified_at=verified;rows[0].valid_until=command.valid_until
                rows[0].revision+=1
            else:
                if command.expected_revision is not None: raise HTTPException(409,'Допуск изменился; перечитайте данные')
                v.repo.add('user_skills',site_id=v.principal.site_id,user_id=user_id,skill_id=skill_id,verified_at=verified,valid_until=command.valid_until)
            v.session.flush();_validate_bookings(v,{user_id})
            _audit(v,'user_skills',user_id,'update',dict(skill_id=skill_id))
            return dict(status='saved')

    @app.post(PREFIX+'/management/staff/{user_id}/qualifications/{skill_id}/revoke')
    def revoke_qualification(user_id:UUID,skill_id:UUID,command:Revision,v=Depends(views)):
        with _edit(v,{user_id}):
            row=v.one('user_skills',user_id=user_id,skill_id=skill_id)
            _revision(row,command.expected_revision)
            previous=dict(verified_at=row.verified_at,valid_until=row.valid_until,revision=row.revision)
            row.verified_at=None;row.valid_until=None;row.revision+=1
            v.session.flush();_validate_bookings(v,{user_id})
            _audit(v,'user_skills',user_id,'revoke',dict(skill_id=skill_id,revision=row.revision,previous=previous))
            return dict(revision=row.revision)

    def crew_save(v,command,crew_id=None):
        existing=v.one('crews',crew_id=crew_id) if crew_id else None
        ids={m.user_id for m in command.members}|{m.user_id for m in v.rows('crew_members',crew_id=crew_id)} if crew_id else {m.user_id for m in command.members}
        with _edit(v,ids):
            if existing:
                row=_lock(v,'crews',crew_id=crew_id)[0];_revision(row,command.expected_revision)
                for assignment in v.rows('work_assignments',crew_id=crew_id):
                    order=v.one('work_orders',work_order_id=assignment.work_order_id)
                    if assignment.status not in ('cancelled','declined','finished') and order.status not in ('completed','cancelled'):
                        member=next((m for m in command.members if m.user_id==assignment.user_id),None)
                        tz=ZoneInfo(v.principal.timezone)
                        if not command.is_active or not member or not assignment.start_at or not assignment.end_at or member.valid_from>assignment.start_at.astimezone(tz).date() or (member.valid_to and member.valid_to<(assignment.end_at-timedelta(microseconds=1)).astimezone(tz).date()):
                            raise HTTPException(409,'Изменение бригады затрагивает подтверждённые назначения')
                row.name=command.name;row.is_active=command.is_active;row.revision+=1
                cls=v.models['crew_members'];v.session.execute(delete(cls).where(cls.site_id==v.principal.site_id,cls.crew_id==crew_id))
            else: row=v.repo.add('crews',site_id=v.principal.site_id,name=command.name,is_active=command.is_active)
            for member in command.members:
                employee=v.one('site_memberships',user_id=member.user_id)
                if not employee.is_active or SQL_ROLES.get(employee.role)!='executor': raise HTTPException(422,'Участник бригады должен быть активным исполнителем')
                v.repo.add('crew_members',site_id=v.principal.site_id,crew_id=row.crew_id,**member.model_dump())
            _audit(v,'crews',row.crew_id,'update' if crew_id else 'create',dict(name=row.name,revision=row.revision,members=[m.model_dump() for m in command.members]))
            return dict(id=row.crew_id,revision=row.revision)

    @app.post(PREFIX+'/management/crews',status_code=201)
    def crew_create(command:CrewInput,v=Depends(views)):
        return crew_save(v,command)

    @app.put(PREFIX+'/management/crews/{crew_id}')
    def crew_update(crew_id:UUID,command:CrewEdit,v=Depends(views)):
        return crew_save(v,command,crew_id)
