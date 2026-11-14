"""Immutable drafts from the reviewed common requirements ledger.

Regulations retain real binding/rule/edition IDs. No live orders are written.
"""
from datetime import datetime,time,timedelta
from decimal import Decimal
from uuid import UUID,uuid4,uuid5
from zoneinfo import ZoneInfo
import json
from fastapi import Depends,HTTPException,Query,Response
from sqlalchemy import text
from app.schemas.draft_plans import DraftList,DraftRecord,WorkOccurrence,WorkSegment
from app.schemas.portfolio import PortfolioInput,PortfolioPreview,SavePortfolio
from app.scheduling.draft_generator import expand
from app.scheduling.draft_validator import digest
from . import requirements
from .draft_plans import clean,checked,persist,metadata,get_version,_lock_catalog,EDIT_ROLES
from .catalog_imports import READ_ROLES
from .management import PREFIX,_guard,_edit
from .assignment import local_time

BASE=PREFIX+'/portfolio-plans'
GENERATOR_VERSION='portfolio-occurrences-v1'


def capture(v,request):
    result,items,facts,issues=requirements.preview(v,request.requirements,capture=True)
    equipment={str(row['equipment']['equipment_id']):row['equipment'] for row in facts.get('bindings',[])}
    if 'catalog' in facts:equipment.update(facts['catalog']['source']['equipment'])
    source=clean(dict(site_id=v.principal.site_id,timezone=result['timezone'],equipment=equipment,summary=result['summary'],
        requirements=[x.model_dump(mode='json') for x in items],facts=facts,issues=issues))
    # The read-only ledger hashes its observation day. A saved future plan must
    # survive midnight when the actual facts and requirement states did not
    # change; overdue transitions and newly accepted/issued work still differ.
    source['requirements_sha256']=digest(source)
    return source


def generate(v,request):
    source=capture(v,request);roots=[];segments=[]
    issues=[dict(code=x['code'],message=(x.get('source_label','')+': ' if x.get('source_label') else '')+x['message'],row_number=x.get('source_row')) for x in source['issues']]
    new={x['requirement_id']:x for x in source['requirements'] if x['state']=='new'}
    if any(x['state']=='review' for x in source['requirements']):
        issues.append(dict(code='REQUIREMENTS_REVIEW',message='Уточните все спорные обязательства выбранного состава'))
    bindings={str(x['binding']['binding_id']):x for x in source['facts'].get('bindings',[])}
    tz=ZoneInfo(source['timezone'])
    for x in new.values():
        if x['source_kind']!='regulation':continue
        fact=bindings[x['binding_id']];rule=fact['rule'];parameters=rule['schedule_parameters']
        try:
            left=local_time(datetime.combine(datetime.fromisoformat(x['earliest_date']).date(),time.min),tz)
            right=local_time(datetime.combine(datetime.fromisoformat(x['due_date']).date()+timedelta(days=1),time.min),tz)
        except HTTPException:
            issues.append(dict(code='LOCAL_TIME_AMBIGUOUS',message='Переход часового пояса требует уточнения допустимых дат'));continue
        if x['person_hours'] is None or not parameters.get('planning_duration_minutes'):
            issues.append(dict(code='NORM_UNCONFIRMED',message='Подтвердите норму и длительность регламентной работы'));continue
        root=WorkOccurrence(occurrence_id=x['requirement_id'],site_id=source['site_id'],import_id=None,source_row=None,decision_revision=None,
            source_kind='regulation',binding_id=x['binding_id'],rule_id=x['rule_id'],regulation_id=x['regulation_id'],
            source_sha256=digest(fact),parser_version='approved-regulation-v1',source_cells=[],source_date=x['source_date'],source_slot='whole_day',
            date_basis='accepted_history' if parameters.get('calendar_basis',parameters.get('basis'))=='after_accepted_completion' else 'regulation_rule',
            title=x['title'],operation_code=x['operation_code'],maintenance_type=x['maintenance_type'],interpretation='ALLOWED_WINDOW',
            equipment_ids=x['equipment_ids'],earliest_date=x['earliest_date'],latest_date=x['due_date'],allowed_intervals=[dict(start_at=left,end_at=right)],
            total_person_hours=x['person_hours'],crew_size=x['crew_size'],splittable=False,min_segment_minutes=None,
            minimum_duration_minutes=parameters['planning_duration_minutes'],qualification_ids=x['qualification_ids'],qualifications_confirmed=True,
            included_rows=[],norm_ref=parameters.get('methodology_ref') or rule['source_ref'],norm_scope='per_asset',policy_note=x['explanation'])
        roots.append(root);segments.append(WorkSegment(segment_id=uuid5(root.occurrence_id,'initial:0'),occurrence_id=root.occurrence_id,
            equipment_ids=root.equipment_ids,person_hours=root.total_person_hours))
    if request.requirements.catalog:
        frozen=source['facts']['catalog']['source']
        # JSON snapshots have string object keys; the catalog generator uses row numbers.
        frozen=dict(frozen,operations={int(k):val for k,val in frozen['operations'].items()},decisions={int(k):val for k,val in frozen['decisions'].items()})
        catalog_roots,catalog_segments,_=expand(frozen,request.requirements.catalog)
        roots.extend(r for r in catalog_roots if str(r.occurrence_id) in new)
        segments.extend(s for s in catalog_segments if str(s.occurrence_id) in new)
    if not roots:issues.append(dict(code='NO_NEW_OCCURRENCES',message='Нет новых подтверждённых работ для сохранения'))
    if len(roots)>5000 or len(segments)>10000:raise HTTPException(422,'Сократите горизонт или состав черновика')
    normalized=request.model_dump(mode='json');normalized['requirements']['binding_ids'].sort()
    if normalized['requirements']['catalog']:normalized['requirements']['catalog']['row_numbers'].sort()
    snapshot=dict(generator_version=GENERATOR_VERSION,input=normalized,source=source,source_digest=digest(source))
    if len(json.dumps(snapshot).encode())>24*1024*1024:raise HTTPException(422,'Снимок слишком велик: сократите горизонт или состав')
    preview=dict(input_sha256=digest(dict(snapshot=snapshot,actor=str(v.principal.user_id))),generator_version=GENERATOR_VERSION,
        total_occurrences=len(roots),total_segments=len(segments),total_person_hours=sum((r.total_person_hours for r in roots),Decimal(0)),
        selected_rows=source['summary']['selected_catalog_rows'],unselected_rows=source['summary']['unselected_catalog_rows'],
        can_save=bool(roots) and not issues and source['summary']['complete'],issues=issues[:25],total_issues=len(issues),items=roots[:25],
        excluded_occurrences=sum(x['state'] in ('existing','fulfilled') for x in source['requirements']),requirements_sha256=source['requirements_sha256'])
    return preview,snapshot,roots,segments


