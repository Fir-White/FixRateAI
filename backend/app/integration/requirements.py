"""Read-only, scoped union of existing obligations and confirmed catalog rows."""
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from decimal import Decimal
import json
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import Depends,HTTPException,Response
from pydantic import ValidationError
from sqlalchemy import select,or_,text
from sqlalchemy.orm import joinedload
from app.schemas.requirements import RequirementsRequest,RequirementsPreview,Requirement
from app.scheduling.schemas import SchedulingBinding
from app.scheduling.generator import generate_binding_period
from app.scheduling.draft_validator import digest
from .projections import Views
from .management import PREFIX,_guard
from .catalog_imports import READ_ROLES
from .calendar import _binding_payload
from .draft_plans import generate,clean

MAX_BINDINGS=500
MAX_FACTS=20000
MAX_REQUIREMENTS=10000
BASE=PREFIX+'/planning-requirements'


def _prime(v,table,*keys,where=(),options=()):
    cls=v.models[table]
    query=select(cls).where(*where).options(*options)
    if hasattr(cls,'site_id'):query=query.where(cls.site_id==v.principal.site_id)
    rows=v.session.scalars(query.limit(MAX_FACTS+1)).all()
    if len(rows)>MAX_FACTS:raise HTTPException(422,'Слишком много исходных фактов; сократите выбранный состав')
    v._read_rows[table]=rows
    for key in keys:
        index=defaultdict(list)
        for row in rows:index[getattr(row,key)].append(row)
        v._task_rows[table,key]=index
    return rows


