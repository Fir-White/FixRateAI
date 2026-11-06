"""Explicit analyst workflows; no generated measurements or implicit approvals."""
from __future__ import annotations
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import json

from fastapi import Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator
from sqlalchemy import select, text, delete, update
from sqlalchemy.dialects.postgresql import insert
from app.security.sessions import Principal, has_role

PREFIX='/api/v1/maintenance'

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class ReadingInput(Strict):
    equipment_id: UUID
    parameter_code: str=Field(min_length=1,max_length=128)
    value: Decimal=Field(allow_inf_nan=False,max_digits=18,decimal_places=6)
    unit: str=Field(min_length=1,max_length=64)
    measured_at: AwareDatetime
    phase: Literal['before','after']

class ExecutionInput(Strict):
    started_at: AwareDatetime | None = None
    performed_at: AwareDatetime | None = None
    person_hours: Decimal | None = Field(default=None,gt=0,le=10000,allow_inf_nan=False)
    @model_validator(mode='after')
    def coherent(self):
        if (self.performed_at and self.started_at and self.performed_at<self.started_at) or (self.performed_at and self.performed_at>datetime.now(timezone.utc)) or (self.started_at and self.started_at>datetime.now(timezone.utc)):
            raise ValueError('execution timestamps must be ordered and not in the future')
        return self

class LateExecution(Strict):
    expected_revision: int=Field(gt=0)
    reason: str=Field(min_length=1,max_length=2000)
    until: AwareDatetime

class ForecastSelection(Strict):
    selected_date: date
    reason: str=Field(min_length=1,max_length=2000)

class Reason(Strict):
    expected_revision: int=Field(gt=0)
    reason: str=Field(min_length=1,max_length=2000)


def audit(v,order,action,details,actor_type="user"):
    v.repo.add('audit_events',site_id=v.principal.site_id,actor_type=actor_type,actor_user_id=v.principal.user_id if actor_type=='user' else None,
        entity_type='work_orders',entity_id=order.work_order_id,action=action,
        after_snapshot=json.loads(json.dumps(details,default=str)))


def notify_event(v,order,event,roles):
    if 'maintenance_notifications' not in v.models.classes: return
    members=[m for m in v.rows('site_memberships') if m.is_active and m.role in roles]
    assigned={a.user_id for a in v.rows('work_assignments',work_order_id=order.work_order_id) if a.status not in ('cancelled','declined')}
    table=v.models['maintenance_notifications'].__table__
    for member in members:
        if member.role in ('executor','technician') and member.user_id not in assigned: continue
        v.session.execute(insert(table).values(site_id=order.site_id,user_id=member.user_id,
            work_order_id=order.work_order_id,event_key=f'{order.work_order_id}:{order.revision}:{event}',
            message={'overdue':'Просрочено ТО','assigned':'Вам назначено ТО','rework':'Отчёт возвращён на доработку',
                     'submitted':'Фотоотчёт ожидает приёмки','accepted':'Работа принята'}.get(event,event))
            .on_conflict_do_nothing(index_elements=['site_id','user_id','event_key']))


