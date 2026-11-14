"""Immutable scenario versions, source lineage and shared validation.

Active schedule_plans/entries and assignments are deliberately never written.
"""
from collections import defaultdict
from calendar import monthrange
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from uuid import UUID,uuid4
from zoneinfo import ZoneInfo
import json
from fastapi import Depends,HTTPException,Query,Response
from sqlalchemy import text
from app.schemas.draft_plans import (GenerationInput,GenerationPreview,SaveDraft,EditSegments,DraftList,
    DraftRecord,DraftOverview,OccurrencePage,SegmentPage,PlanValidation,WorkOccurrence,WorkSegment,PlanningChoices,LocalPlacement,PreparedSourceChoices,ChangeDraftPolicy,DraftPolicyView)
from app.scheduling.draft_generator import expand,GENERATOR_VERSION
from app.scheduling.draft_validator import validate,digest
from .catalog_imports import READ_ROLES
from .catalog_decisions import latest,records,load as load_decisions
from .management import PREFIX,_guard,_edit,_audit
from .draft_resources import resources
from .assignment import local_time

EDIT_ROLES=('chief_engineer','dispatcher','admin')
BASE=PREFIX+'/draft-plans'


def clean(value): return json.loads(json.dumps(value,default=str))


def source_snapshot(v,request):
    meta=v.session.execute(text('''SELECT source_sha256,parser_version,ARRAY(SELECT (o->>'row')::int
        FROM jsonb_array_elements(c.catalog_data->'operations') o) AS row_numbers
        FROM regulation_catalog_imports c WHERE site_id=:site AND import_id=:id'''),dict(site=v.principal.site_id,id=request.import_id)).mappings().first()
    if not meta: raise HTTPException(404,'Каталог не найден')
    decisions=latest(v,request.import_id,request.row_numbers)
    parents={r['payload'].get('included_in_row') for r in decisions.values()}-{None}
    if parents: decisions.update(latest(v,request.import_id,list(parents)))
    asset_ids={UUID(str(i)) for r in decisions.values() for i in r['payload']['equipment_ids']}
    assets={str(r['equipment_id']):dict(r) for r in v.session.execute(text('''SELECT equipment_id,asset_code,name,status,revision,commissioned_on,system_id,
        properties->>'data_origin' AS data_origin FROM equipment WHERE site_id=:site AND equipment_id=ANY(CAST(:ids AS uuid[]))'''),
        dict(site=v.principal.site_id,ids=list(asset_ids))).mappings()}
    operation_rows=v.session.execute(text('''SELECT o - 'raw_cells' AS operation FROM regulation_catalog_imports c,
        LATERAL jsonb_array_elements(c.catalog_data->'operations') o
        WHERE c.site_id=:site AND c.import_id=:id AND (o->>'row')::int=ANY(CAST(:rows AS integer[]))'''),
        dict(site=v.principal.site_id,id=request.import_id,rows=request.row_numbers)).scalars().all()
    operations={r['row']:{k:r[k] for k in ('row','code','title','maintenance_type','frequency_raw','source_cells','calendar_marks')} for r in operation_rows}
    # The immutable source owns formulas/raw values; generation uses just literal marks.
    for row in operations.values(): row['calendar_marks']=[{k:m[k] for k in ('day','address','text')} for m in row['calendar_marks']]
    site=v.one('sites',site_id=v.principal.site_id)
    return dict(site_id=site.site_id,timezone=site.timezone,source_sha256=meta['source_sha256'],parser_version=meta['parser_version'],
        operation_count=len(meta['row_numbers']),operations=operations,equipment=assets,
        decisions=records(set(meta['row_numbers']),decisions,assets,[r for r in request.row_numbers if r in meta['row_numbers']]))