def _rules(v,request,now):
    """A private filtered Views snapshot; no per-binding SQL or writer caching."""
    reader=Views(v.session,v.models,v.principal)
    b=v.models['rule_equipment'];r=v.models['maintenance_rules'];e=v.models['equipment'];edition=v.models['regulation_editions']
    query=select(b.binding_id).join(r,b.maintenance_rule_id==r.maintenance_rule_id).join(e,b.equipment_id==e.equipment_id).join(edition,r.regulation_edition_id==edition.regulation_edition_id)
    query=query.where(b.site_id==v.principal.site_id,r.site_id==v.principal.site_id,e.site_id==v.principal.site_id,
        edition.site_id==v.principal.site_id,r.schedule_parameters['catalog_publication_id'].astext.is_(None))
    if request.binding_ids:query=query.where(b.binding_id.in_(request.binding_ids))
    else:
        query=query.where(e.status!='retired',r.publication_status!='archived',b.valid_from<=request.ends_on,r.active_from<=request.ends_on,edition.effective_from<=request.ends_on)
        for column in (b.valid_to,r.active_until,edition.effective_to):query=query.where(or_(column.is_(None),column>=request.starts_on))
    ids=list(v.session.scalars(query.order_by(b.binding_id).limit(MAX_BINDINGS+1)))
    if len(ids)>MAX_BINDINGS:raise HTTPException(422,'В составе больше 500 привязок; выберите меньший состав')
    if request.binding_ids and set(ids)!=set(request.binding_ids):raise HTTPException(404,'Часть выбранных привязок недоступна в этом объекте')
    bindings=_prime(reader,'rule_equipment','binding_id','equipment_id',where=(b.binding_id.in_(ids),),
        options=(joinedload(b.rule).joinedload(r.operation),joinedload(b.rule).joinedload(r.edition),joinedload(b.equipment)))
    assets={x.equipment_id for x in bindings};operations={x.rule.operation_template_id for x in bindings}
    check=v.models['checklist_templates'];typ=v.models['maintenance_types']
    _prime(reader,'checklist_templates','operation_template_id',where=(check.operation_template_id.in_(operations),))
    skill=v.models['rule_required_skills']
    _prime(reader,'rule_required_skills','maintenance_rule_id',where=(skill.maintenance_rule_id.in_({x.maintenance_rule_id for x in bindings}),))
    _prime(reader,'maintenance_types','maintenance_type_id',where=(typ.maintenance_type_id.in_({x.rule.operation.maintenance_type_id for x in bindings}),))
    _prime(reader,'sites','site_id')
    # Accepted history stays linked to equipment + operation, including old rule
    # versions. Future/unaccepted reviews cannot advance a rolling due date.
    order=v.models['work_orders'];link=v.models['work_order_equipment'];review=v.models['acceptance_reviews']
    past=select(order.work_order_id).join(link,link.work_order_id==order.work_order_id).join(r,r.maintenance_rule_id==order.maintenance_rule_id).join(review,review.work_order_id==order.work_order_id)
    past=past.where(order.site_id==v.principal.site_id,link.site_id==v.principal.site_id,r.site_id==v.principal.site_id,review.site_id==v.principal.site_id,
        link.equipment_id.in_(assets),r.operation_template_id.in_(operations),order.completed_at.is_not(None),review.decision=='accepted',review.reviewed_at<=now).distinct()
    orders=_prime(reader,'work_orders','work_order_id',where=(order.work_order_id.in_(past),))
    past_ids={x.work_order_id for x in orders}
    _prime(reader,'work_order_equipment','equipment_id',where=(link.work_order_id.in_(past_ids),link.equipment_id.in_(assets)))
    _prime(reader,'acceptance_reviews','work_order_id',where=(review.work_order_id.in_(past_ids),review.decision=='accepted',review.reviewed_at<=now))
    _prime(reader,'maintenance_rules','maintenance_rule_id',where=(r.maintenance_rule_id.in_({x.maintenance_rule_id for x in orders}),))
    # Existing entries are matched by original obligation date, never by a
    # moved planned date. Cancelled or ambiguous entries require human review.
    existing=v.session.execute(text('''SELECT s.binding_id,b.equipment_id,p.operation_template_id,s.source_date,s.regulatory_deadline_on,s.maintenance_rule_id,s.schedule_entry_id,s.status AS entry_status,
        o.work_order_id,o.status AS order_status,EXISTS(SELECT 1 FROM acceptance_reviews a WHERE a.site_id=s.site_id
            AND a.work_order_id=o.work_order_id AND a.decision='accepted' AND a.reviewed_at<=:now) AS accepted
        FROM schedule_entries s LEFT JOIN work_orders o ON o.site_id=s.site_id AND o.schedule_entry_id=s.schedule_entry_id
        JOIN maintenance_rules p ON p.site_id=s.site_id AND p.maintenance_rule_id=s.maintenance_rule_id
        LEFT JOIN rule_equipment b ON b.site_id=s.site_id AND b.binding_id=s.binding_id
        WHERE s.site_id=:site AND (s.binding_id=ANY(CAST(:ids AS uuid[]))
            OR (b.equipment_id=ANY(CAST(:assets AS uuid[])) AND p.operation_template_id=ANY(CAST(:ops AS uuid[]))))
        ORDER BY s.schedule_entry_id,o.work_order_id LIMIT :limit'''),dict(site=v.principal.site_id,ids=ids,assets=list(assets),ops=list(operations),now=now,limit=MAX_FACTS+1)).mappings().all()
    if len(existing)>MAX_FACTS:raise HTTPException(422,'Слишком много сохранённых обязательств; сократите состав')
    indexed=defaultdict(list)
    for row in existing:
        day=row['source_date'] or row['regulatory_deadline_on']
        indexed[row['binding_id'],day].append(dict(row))
        indexed['asset',row['equipment_id'],row['operation_template_id'],day].append(dict(row))
    facts={table:[{c.name:getattr(row,c.name) for c in row.__table__.columns} for row in rows] for table,rows in reader._read_rows.items()}
    facts['bindings']=[dict(binding={c.name:getattr(x,c.name) for c in x.__table__.columns},rule={c.name:getattr(x.rule,c.name) for c in x.rule.__table__.columns},
        operation={c.name:getattr(x.rule.operation,c.name) for c in x.rule.operation.__table__.columns},edition={c.name:getattr(x.rule.edition,c.name) for c in x.rule.edition.__table__.columns},
        equipment={c.name:getattr(x.equipment,c.name) for c in x.equipment.__table__.columns}) for x in bindings]
    facts['existing']=list(map(dict,existing))
    return reader,bindings,indexed,facts