def validate_execution(v,order,report,payload,submitting=False):
    links={l.equipment_id for l in v.rows('work_order_equipment',work_order_id=order.work_order_id)}
    requirements=order.operation_snapshot.get('measurement_requirements',[])
    if payload is not None:
        keys=set()
        for reading in payload.readings:
            key=(reading.equipment_id,reading.parameter_code,reading.phase)
            if key in keys or reading.equipment_id not in links or reading.measured_at>datetime.now(timezone.utc):
                raise HTTPException(422,'Проверьте оборудование, дату и уникальность показаний')
            keys.add(key)
            matching=[r for r in requirements if r.get('parameter_code')==reading.parameter_code]
            if not matching or any(r.get('unit')!=reading.unit for r in matching):
                raise HTTPException(422,'Параметр и единица должны соответствовать утверждённой методике')
            if payload.actual and payload.actual.started_at and payload.actual.performed_at and not payload.actual.started_at<=reading.measured_at<=payload.actual.performed_at:
                raise HTTPException(422,'Показание находится за пределами фактического выполнения')
        cls=v.models['work_readings']
        v.session.execute(delete(cls).where(cls.site_id==order.site_id,cls.work_report_id==report.work_report_id))
        for r in payload.readings:
            v.repo.add('work_readings',site_id=order.site_id,system_id=order.system_id,work_order_id=order.work_order_id,
                work_report_id=report.work_report_id,equipment_id=r.equipment_id,parameter_code=r.parameter_code,
                numeric_value=r.value,unit_code=r.unit,measured_at=r.measured_at,phase=r.phase,is_estimated=False)
        report.execution_context=json.loads(payload.actual.model_dump_json()) if payload.actual else {}
    if not submitting: return
    if order.operation_snapshot.get('methodology_ref') and not all(report.execution_context.get(k) for k in ("started_at","performed_at","person_hours")):
        raise HTTPException(422,'Укажите фактическое время и трудозатраты')
    readings=v.rows('work_readings',work_report_id=report.work_report_id)
    for req in requirements:
        if not req.get('required',True): continue
        for phase in req.get('phases',['before','after']):
            if not any(r.parameter_code==req['parameter_code'] and r.unit_code==req['unit'] and r.phase==phase for r in readings):
                raise HTTPException(422,f"Заполните протокол {req['parameter_code']} ({phase})")
    acts={p.verification_context.get('kind') for p in v.rows('evidence_files',work_report_id=report.work_report_id) if p.stage=='other'}
    if set(order.operation_snapshot.get('required_acts',[]))-acts:
        raise HTTPException(422,'Прикрепите обязательные акты или протоколы инструментальных проверок')


def validate_acceptance(v,order,report,payload):
    if payload.verdict!='accepted': return
    evidence=v.rows('evidence_files',work_report_id=report.work_report_id)
    required=set(order.operation_snapshot.get('required_acts',[]))
    verified={p.verification_context.get('kind') for p in evidence if p.stage=='other' and p.verification_context.get('verified_by')}
    if required-verified: raise HTTPException(422,'Контролёр должен проверить все обязательные акты')
    valid_refs={str(p.evidence_file_id) for p in evidence}
    if set(payload.additional_evidence_refs)-valid_refs: raise HTTPException(422,'Акт относится к другой попытке')
    now=datetime.now(timezone.utc)
    if order.regulatory_deadline_at and now>order.regulatory_deadline_at:
        authorization=order.exception_context.get('late_acceptance',{})
        allowed=authorization.get('report_id')==str(report.work_report_id)
        if v.principal.role=='chief_engineer' and payload.late_reason:
            order.exception_context=dict(order.exception_context,late_acceptance=dict(report_id=str(report.work_report_id),
                approved_by=str(v.principal.user_id),reason=payload.late_reason,approved_at=now.isoformat()))
        elif not allowed:
            raise HTTPException(409,'LATE_ACCEPTANCE_REQUIRES_CHIEF: нужно разрешение главного инженера с причиной задержки')


def workbook(rows):
    """Minimal standards-based XLSX. All source strings are inline strings, never formulas."""
    def cell(col,row,value):
        name=''
        while col: col,rem=divmod(col-1,26);name=chr(65+rem)+name
        return f'<c r="{name}{row}" t="inlineStr"><is><t xml:space="preserve">{escape(''.join(c for c in str(value if value is not None else "") if ord(c)>=32 or c in '\t\n\r'))}</t></is></c>'
    sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join('<row r="%d">'%i+''.join(cell(j,i,v) for j,v in enumerate(row,1))+'</row>' for i,row in enumerate(rows,1))+'</sheetData></worksheet>'
    files={
      '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
      '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
      'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ТО" sheetId="1" r:id="rId1"/></sheets></workbook>',
      'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
      'xl/worksheets/sheet1.xml':sheet}
    data=BytesIO()
    with ZipFile(data,'w',ZIP_DEFLATED) as z:
        for name,value in files.items():z.writestr(name,value.encode())
    return data.getvalue()