def generate(v,request,*,capture_issues=False):
    source=source_snapshot(v,request)
    occurrences,segments,issues=expand(source,request)
    for occurrence in occurrences:
        latest_commission=max((date.fromisoformat(str(source['equipment'][str(i)]['commissioned_on'])) for i in occurrence.equipment_ids
            if source['equipment'][str(i)]['commissioned_on']),default=None)
        if latest_commission and occurrence.earliest_date<latest_commission:
            issues.append(dict(code='BEFORE_COMMISSIONING',message='Допустимые даты начинаются до ввода выбранного оборудования',row_number=occurrence.source_row))
    if not occurrences and not issues: issues.append(dict(code='NO_OCCURRENCES',message='В выбранном горизонте нет подтверждённых событий'))
    normalized=request.model_dump(mode='json');normalized['row_numbers'].sort()
    snapshot=dict(generator_version=GENERATOR_VERSION,input=normalized,source=clean(source),source_digest=digest(clean(source)))
    sha=digest(dict(snapshot=snapshot,actor=str(v.principal.user_id)))
    preview=dict(input_sha256=sha,generator_version=GENERATOR_VERSION,total_occurrences=len(occurrences),total_segments=len(segments),
        total_person_hours=sum((r.total_person_hours for r in occurrences),Decimal(0)),selected_rows=len(request.row_numbers),
        unselected_rows=source['operation_count']-len(source['operations']),can_save=bool(occurrences) and not issues,
        total_issues=len(issues),issues=issues[:25],items=occurrences[:25])
    result=(preview,snapshot,occurrences,segments)
    return (*result,issues) if capture_issues else result


def checked(v,snapshot,occurrences,segments,*,stale=False,previous=(),unlock=False,capture=False):
    request=GenerationInput.model_validate(snapshot['input'])
    tz=ZoneInfo(snapshot['source']['timezone']);now=datetime.now(timezone.utc)
    start=datetime.combine(request.starts_on,time.min,tz)
    end=datetime.combine(request.ends_on+timedelta(days=2),time.min,tz)
    people,equipment,unknown=resources(v,start,end,now,{i for o in occurrences for i in o.equipment_ids})
    report=validate(occurrences,segments,people,request.policy,request.starts_on,request.ends_on,str(tz),now,
        source_stale=stale,equipment_bookings=equipment,equipment_unknown=unknown,previous_segments=previous,unlock=unlock)
    facts=dict(as_of=now.isoformat(),workers=[w.model_dump(mode='json') for w in people],
        equipment_bookings={str(k):[(a.isoformat(),b.isoformat()) for a,b in values] for k,values in equipment.items()},equipment_unknown=sorted(map(str,unknown)))
    return (report,facts) if capture else report


def metadata(row):
    data={k:row[k] for k in ('draft_id','revision','parent_revision','import_id','title','starts_on','ends_on','created_at','created_by','author_name','reason','input_sha256')}
    return dict(data,**row['summary'])


def get_version(v,identity,revision=None,*,full=True):
    meta='d.draft_id,d.revision,d.parent_revision,d.import_id,d.title,d.starts_on,d.ends_on,d.created_at,d.created_by,d.reason,d.input_sha256,d.summary'
    columns='d.*' if full is True else meta+',d.validation_snapshot,d.month_summary' if full=='overview' else meta
    row=v.session.execute(text('SELECT '+columns+''',u.full_name AS author_name FROM planning_draft_versions d JOIN users u ON u.user_id=d.created_by
        WHERE d.site_id=:site AND d.draft_id=:id'''+(' AND d.revision=:revision' if revision else '')+' ORDER BY d.revision DESC LIMIT 1'),
        dict(site=v.principal.site_id,id=identity,revision=revision)).mappings().first()
    if not row: raise HTTPException(404,'Версия плана не найдена')
    return dict(row)


def persist(v,*,draft_id,revision,title,reason,snapshot,sha,occurrences,segments,report,resource_snapshot,key=None,request_sha=None,action=None):
    request=GenerationInput.model_validate(snapshot['input']);identity=uuid4()
    summary=dict(occurrence_count=len(occurrences),segment_count=len(segments),total_person_hours=str(sum((o.total_person_hours for o in occurrences),Decimal(0))))
    due=defaultdict(Decimal);planned=defaultdict(Decimal)
    for o in occurrences: due[o.latest_date.isoformat()[:7]]+=o.total_person_hours
    for day in report.days: planned[day.date.isoformat()[:7]]+=day.planned_person_hours
    months=[dict(month=m,due_person_hours=str(due[m]),planned_person_hours=str(planned[m])) for m in sorted(set(due)|set(planned))]
    v.session.execute(text('''INSERT INTO planning_draft_versions
        (version_id,draft_id,site_id,import_id,revision,parent_revision,created_by,title,reason,starts_on,ends_on,input_sha256,
        source_snapshot,resource_snapshot,occurrences,segments,validation_snapshot,summary,month_summary,idempotency_key,request_sha256)
        VALUES (:id,:draft,:site,:catalog,:revision,:parent,:actor,:title,:reason,:start,:end,:sha,
        CAST(:source AS jsonb),CAST(:resources AS jsonb),CAST(:occurrences AS jsonb),CAST(:segments AS jsonb),CAST(:validation AS jsonb),CAST(:summary AS jsonb),CAST(:months AS jsonb),:key,:request_sha)'''),
        dict(id=identity,draft=draft_id,site=v.principal.site_id,catalog=request.import_id,revision=revision,parent=revision-1 if revision>1 else None,
            actor=v.principal.user_id,title=title,reason=reason,start=request.starts_on,end=request.ends_on,sha=sha,
            source=json.dumps(snapshot,default=str),resources=json.dumps(resource_snapshot),occurrences=json.dumps([o.model_dump(mode='json') for o in occurrences]),
            segments=json.dumps([s.model_dump(mode='json') for s in segments]),validation=report.model_dump_json(),summary=json.dumps(summary),months=json.dumps(months),key=key,request_sha=request_sha))
    _audit(v,'planning_draft_versions',identity,action or ('create' if revision==1 else 'edit_segments'),dict(draft_id=str(draft_id),revision=revision,source_sha256=sha,status=report.status))
    return metadata(get_version(v,draft_id,revision,full=False))