def _existing(rows,rule_id=None,*,catalog=False):
    if not rows:return 'new',[],[]
    tasks=sorted({r['work_order_id'] for r in rows if r['work_order_id']},key=str)
    if (not tasks or any(r['entry_status']!='planned' or r['order_status'] in (None,'cancelled') for r in rows)
        or not catalog and (len({r['schedule_entry_id'] for r in rows})!=1 or len(tasks)!=1 or any(r['maintenance_rule_id']!=rule_id for r in rows))):
        return 'review',tasks,['EXISTING_OCCURRENCE_REVIEW']
    if all(r['order_status']=='completed' and r['accepted'] for r in rows):return 'fulfilled',tasks,[]
    if any(r['order_status']=='completed' and not r['accepted'] for r in rows):return 'review',tasks,['COMPLETION_NOT_ACCEPTED']
    return 'existing',tasks,[]


def preview(v,request,now=None):
    now=now or datetime.now(timezone.utc);site=v.one('sites',site_id=v.principal.site_id);tz=ZoneInfo(site.timezone)
    items=[];issues=[];facts={};binding_count=0;source_labels={}
    def issue(kind,code,message,**ref):
        ref.setdefault('source_label',source_labels.get(ref.get('binding_id'),''))
        issues.append(dict(source_kind=kind,code=code,message=message,**ref))
    if request.include_regulations:
        reader,bindings,existing,facts=_rules(v,request,now);binding_count=len(bindings)
        if not bindings:issue('regulation','NO_REGULATION_BINDINGS','Для этого периода не найдены привязки регламентов; проверьте настройки обслуживания оборудования')
        for binding in bindings:
            rule=binding.rule;asset=binding.equipment;op=rule.operation
            source_labels[binding.binding_id]=f"{asset.name} · {rule.schedule_parameters.get('operation_metadata',{}).get('code',op.code)}"
            if not op.is_active or asset.status=='retired' or rule.publication_status=='archived':
                issue('regulation','SOURCE_INACTIVE','Выбранная привязка, операция или оборудование не действуют',binding_id=binding.binding_id);continue
            if rule.publication_status!='published' or not rule.edition.is_approved:
                issue('regulation','RULE_UNCONFIRMED','Утвердите регламент и его редакцию перед расчётом',binding_id=binding.binding_id);continue
            try:
                payload,code,message=_binding_payload(reader,binding,rule,asset,site)
                if payload is None:
                    issue('regulation',code,message,binding_id=binding.binding_id);continue
                parsed=SchedulingBinding.model_validate_json(json.dumps(payload,default=str))
                results=generate_binding_period(parsed,request.starts_on,request.ends_on,now,tz)
            except (ValidationError,ValueError,OverflowError):
                issue('regulation','INVALID_PERSISTED_INPUT','Параметры регламента противоречат контракту; уточните даты, единицы и историю',binding_id=binding.binding_id);continue
            for result in results:
                if result.status in ('needs_input','manual_review'):
                    text_message=result.explanation
                    if result.next_due_date:text_message+=f' Следующий обязательный срок: {result.next_due_date}.'
                    issue('regulation',result.error_code or 'RULE_REVIEW_REQUIRED',text_message,binding_id=binding.binding_id)
                for warning in result.warnings:
                    if warning in ('NORM_UNIT_UNCONFIRMED','NORM_VALUE_MISSING','DURATION_UNCONFIRMED','EQUIPMENT_OUT_OF_SERVICE'):
                        issue('regulation',warning,{'NORM_UNIT_UNCONFIRMED':'Подтвердите единицу нормы','NORM_VALUE_MISSING':'Укажите подтверждённую трудоёмкость','DURATION_UNCONFIRMED':'Подтвердите длительность выполнения','EQUIPMENT_OUT_OF_SERVICE':'Оборудование находится в ремонте'}[warning],binding_id=binding.binding_id)
                for generated in result.occurrences:
                    o=generated.occurrence;source_day=o.source_date or o.occurrence_date
                    saved=existing.get((binding.binding_id,source_day)) or existing.get(('asset',asset.equipment_id,op.operation_template_id,source_day),[])
                    state,tasks,flags=_existing(saved,rule.maintenance_rule_id)
                    flags+=list(result.warnings)
                    if generated.deadline_passed and state!='fulfilled':flags.append('OVERDUE_REQUIRES_REVIEW')
                    informational={'ROLLING_NEXT_OCCURRENCE_ONLY','SYNTHETIC_DATA','HISTORY_AFTER_CUTOFF_IGNORED'}
                    if state!='fulfilled' and (any(f not in informational for f in flags) or result.status=='manual_review'):state='review'
                    items.append(Requirement(requirement_id=o.occurrence_id,source_kind='regulation',binding_id=binding.binding_id,
                        rule_id=rule.maintenance_rule_id,regulation_id=rule.regulation_edition_id,source_revision=rule.rule_version,
                        source_ref=rule.source_ref,equipment_ids=[asset.equipment_id],equipment_labels=[asset.name],
                        operation_code=parsed.operation.code,title=parsed.operation.title,maintenance_type=parsed.operation.maintenance_type,
                        source_date=o.source_date or o.occurrence_date,earliest_date=o.earliest_date,due_date=o.mandatory_due_date,
                        person_hours=generated.required_person_hours,crew_size=parsed.operation.crew_size,qualification_ids=parsed.operation.qualification_ids,
                        state=state,task_ids=tasks,explanation=generated.explanation,issues=sorted(set(flags)),synthetic=parsed.equipment.data_origin=='synthetic_demo'))
                    if len(items)>MAX_REQUIREMENTS:raise HTTPException(422,'В составе больше 10000 обязательств; сократите горизонт')
    if request.catalog:
        _,snapshot,roots,_,catalog_issues=generate(v,request.catalog,capture_issues=True);facts['catalog']=snapshot
        source=snapshot['source'];assets=source['equipment']
        keys_by_root={str(r.occurrence_id):{digest(dict(source_sha=r.source_sha256,row=n,source_date=r.source_date,slot=r.source_slot,asset=str(a)))
            for n in [r.source_row,*r.included_rows] for a in r.equipment_ids} for r in roots}
        keys=set().union(*keys_by_root.values()) if keys_by_root else set()
        if len(keys)>MAX_FACTS:raise HTTPException(422,'Слишком много исходных событий; сократите выбранный состав')
        saved=v.session.execute(text('''SELECT k.obligation_key,t.occurrence_id,o.work_order_id,o.status AS order_status,s.status AS entry_status,
            EXISTS(SELECT 1 FROM acceptance_reviews a WHERE a.site_id=t.site_id AND a.work_order_id=o.work_order_id
                AND a.decision='accepted' AND a.reviewed_at<=:now) AS accepted
            FROM published_catalog_obligations k JOIN published_catalog_tasks t ON t.site_id=k.site_id AND t.publication_id=k.publication_id AND t.occurrence_id=k.occurrence_id
            JOIN work_orders o ON o.site_id=t.site_id AND o.work_order_id=t.work_order_id
            JOIN schedule_entries s ON s.site_id=o.site_id AND s.schedule_entry_id=o.schedule_entry_id
            WHERE t.site_id=:site AND k.obligation_key=ANY(CAST(:ids AS text[]))
                AND EXISTS(SELECT 1 FROM work_order_equipment l WHERE l.site_id=t.site_id AND l.work_order_id=t.work_order_id AND l.equipment_id=k.equipment_id)
            ORDER BY k.obligation_key,t.item_id LIMIT :limit'''),
            dict(site=v.principal.site_id,ids=list(keys),now=now,limit=MAX_FACTS+1)).mappings().all()
        if len(saved)>MAX_FACTS:raise HTTPException(422,'Слишком много сохранённых каталожных заданий')
        by_key=defaultdict(list)
        for row in saved:by_key[row['obligation_key']].append(dict(row))
        facts['catalog_tasks']=list(map(dict,saved))
        # Reuse catalog diagnostics without reinterpreting marks, units or hours.
        for row in catalog_issues:issue('catalog',row['code'],row['message'],import_id=request.catalog.import_id,source_row=row['row_number'])
        for root in roots:
            root_keys=keys_by_root[str(root.occurrence_id)];matched=[key for key in root_keys if key in by_key]
            state,tasks,flags=_existing([row for key in matched for row in by_key[key]],catalog=True)
            if matched and len(matched)!=len(root_keys):state='review';flags.append('PARTIAL_ALREADY_PUBLISHED')
            if root.latest_date<now.astimezone(tz).date() and state!='fulfilled':state='review';flags.append('OVERDUE_REQUIRES_REVIEW')
            items.append(Requirement(requirement_id=root.occurrence_id,source_kind='catalog',import_id=root.import_id,source_row=root.source_row,
                source_revision=root.decision_revision,source_ref=f'Excel {root.source_sha256}: '+', '.join(root.source_cells),
                equipment_ids=root.equipment_ids,equipment_labels=[assets[str(a)]['name'] for a in root.equipment_ids],operation_code=root.operation_code,
                title=root.title,maintenance_type=root.maintenance_type,source_date=root.source_date,source_slot=root.source_slot,earliest_date=root.earliest_date,due_date=root.latest_date,
                allowed_intervals=[w.model_dump(mode='json') for w in root.allowed_intervals],person_hours=root.total_person_hours,crew_size=root.crew_size,
                qualification_ids=root.qualification_ids,state=state,task_ids=tasks,explanation=root.policy_note,issues=flags,
                synthetic=any(assets[str(a)]['data_origin']=='synthetic_demo' for a in root.equipment_ids)))
    if len(items)>MAX_REQUIREMENTS:raise HTTPException(422,'В составе больше 10000 обязательств; сократите горизонт')
    overlaps=defaultdict(list)
    for item in items:
        for asset in item.equipment_ids:overlaps[asset,item.operation_code.casefold(),item.source_date].append(item)
    for group in overlaps.values():
        if len({item.source_kind for item in group})<2:continue
        issue('regulation','SOURCE_EQUIVALENCE_REQUIRED','Одинаковый код и дата на одном оборудовании в разных источниках: подтвердите сопоставление; часы не объединены автоматически')
        for item in group:
            if item.state not in ('existing','fulfilled'):item.state='review'
            if 'SOURCE_EQUIVALENCE_REQUIRED' not in item.issues:item.issues.append('SOURCE_EQUIVALENCE_REQUIRED')
    items.sort(key=lambda x:(x.due_date,x.source_kind,str(x.requirement_id)))
    counts=Counter(x.state for x in items);sources=Counter(x.source_kind for x in items)
    unknown=sum(x.person_hours is None for x in items);known=sum((x.person_hours for x in items if x.person_hours is not None),Decimal(0))
    complete=not issues and not unknown and not counts['review']
    months=defaultdict(lambda:dict(known_person_hours=Decimal(0),requirements=0,unknown_hours_count=0))
    for x in items:
        month=months[x.due_date.strftime('%Y-%m')];month['requirements']+=1
        if x.person_hours is None:month['unknown_hours_count']+=1
        else:month['known_person_hours']+=x.person_hours
    summary=dict(total=len(items),known_person_hours=known,total_person_hours=known if complete else None,
        new_person_hours=sum((x.person_hours for x in items if x.state=='new'),Decimal(0)) if complete else None,
        unknown_hours_count=unknown,state_counts=dict(counts),source_counts=dict(sources),binding_count=binding_count,
        selected_catalog_rows=len(request.catalog.row_numbers) if request.catalog else 0,
        unselected_catalog_rows=source['operation_count']-len(request.catalog.row_numbers) if request.catalog else 0,complete=complete)
    needle=request.q.casefold();filtered=[x for x in items if (request.state=='all' or x.state==request.state)
        and (not needle or needle in ' '.join([x.operation_code,x.title,*x.equipment_labels]).casefold())]
    for rows in facts.values():
        if isinstance(rows,list):rows.sort(key=lambda value:digest(clean(value)))
    normalized=request.model_dump(mode='json',exclude={'q','state','offset','issue_offset'})
    normalized['binding_ids'].sort()
    if normalized['catalog']:normalized['catalog']['row_numbers'].sort()
    return dict(starts_on=request.starts_on,ends_on=request.ends_on,timezone=site.timezone,calculated_at=now,
        source_sha256=digest(dict(input=normalized,facts=clean(facts),day=now.astimezone(tz).date())),summary=summary,
        months=[dict(month=k,**v) for k,v in sorted(months.items())],items=filtered[request.offset:request.offset+25],total=len(filtered),
        issues=issues[request.issue_offset:request.issue_offset+25],total_issues=len(issues))


def register_routes(app,views):
    @app.post(BASE+'/preview',response_model=RequirementsPreview)
    def requirements_preview(command:RequirementsRequest,response:Response,v=Depends(views)):
        _guard(v,*READ_ROLES)
        response.headers['Cache-Control']='private, no-store'
        return preview(v,command)