def register_routes(app,views):
    @app.post(BASE+'/preview',response_model=PortfolioPreview)
    def preview(command:PortfolioInput,response:Response,v=Depends(views)):
        _guard(v,*EDIT_ROLES);response.headers['Cache-Control']='private, no-store'
        return generate(v,command)[0]

    @app.post(BASE,response_model=DraftRecord,status_code=201)
    def create(command:SavePortfolio,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            _lock_catalog(v)
            request_sha=digest(dict(actor=str(v.principal.user_id),command=command.model_dump(mode='json')))
            old=v.session.execute(text('SELECT draft_id,revision,request_sha256 FROM planning_draft_versions WHERE site_id=:site AND idempotency_key=:key'),
                dict(site=v.principal.site_id,key=command.idempotency_key)).mappings().first()
            if old:
                if old['request_sha256']!=request_sha:raise HTTPException(409,'Этот ключ повтора уже использован для другого запроса')
                response.status_code=200;return metadata(get_version(v,old['draft_id'],old['revision'],full=False))
            result,snapshot,roots,segments=generate(v,command.input)
            if result['input_sha256']!=command.preview_sha256:raise HTTPException(409,'Состав или пользователь изменились. Повторите предпросмотр')
            if not result['can_save']:raise HTTPException(422,'Уточните замечания выбранного состава перед сохранением')
            report,facts=checked(v,snapshot,roots,segments,capture=True)
            record=persist(v,draft_id=uuid4(),revision=1,title=command.title,reason=command.reason,snapshot=snapshot,
                sha=result['input_sha256'],occurrences=roots,segments=segments,report=report,resource_snapshot=facts,
                key=command.idempotency_key,request_sha=request_sha)
        return record

    @app.get(BASE,response_model=DraftList)
    def listing(response:Response,offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);params=dict(site=v.principal.site_id,offset=offset)
        rows=v.session.execute(text('''SELECT d.*,u.full_name AS author_name FROM
            (SELECT DISTINCT ON (draft_id) draft_id,revision,parent_revision,import_id,title,starts_on,ends_on,created_at,created_by,reason,input_sha256,summary
            FROM planning_draft_versions WHERE site_id=:site AND import_id IS NULL ORDER BY draft_id,revision DESC) d
            JOIN users u ON u.user_id=d.created_by ORDER BY d.created_at DESC,d.draft_id LIMIT 25 OFFSET :offset'''),params).mappings().all()
        total=v.session.scalar(text('SELECT count(DISTINCT draft_id) FROM planning_draft_versions WHERE site_id=:site AND import_id IS NULL'),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[metadata(r) for r in rows],total=total)