def _lock_catalog(v):
    v.session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),dict(key=f'catalog:{v.principal.site_id}'))


def register_routes(app,views):
    @app.get(BASE+'/{identity}/policy',response_model=DraftPolicyView)
    def policy_view(identity:UUID,response:Response,revision:int|None=Query(None,ge=1),v=Depends(views)):
        _guard(v,*READ_ROLES)
        row=get_version(v,identity,revision,full=False)
        policy=v.session.scalar(text("SELECT source_snapshot#>'{input,policy}' FROM planning_draft_versions WHERE site_id=:site AND draft_id=:id AND revision=:revision"),
            dict(site=v.principal.site_id,id=identity,revision=row['revision']))
        response.headers['Cache-Control']='private, no-store'
        return dict(record=metadata(row),policy=policy)

    @app.post(BASE+'/{identity}/policy',response_model=DraftRecord)
    def change_policy(identity:UUID,command:ChangeDraftPolicy,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            _lock_catalog(v)
            request_sha=digest(dict(actor=str(v.principal.user_id),draft_id=str(identity),command=command.model_dump(mode='json')))
            old=v.session.execute(text('SELECT draft_id,revision,request_sha256 FROM planning_draft_versions WHERE site_id=:site AND idempotency_key=:key'),
                dict(site=v.principal.site_id,key=command.idempotency_key)).mappings().first()
            if old:
                if old['request_sha256']!=request_sha:raise HTTPException(409,'Ключ повтора использован для другого изменения параметров')
                return metadata(get_version(v,old['draft_id'],old['revision'],full=False))
            row=get_version(v,identity)
            if row['revision']!=command.expected_revision:raise HTTPException(409,'Версия плана изменилась; параметры сохранены в форме, обновите актуальную версию')
            snapshot=clean(row['source_snapshot']);request=GenerationInput.model_validate(snapshot['input'])
            if digest(clean(source_snapshot(v,request)))!=snapshot['source_digest'] or snapshot['generator_version']!=GENERATOR_VERSION:
                raise HTTPException(409,'Источник изменился; создайте актуальный расчёт перед изменением параметров')
            if (request.policy.day_start_minute,request.policy.night_start_minute)!=(command.policy.day_start_minute,command.policy.night_start_minute):
                raise HTTPException(422,'Изменение границ событий день/ночь требует нового расчёта состава работ')
            snapshot['input']['policy']=command.policy.model_dump(mode='json')
            roots=[WorkOccurrence.model_validate(o) for o in row['occurrences']]
            segments=[WorkSegment.model_validate(s) for s in row['segments']]
            report,facts=checked(v,snapshot,roots,segments,capture=True)
            # Constraints may make the unchanged draft incomplete/invalid. Keep
            # the truthful report; never silently move locks or active orders.
            result=persist(v,draft_id=identity,revision=row['revision']+1,title=row['title'],reason=command.reason,snapshot=snapshot,
                sha=digest(dict(snapshot=snapshot,actor=str(v.principal.user_id))),occurrences=roots,segments=segments,report=report,
                resource_snapshot=facts,key=command.idempotency_key,request_sha=request_sha,action='change_policy')
        return result

    @app.get(BASE+'/source-choices/{import_id}',response_model=PreparedSourceChoices)
    def source_choices(import_id:UUID,response:Response,q:str=Query('',max_length=320),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES)
        rows,decisions,equipment=load_decisions(v,import_id)
        ready=[n for n,r in records(rows,decisions,equipment).items() if r['prepared']]
        params=dict(site=v.principal.site_id,id=import_id,rows=ready,offset=offset,
            q='%'+q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        body=" FROM regulation_catalog_imports c,LATERAL jsonb_array_elements(c.catalog_data->'operations') o WHERE c.site_id=:site AND c.import_id=:id AND (o->>'row')::int=ANY(CAST(:rows AS integer[])) AND concat(o->>'code',' ',o->>'title') ILIKE :q"
        items=v.session.execute(text("SELECT (o->>'row')::int AS row_number,o->>'code' AS code,o->>'title' AS title,o->>'maintenance_type' AS maintenance_type"+body+" ORDER BY row_number LIMIT 25 OFFSET :offset"),params).mappings().all()
        total=v.session.scalar(text('SELECT count(*)'+body),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[dict(r) for r in items],total=total)

    @app.post(BASE+'/preview',response_model=GenerationPreview)
    def preview(command:GenerationInput,response:Response,v=Depends(views)):
        _guard(v,*EDIT_ROLES);response.headers['Cache-Control']='private, no-store'
        return generate(v,command)[0]

    @app.post(BASE,response_model=DraftRecord,status_code=201)
    def create(command:SaveDraft,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            _lock_catalog(v)
            request_sha=digest(dict(actor=str(v.principal.user_id),command=command.model_dump(mode='json')))
            old=v.session.execute(text('SELECT draft_id,revision,request_sha256 FROM planning_draft_versions WHERE site_id=:site AND idempotency_key=:key'),
                dict(site=v.principal.site_id,key=command.idempotency_key)).mappings().first()
            if old:
                if old['request_sha256']!=request_sha: raise HTTPException(409,'Этот ключ повтора уже использован для другого запроса')
                response.status_code=200
                return metadata(get_version(v,old['draft_id'],old['revision'],full=False))
            result,snapshot,occurrences,segments=generate(v,command.input)
            if result['input_sha256']!=command.preview_sha256: raise HTTPException(409,'Исходные данные или пользователь изменились. Повторите предпросмотр')
            if not result['can_save']: raise HTTPException(422,'Не все выбранные строки готовы к генерации. Проверьте замечания предпросмотра')
            report,facts=checked(v,snapshot,occurrences,segments,capture=True)
            record=persist(v,draft_id=uuid4(),revision=1,title=command.title,reason=command.reason,snapshot=snapshot,
                sha=result['input_sha256'],occurrences=occurrences,segments=segments,report=report,resource_snapshot=facts,key=command.idempotency_key,request_sha=request_sha)
        response.headers['Cache-Control']='private, no-store'
        return record

    @app.get(BASE,response_model=DraftList)
    def listing(import_id:UUID,response:Response,offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES)
        params=dict(site=v.principal.site_id,id=import_id,offset=offset)
        rows=v.session.execute(text('''SELECT d.*,u.full_name AS author_name FROM
            (SELECT DISTINCT ON (draft_id) draft_id,revision,parent_revision,import_id,title,starts_on,ends_on,created_at,created_by,reason,input_sha256,summary
            FROM planning_draft_versions WHERE site_id=:site AND import_id=:id ORDER BY draft_id,revision DESC) d
            JOIN users u ON u.user_id=d.created_by ORDER BY d.created_at DESC,d.draft_id LIMIT 25 OFFSET :offset'''),params).mappings().all()
        total=v.session.scalar(text('SELECT count(DISTINCT draft_id) FROM planning_draft_versions WHERE site_id=:site AND import_id=:id'),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[metadata(r) for r in rows],total=total)

    @app.get(BASE+'/choices/{kind}',response_model=PlanningChoices)
    def choices(kind:str,response:Response,q:str=Query('',max_length=320),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES)
        needle='%'+q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        if kind=='workers':
            body="FROM site_memberships m JOIN users u USING(user_id) WHERE m.site_id=:site AND m.is_active AND u.is_active AND m.role IN ('executor','technician') AND u.full_name ILIKE :q"
            columns='u.user_id AS id,u.full_name AS label'
        elif kind=='skills': body='FROM skills WHERE name ILIKE :q';columns='skill_id AS id,name AS label'
        else: raise HTTPException(404,'Справочник не найден')
        params=dict(site=v.principal.site_id,q=needle,offset=offset)
        rows=v.session.execute(text('SELECT '+columns+' '+body+' ORDER BY label,id LIMIT 25 OFFSET :offset'),params).mappings().all()
        total=v.session.scalar(text('SELECT count(*) '+body),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[dict(r) for r in rows],total=total)

    @app.get(BASE+'/{identity}',response_model=DraftOverview)
    def overview(identity:UUID,response:Response,revision:int|None=Query(None,ge=1),v=Depends(views)):
        _guard(v,*READ_ROLES);row=get_version(v,identity,revision,full='overview')
        response.headers['Cache-Control']='private, no-store'
        return dict(record=metadata(row),months=row['month_summary'],validation=row['validation_snapshot'])

    @app.get(BASE+'/{identity}/versions',response_model=DraftList)
    def versions(identity:UUID,response:Response,offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);get_version(v,identity,full=False)
        params=dict(site=v.principal.site_id,id=identity,offset=offset)
        rows=v.session.execute(text('''SELECT d.draft_id,d.revision,d.parent_revision,d.import_id,d.title,d.starts_on,d.ends_on,d.created_at,d.created_by,d.reason,d.input_sha256,d.summary,u.full_name AS author_name
            FROM planning_draft_versions d JOIN users u ON u.user_id=d.created_by WHERE d.site_id=:site AND d.draft_id=:id ORDER BY revision DESC LIMIT 25 OFFSET :offset'''),params).mappings().all()
        total=v.session.scalar(text('SELECT count(*) FROM planning_draft_versions WHERE site_id=:site AND draft_id=:id'),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[metadata(r) for r in rows],total=total)

    @app.get(BASE+'/{identity}/occurrences',response_model=OccurrencePage)
    def occurrences_page(identity:UUID,response:Response,revision:int|None=Query(None,ge=1),offset:int=Query(0,ge=0,le=1000000),
        q:str=Query('',max_length=320),period:str=Query('',pattern=r'^$|^(20\d{2}|21\d{2}|2200)-(0[1-9]|1[0-2])$'),v=Depends(views)):
        _guard(v,*READ_ROLES);row=get_version(v,identity,revision,full=False)
        params=dict(site=v.principal.site_id,id=identity,revision=row['revision'],offset=offset,
            q='%'+q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        condition=" AND concat(o->>'title',' ',o->>'operation_code') ILIKE :q"
        if period:
            year,month=map(int,period.split('-'));params.update(first=date(year,month,1),last=date(year,month,monthrange(year,month)[1]))
            condition+=" AND (o->>'earliest_date')::date<=:last AND (o->>'latest_date')::date+CASE WHEN o->>'source_slot'='night' THEN 1 ELSE 0 END>=:first"
        body=" FROM planning_draft_versions d,LATERAL jsonb_array_elements(d.occurrences) o WHERE d.site_id=:site AND d.draft_id=:id AND d.revision=:revision"+condition
        rows=v.session.execute(text('SELECT o'+body+" ORDER BY o->>'latest_date',o->>'occurrence_id' LIMIT 25 OFFSET :offset"),params).scalars().all()
        total=v.session.scalar(text('SELECT count(*)'+body),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=rows,total=total)

    @app.get(BASE+'/{identity}/occurrences/{occurrence_id}/segments',response_model=SegmentPage)
    def segment_page(identity:UUID,occurrence_id:UUID,response:Response,revision:int|None=Query(None,ge=1),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);row=get_version(v,identity,revision,full=False)
        params=dict(site=v.principal.site_id,id=identity,revision=row['revision'],occurrence=str(occurrence_id),offset=offset)
        context=' FROM planning_draft_versions d,LATERAL jsonb_array_elements(d.occurrences) o WHERE d.site_id=:site AND d.draft_id=:id AND d.revision=:revision AND o->>\'occurrence_id\'=:occurrence'
        root=v.session.scalar(text('SELECT o'+context),params)
        if root is None: raise HTTPException(404,'Работа версии не найдена')
        body=" FROM planning_draft_versions d,LATERAL jsonb_array_elements(d.segments) s WHERE d.site_id=:site AND d.draft_id=:id AND d.revision=:revision AND s->>'occurrence_id'=:occurrence"
        rows=v.session.execute(text('SELECT s'+body+" ORDER BY s->>'segment_id' LIMIT 25 OFFSET :offset"),params).scalars().all()
        total=v.session.scalar(text('SELECT count(*)'+body),params)
        ids={UUID(i) for s in rows for i in s['worker_ids']}
        labels={str(r['user_id']):r['full_name'] for r in v.session.execute(text('''SELECT u.user_id,u.full_name FROM users u
            JOIN site_memberships m USING(user_id) WHERE m.site_id=:site AND u.user_id=ANY(CAST(:ids AS uuid[]))'''),dict(site=v.principal.site_id,ids=list(ids))).mappings()}
        response.headers['Cache-Control']='private, no-store'
        return dict(occurrence=root,items=rows,total=total,worker_labels=labels)

    @app.post(BASE+'/{identity}/validate',response_model=PlanValidation)
    def validate_version(identity:UUID,response:Response,revision:int|None=Query(None,ge=1),v=Depends(views)):
        _guard(v,*READ_ROLES);row=get_version(v,identity,revision)
        snapshot=row['source_snapshot'];request=GenerationInput.model_validate(snapshot['input'])
        current=source_snapshot(v,request)
        stale=digest(clean(current))!=snapshot['source_digest'] or snapshot['generator_version']!=GENERATOR_VERSION
        response.headers['Cache-Control']='private, no-store'
        return checked(v,snapshot,[WorkOccurrence.model_validate(o) for o in row['occurrences']],
            [WorkSegment.model_validate(s) for s in row['segments']],stale=stale)

    @app.post(BASE+'/{identity}/segments',response_model=DraftRecord)
    def edit(identity:UUID,command:EditSegments,response:Response,v=Depends(views)):
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            _lock_catalog(v);row=get_version(v,identity)
            if row['revision']!=command.expected_revision: raise HTTPException(409,'Версия плана изменилась; обновите её перед записью. Введённые значения не применены')
            snapshot=row['source_snapshot'];request=GenerationInput.model_validate(snapshot['input'])
            if digest(clean(source_snapshot(v,request)))!=snapshot['source_digest'] or snapshot['generator_version']!=GENERATOR_VERSION:
                raise HTTPException(409,'Источник или решение изменились; создайте новый предпросмотр с актуальными данными')
            occurrences=[WorkOccurrence.model_validate(o) for o in row['occurrences']]
            previous=[WorkSegment.model_validate(s) for s in row['segments']]
            owned={s.segment_id for s in previous if s.occurrence_id==command.occurrence_id}
            replaced=set(command.replace_segment_ids) if command.replace_segment_ids is not None else owned
            if not owned or not replaced.issubset(owned) or any(s.occurrence_id!=command.occurrence_id for s in command.segments):
                raise HTTPException(422,'Выберите сегменты только указанной работы этой версии')
            segments=[s for s in previous if s.segment_id not in replaced]+command.segments
            if len(segments)>10000 or sum(len(s.depends_on_segment_ids) for s in segments)>100000:
                raise HTTPException(422,'Превышен лимит сегментов или зависимостей версии')
            report,facts=checked(v,snapshot,occurrences,segments,previous=previous,unlock=command.unlock,capture=True)
            if report.status=='invalid':
                raise HTTPException(422,'Изменение нарушает ограничения: '+'; '.join(i.message for i in report.issues if i.code not in ('UNPLACED','QUALIFICATIONS_UNCONFIRMED','CAPACITY_UNCONFIRMED')))
            result=persist(v,draft_id=identity,revision=row['revision']+1,title=row['title'],reason=command.reason,snapshot=snapshot,
                sha=row['input_sha256'],occurrences=occurrences,segments=segments,report=report,resource_snapshot=facts)
        response.headers['Cache-Control']='private, no-store'
        return result

    @app.post(BASE+'/{identity}/placements',response_model=DraftRecord)
    def place(identity:UUID,command:LocalPlacement,response:Response,v=Depends(views)):
        _guard(v,*EDIT_ROLES)
        row=get_version(v,identity)
        segment=next((s for s in row['segments'] if s['segment_id']==str(command.segment_id)),None)
        if segment is None: raise HTTPException(404,'Сегмент не найден')
        tz=ZoneInfo(row['source_snapshot']['source']['timezone'])
        data=dict(segment,start_at=local_time(command.start_local,tz) if command.start_local else None,
            end_at=local_time(command.end_local,tz) if command.end_local else None,worker_ids=command.worker_ids,locked=command.locked)
        candidate=WorkSegment.model_validate(data)
        return edit(identity,EditSegments(expected_revision=command.expected_revision,occurrence_id=candidate.occurrence_id,
            replace_segment_ids=[candidate.segment_id],segments=[candidate],unlock=command.unlock,reason=command.reason),response,v)