def register_analyst_routes(app,views,photo_path,editable):
    def chief(v):
        if v.principal.role!='chief_engineer':raise HTTPException(403,'Нужна роль главного инженера')
    def revise(order,payload):
        if order.revision!=payload.expected_revision:raise HTTPException(409,'REVISION_CONFLICT: обновите данные')

    @app.get(PREFIX+'/checklist-catalog')
    def catalog(v=Depends(views)):
        if not has_role(v.principal.role,('admin','engineer','dispatcher')): raise HTTPException(403,'Нет права редактирования регламентов')
        from pathlib import Path
        return json.loads((Path(__file__).resolve().parents[1]/'data/checklist_catalog.json').read_text(encoding='utf-8'))

    @app.get(PREFIX+'/notifications')
    def inbox(v=Depends(views)):
        return [dict(id=str(n.notification_id),message=n.message,taskId=str(n.work_order_id) if n.work_order_id else None,
                     createdAt=n.created_at,readAt=n.read_at) for n in sorted(v.rows('maintenance_notifications',user_id=v.principal.user_id),key=lambda n:n.created_at,reverse=True)[:100]]

    @app.post(PREFIX+'/notifications/read-all')
    def read_all_notifications(v=Depends(views)):
        notifications = v.models['maintenance_notifications']
        result = v.session.execute(update(notifications).where(
            notifications.site_id == v.principal.site_id,
            notifications.user_id == v.principal.user_id,
            notifications.read_at.is_(None),
        ).values(read_at=datetime.now(timezone.utc)))
        v.session.commit()
        return {'read': True, 'count': result.rowcount}

    @app.post(PREFIX+'/notifications/clear')
    def clear_notifications(v=Depends(views)):
        notifications = v.models['maintenance_notifications']
        result = v.session.execute(delete(notifications).where(
            notifications.site_id == v.principal.site_id,
            notifications.user_id == v.principal.user_id,
        ))
        v.session.commit()
        return {'cleared': True, 'count': result.rowcount}

    @app.post(PREFIX+'/notifications/{identity}/delete')
    def delete_notification(identity:UUID,v=Depends(views)):
        row=v.one('maintenance_notifications',notification_id=identity,user_id=v.principal.user_id)
        v.session.delete(row);v.session.commit();return {'deleted':True}

    @app.post(PREFIX+'/notifications/{identity}/read')
    def read_notification(identity:UUID,v=Depends(views)):
        row=v.one('maintenance_notifications',notification_id=identity,user_id=v.principal.user_id)
        row.read_at=datetime.now(timezone.utc);v.session.commit();return {'read':True}

    @app.post(PREFIX+'/tasks/{task_id}/late-authorization')
    def late_authorization(task_id:UUID,payload:Reason,v=Depends(views)):
        chief(v);order=v.task(task_id,lock=True);revise(order,payload)
        reports=sorted(v.rows('work_reports',work_order_id=task_id),key=lambda r:r.revision_no)
        if order.status!='in_review' or not reports:raise HTTPException(409,'Нет отправленной попытки')
        grant=dict(report_id=str(reports[-1].work_report_id),approved_by=str(v.principal.user_id),reason=payload.reason,approved_at=datetime.now(timezone.utc).isoformat())
        order.exception_context=dict(order.exception_context,late_acceptance=grant);order.revision+=1
        audit(v,order,'authorize_late_acceptance',grant);v.session.commit();return v.bundle(order)

    @app.post(PREFIX+'/tasks/{task_id}/reopen')
    def reopen(task_id:UUID,payload:Reason,v=Depends(views)):
        chief(v);order=v.task(task_id,lock=True);revise(order,payload)
        if order.status!='completed':raise HTTPException(409,'Открыть повторно можно только принятое задание')
        # Previous accepted reports/reviews remain immutable and downloadable.
        order.status='rework';order.revision+=1
        audit(v,order,'reopen',dict(reason=payload.reason,previous_completed_at=order.completed_at))
        notify_event(v,order,'rework',('executor','technician'));v.session.commit();return v.bundle(order)

    @app.get(PREFIX+'/tasks/{task_id}/attempts')
    def attempts(task_id:UUID,v=Depends(views)):
        v.task(task_id)
        return [v.report_view(r) for r in sorted(v.rows('work_reports',work_order_id=task_id),key=lambda r:r.revision_no)]

    @app.post(PREFIX+'/tasks/{task_id}/acts')
    def upload_act(task_id:UUID,expected_revision:int=Form(...),kind:str=Form(...),file:UploadFile=File(...),v=Depends(views)):
        from uuid import uuid4
        import hashlib
        from app.files import validate_upload
        from app.storage import safe_storage_path
        order,report=editable(v,task_id,expected_revision)
        if kind not in order.operation_snapshot.get('required_acts',[]):raise HTTPException(422,'Тип акта не указан в регламенте')
        data=file.file.read(10_485_761)
        try:mime=validate_upload(data,file.filename,file.content_type)
        except Exception:raise HTTPException(422,'Прикрепите скан акта JPEG/PNG/WebP до 10 МиБ') from None
        identity=uuid4();key=f'{order.site_id}/{identity}'
        path=safe_storage_path(app.state.settings.photo_storage_root,key)
        try:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            v.repo.add('evidence_files',evidence_file_id=identity,site_id=order.site_id,work_order_id=task_id,
                work_report_id=report.work_report_id,uploaded_by=v.principal.user_id,stage='other',storage_key=key,
                mime_type=mime,file_size=len(data),sha256=hashlib.sha256(data).hexdigest(),verification_context={'kind':kind})
            order.revision+=1;audit(v,order,'upload_act',dict(id=identity,kind=kind));v.session.commit()
        except BaseException:
            path.unlink(missing_ok=True);raise
        return v.bundle(order)

    @app.post(PREFIX+'/tasks/{task_id}/acts/{identity}/verify')
    def verify_act(task_id:UUID,identity:UUID,payload:Reason,v=Depends(views)):
        if not has_role(v.principal.role,('engineer',)):raise HTTPException(403,'Нужен контролёр')
        order=v.task(task_id,lock=True);revise(order,payload)
        evidence=v.one('evidence_files',evidence_file_id=identity,work_order_id=task_id,stage='other')
        if order.status!='in_review' or evidence.work_report_id!=max(v.rows('work_reports',work_order_id=task_id),key=lambda r:r.revision_no).work_report_id:
            raise HTTPException(409,'Проверяйте акт текущей отправленной попытки')
        if evidence.uploaded_by==v.principal.user_id:raise HTTPException(403,'Нельзя подтверждать свой акт')
        evidence.verification_context=dict(evidence.verification_context,verified_by=str(v.principal.user_id),reason=payload.reason,verified_at=datetime.now(timezone.utc).isoformat())
        order.revision+=1;audit(v,order,'verify_act',evidence.verification_context);v.session.commit();return v.bundle(order)

    @app.get(PREFIX+'/plans')
    def plans(year:int,month:int,v=Depends(views)):
        return [dict(id=str(p.schedule_plan_id),revision=p.revision,status=p.status,approvedBy=str(p.approved_by) if p.approved_by else None,approvedAt=p.approved_at) for p in v.rows('schedule_plans',period_year=year,period_month=month)]

    @app.post(PREFIX+'/plans/{identity}/approve')
    def approve_plan(identity:UUID,payload:Reason,v=Depends(views)):
        chief(v);cls=v.models['schedule_plans']
        row=v.session.scalar(select(cls).where(cls.site_id==v.principal.site_id,cls.schedule_plan_id==identity).with_for_update())
        if row is None:raise HTTPException(404,'План не найден')
        revise(row,payload)
        if row.status!='draft':raise HTTPException(409,'Утверждается только черновик плана')
        row.status='approved';row.approved_by=v.principal.user_id;row.approved_at=datetime.now(timezone.utc)
        from .planning import catalog_token
        row.source_snapshot=dict(row.source_snapshot,approved_catalog_token=catalog_token(v),approval_reason=payload.reason,approved_rule_versions=sorted(str(b.maintenance_rule_id) for b in v.rows("rule_equipment") if b.rule.publication_status=="published" and not b.rule.schedule_parameters.get("superseded_binding")))
        v.repo.add('audit_events',site_id=row.site_id,actor_type='user',actor_user_id=v.principal.user_id,
            entity_type='schedule_plans',entity_id=identity,action='approve',after_snapshot=dict(reason=payload.reason))
        v.session.commit();return dict(status=row.status)

    @app.get(PREFIX+'/overview')
    def overview(v=Depends(views)):
        if v.principal.role not in ('director','chief_engineer','engineer','dispatcher','admin'):raise HTTPException(403,'Нет доступа к сводке')
        from .projections import Views
        sites=[v.one('sites',site_id=v.principal.site_id)]
        if v.principal.role=='director':
            members=v.models['site_memberships'];sitecls=v.models['sites']
            sites=v.session.scalars(select(sitecls).join(members,members.site_id==sitecls.site_id).where(members.user_id==v.principal.user_id,members.role=='director',members.is_active,sitecls.is_active)).all()
        result=[]
        for site in sites:
            scoped=Views(v.session,v.models,Principal(v.principal.user_id,site.site_id,v.principal.role,v.principal.name,v.principal.email,site.name,site.timezone))
            orders=scoped.rows('work_orders');reviews=[r for r in scoped.rows('acceptance_reviews') if r.decision=='accepted']
            deadlines={o.work_order_id:o.regulatory_deadline_at for o in orders}
            ontime=sum(1 for r in reviews if deadlines.get(r.work_order_id) and r.reviewed_at<=deadlines[r.work_order_id])
            eligible=sum(1 for r in reviews if deadlines.get(r.work_order_id))
            hours=[Decimal(r.execution_context['person_hours']) for r in scoped.rows('work_reports') if r.submitted_at and r.execution_context.get('person_hours')]
            norms=[Decimal(o.norm_hours_snapshot)*(o.required_people_snapshot if o.operation_snapshot.get("norm_unit")=="elapsed_hour" else 1) for o in orders if o.status!="cancelled" and o.operation_snapshot.get("norm_unit") in ("person_hour","elapsed_hour")]
            loads={}
            for order in orders:
                if order.planned_start_at and order.operation_snapshot.get('planning_duration_minutes'):
                    day=order.planned_start_at.astimezone(__import__('zoneinfo').ZoneInfo(site.timezone)).date().isoformat()
                    loads[day]=loads.get(day,0)+order.operation_snapshot['planning_duration_minutes']*order.required_people_snapshot
            result.append(dict(siteId=str(site.site_id),siteName=site.name,jobs=len(orders),accepted=len(reviews),slaOnTime=ontime,slaEligible=eligible,
                plannedNormPersonHours=str(sum(norms)) if norms else None,confirmedNormJobs=len(norms),actualPersonHours=str(sum(hours)) if hours else None,actualReports=len(hours),loadPersonMinutes=loads,
                overdue=sum(bool(o.regulatory_deadline_at and o.regulatory_deadline_at<datetime.now(timezone.utc) and o.status not in ('completed','cancelled')) for o in orders)))
        return result

    @app.get(PREFIX+'/export.xlsx')
    def export(year:int,month:int,kind:Literal['schedule','orders']='schedule',v=Depends(views)):
        if v.principal.role not in ('director','chief_engineer','engineer','dispatcher','admin'):raise HTTPException(403,'Нет права экспорта')
        from calendar import monthrange
        if not 2000<=year<=2100 or not 1<=month<=12:raise HTTPException(422,'Некорректный месяц')
        if kind=='orders':
            rows=[['Задание','Операция','Оборудование','Статус','Срок','Численность','Норма','Единица']]
            for order in v.rows('work_orders'):
                task=v.task_view(order)
                if task['mandatoryDueDate'] and task['mandatoryDueDate'].startswith(f'{year:04}-{month:02}'):
                    rows.append([task['code'],task['title'],task['equipmentName'],task['state'],task['mandatoryDueDate'],task['crewSize'],task['normHours'],task['normUnit']])
        else:
            rows=[['Оборудование','Операция','Частота','Численность','Норма','Единица']+list(range(1,monthrange(year,month)[1]+1))]
            from .calendar import preview_calendar
            preview=preview_calendar(v,year,month)
            for binding in v.rows('rule_equipment'):
                if binding.rule.schedule_parameters.get('superseded_binding'):continue
                rule=binding.rule
                dates={int(i.get('sourceDate',i['mandatoryDueDate'])[-2:]):i['occurrenceDate'] for i in preview['items'] if i['bindingId']==str(binding.binding_id)}
                rows.append([binding.equipment.name,rule.operation.code,rule.source_text,rule.required_people,rule.norm_hours,rule.schedule_parameters.get('norm_unit','unconfirmed')]+[(('ПЛАН → '+dates[d]) if dates[d]!=f'{year:04}-{month:02}-{d:02}' else 'ПЛАН') if d in dates else '' for d in range(1,monthrange(year,month)[1]+1)])
        return Response(workbook(rows),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="maintenance-{kind}-{year}-{month:02}.xlsx"','Cache-Control':'private, no-store'})

    @app.get(PREFIX+'/schedule-matrix')
    def matrix(year:int,month:int,v=Depends(views)):
        if not 2000<=year<=2100 or not 1<=month<=12:raise HTTPException(422,'Некорректный месяц')
        from .calendar import preview_calendar
        preview=preview_calendar(v,year,month)
        result=[]
        visible=v.visible_equipment_ids() if v.principal.role=='executor' else None
        for b in v.rows('rule_equipment'):
            if b.rule.schedule_parameters.get('superseded_binding') or (visible is not None and b.equipment_id not in visible):continue
            r=b.rule;eq=b.equipment
            system=v.one('engineering_systems',system_id=eq.system_id)
            parent=v.one('equipment',equipment_id=eq.parent_equipment_id) if eq.parent_equipment_id else None
            result.append(dict(bindingId=str(b.binding_id),system=system.name,complex=parent.name if parent else None,
                equipment=eq.name,equipmentId=str(eq.equipment_id),code=r.operation.code,title=r.operation.title,
                frequency=r.source_text,crewSize=r.required_people,normValue=str(r.norm_hours) if r.norm_hours is not None else None,
                normUnit=r.schedule_parameters.get('norm_unit','unconfirmed'),published=r.publication_status=='published' and r.edition.is_approved,
                dates=[i.get('sourceDate',i['mandatoryDueDate']) for i in preview['items'] if i['bindingId']==str(b.binding_id)],
                transfers={i.get('sourceDate',i['mandatoryDueDate']):i['occurrenceDate'] for i in preview['items'] if i['bindingId']==str(b.binding_id) and i.get('sourceDate',i['mandatoryDueDate'])!=i['occurrenceDate']}))
        return dict(rows=result,diagnostics=preview['diagnostics'],year=year,month=month)

    @app.post(PREFIX+'/comparisons/{run_id}/confirm')
    def confirm_forecast(run_id:UUID,command:ForecastSelection,v=Depends(views)):
        if not has_role(v.principal.role,('engineer','dispatcher')):raise HTTPException(403,'Решение подтверждает инженер')
        decisions=[d for d in v.rows('orchestration_decisions') if d.comparison_snapshot.get('ui',{}).get('runId')==str(run_id)]
        if not decisions:raise HTTPException(404,'Сравнение не найдено')
        decision=decisions[0];ui=decision.comparison_snapshot['ui']
        from .projections import Views
        from zoneinfo import ZoneInfo
        day=command.selected_date;today=datetime.now(ZoneInfo(v.principal.timezone)).date()
        due=date.fromisoformat(ui['mandatoryDueDate']) if ui.get('mandatoryDueDate') else None
        if due is None or day>due or day<today:raise HTTPException(422,'Нельзя выбрать дату позже обязательного срока или в прошлом')
        early=day<due
        if early and v.principal.role!='chief_engineer':raise HTTPException(403,'Раннюю некалиброванную рекомендацию утверждает главный инженер')
        if early and (ui['ai']['status']!='ok' or ui['ai'].get('recommendedDate')!=str(day)):
            raise HTTPException(422,'У AI нет такой подтверждаемой рекомендации')
        inputrow=v.one('forecast_runs',forecast_run_id=decision.rule_forecast_id)
        snapshot=inputrow.input_snapshot;binding=v.one('rule_equipment',binding_id=UUID(snapshot['binding_id']))
        from .forecasting import binding_input,make_snapshot
        original=__import__('app.schemas.maintenance',fromlist=['ForecastSnapshot']).ForecastSnapshot.model_validate_json(json.dumps(snapshot))
        current=make_snapshot(v,binding_input(v,binding,as_of=original.as_of),original.earliest_date,original.mandatory_due_date,as_of=original.as_of,snapshot_id=original.snapshot_id,source_day=original.source_occurrence_date)
        if current.content_sha256!=original.content_sha256:raise HTTPException(409,'STALE_SNAPSHOT: пересчитайте рекомендации на актуальных данных')
        cls=v.models['orchestration_decisions']
        v.session.scalar(select(cls).where(cls.orchestration_decision_id==decision.orchestration_decision_id).with_for_update())
        existing=[a for a in v.rows('audit_events',entity_id=decision.orchestration_decision_id) if a.action=='confirm_forecast']
        if existing:
            saved=existing[-1].after_snapshot
            if saved['selected_date']!=str(day) or saved['reason']!=command.reason:raise HTTPException(409,'Решение уже подтверждено; для нового решения повторите прогноз')
            return dict(**saved,replayed=True)
        task_id=None
        earliest=date.fromisoformat(ui['earliestDate']) if ui.get('earliestDate') else due
        if early and day<earliest:
            # An extra approved inspection must not discharge tomorrow's daily obligation.
            from .incidents import IncidentSelection
            incident=v.repo.add('incident_reports',site_id=v.principal.site_id,system_id=binding.system_id,equipment_id=binding.equipment_id,
                reported_by=v.principal.user_id,description='Досрочное ТО по AI-рекомендации: '+command.reason,
                ai_result_snapshot=dict(source_comparison=str(run_id)))
            v.session.flush()
            # Reuse the same fully validated chief approval path as manual incidents.
            task_id=app.state.create_incident_task(incident.incident_report_id,IncidentSelection(binding_id=binding.binding_id,planned_date=day,reason=command.reason),v,commit=False)['taskId']
        else:
            entries=[e for e in v.rows('schedule_entries',binding_id=binding.binding_id) if e.regulatory_deadline_on==due and e.status=='planned' and (original.source_occurrence_date is None or e.source_date==original.source_occurrence_date)]
            if len(entries)!=1:raise HTTPException(409,'Создайте единственное регламентное задание перед подтверждением')
            entry=entries[0];orders=v.rows('work_orders',schedule_entry_id=entry.schedule_entry_id)
            if not orders or orders[0].status not in ('draft','assigned'):raise HTTPException(409,'Работа уже начата или завершена')
            order=v.task(orders[0].work_order_id,lock=True)
            if order.status=='assigned' and entry.planned_date!=day:raise HTTPException(409,'Перед изменением даты снимите назначение и повторите подбор')
            entry.planned_date=day;task_id=str(order.work_order_id);order.revision+=1
            order.exception_context=dict(order.exception_context,confirmed_forecast=dict(run_id=str(run_id),selected_date=str(day),reason=command.reason,by=str(v.principal.user_id)))
        saved=dict(selected_date=str(day),reason=command.reason,approved_by=str(v.principal.user_id),taskId=task_id,extra_maintenance=bool(early and day<earliest))
        v.repo.add('audit_events',site_id=v.principal.site_id,actor_type='user',actor_user_id=v.principal.user_id,
            entity_type='orchestration_decisions',entity_id=decision.orchestration_decision_id,action='confirm_forecast',after_snapshot=saved)
        v.session.commit();return saved

    @app.post(PREFIX+'/tasks/{task_id}/late-execution')
    def permit_late_execution(task_id:UUID,command:LateExecution,v=Depends(views)):
        chief(v);order=v.task(task_id,lock=True);revise(order,command)
        now=datetime.now(timezone.utc)
        if order.status not in ('draft','assigned','in_progress','rework') or not order.regulatory_deadline_at or order.regulatory_deadline_at>=now:
            raise HTTPException(409,'Разрешение выдаётся для незакрытой просроченной работы')
        if not now<command.until<=now+timedelta(days=30):raise HTTPException(422,'Укажите явное окно не более 30 суток')
        grant=dict(until=command.until.isoformat(),approved_by=str(v.principal.user_id),reason=command.reason,approved_at=now.isoformat())
        order.exception_context=dict(order.exception_context,late_execution=grant);order.revision+=1
        if order.overdue_since_at is None:order.overdue_since_at=order.regulatory_deadline_at
        audit(v,order,'authorize_late_execution',grant);v.session.commit();return v.bundle(order)
