"""Approval gateway: immutable additions, exact consent and atomic live writes."""
from datetime import datetime,timedelta,timezone,time
from decimal import Decimal
from hashlib import sha256
from uuid import UUID,uuid4,uuid5
from zoneinfo import ZoneInfo
import json
from fastapi import Depends,HTTPException,Query,Response
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from app.schemas.publication import (PreparePublication,PublicationDecision,PublishApproved,
    PublicationProposal,PublicationProposalList,PublicationChangePage,PublicationProfileChoices,PreparePortfolioPublication,RegulationPublicationChoices)
from app.schemas.draft_plans import WorkOccurrence,WorkSegment
from app.schemas.portfolio import planning_input,PortfolioInput
from app.scheduling.publication import additions
from app.scheduling.draft_validator import digest
from .draft_plans import BASE,EDIT_ROLES,get_version,source_snapshot,clean,checked,_lock_catalog
from .catalog_imports import READ_ROLES
from .management import _guard,_edit,_audit
from .assignments import _lock

PATH='/api/v1/maintenance/publication-proposals'
PUBLIC='proposal_id,draft_id,base_revision,state,created_by,created_at,expires_at,reason,scope_note,proposal_digest,summary,validation_snapshot,blockers,blocker_count,decided_by,decided_at,decision_reason,approval_token,published_at,publication_id'


def _origin(asset):
    return asset.get('data_origin',asset.get('properties',{}).get('data_origin'))


def get(v,identity,*,full=False,lock=False):
    row=v.session.execute(text('SELECT '+('*' if full else PUBLIC+", input_snapshot->'policy' AS planning_policy")+' FROM draft_publication_proposals WHERE site_id=:site AND proposal_id=:id'+(' FOR UPDATE' if lock else '')),
        dict(site=v.principal.site_id,id=identity)).mappings().first()
    if not row:raise HTTPException(404,'Предложение не найдено')
    return dict(row)


def public(row):
    value={k:row.get(k) for k in PUBLIC.split(',') if k!='validation_snapshot'}
    value['validation']=row['validation_snapshot']
    value['planning_policy']=row.get('planning_policy') or row.get('input_snapshot',{}).get('policy')
    value['can_approve']=row['blocker_count']==0 and row['state']=='prepared' and row['expires_at']>datetime.now(timezone.utc)
    return value


def conflicts(v,keys):
    if not keys:return []
    return list(v.session.scalars(text('SELECT obligation_key FROM published_catalog_obligations WHERE site_id=:site AND obligation_key=ANY(CAST(:keys AS text[]))'),
        dict(site=v.principal.site_id,keys=[k['key'] for k in keys])))


def consent_digest(row):
    return digest(dict(site=str(row['site_id']),draft=str(row['draft_id']),revision=row['base_revision'],proposal=str(row['proposal_id']),
        source=row['source_digest'],resources=row['resource_digest'],items=row['items'],keys=row['obligation_keys'],expires=row['expires_at'].astimezone(timezone.utc).isoformat(),
        scope=row['scope_note'],reason=row['reason'],summary=row['summary'],input_digest=digest(row['input_snapshot']),
        validation=row['validation_snapshot'],blockers=row['blockers'],blocker_count=row['blocker_count']))


def fresh(v,row):
    if consent_digest(row)!=row['proposal_digest']:raise HTTPException(409,'PLAN_STALE: состав предложения изменён; требуется новое предложение')
    if row['expires_at']<=datetime.now(timezone.utc):raise HTTPException(409,'PLAN_STALE: срок предложения истёк; подготовьте новое')
    draft=get_version(v,row['draft_id'])
    if draft['revision']!=row['base_revision']:raise HTTPException(409,'PLAN_STALE: версия черновика изменилась')
    snapshot=draft['source_snapshot'];generation=planning_input(snapshot['input'])
    if digest(clean(source_snapshot(v,generation)))!=row['source_digest']:raise HTTPException(409,'PLAN_STALE: источник или оборудование изменились')
    roots=[WorkOccurrence.model_validate(o) for o in draft['occurrences']]
    segments=[WorkSegment.model_validate(s) for s in draft['segments']]
    report,facts=checked(v,snapshot,roots,segments,capture=True)
    if report.status!='valid' or report.resource_sha256!=row['resource_digest']:raise HTTPException(409,'PLAN_STALE: доступность, допуски или занятость изменились; нужна новая проверка')
    if conflicts(v,row['obligation_keys']):raise HTTPException(409,'PLAN_STALE: часть обязательств уже опубликована. Повторная выдача запрещена')
    return draft,roots,segments,facts


def lock_facts(v,row):
    snapshot=row['input_snapshot'];assets={UUID(a) for item in row['items'] for a in item['equipment_ids']}
    _lock_catalog(v)
    planning_key=int.from_bytes(sha256(f'{v.principal.site_id}:planning'.encode()).digest()[:8],'big',signed=True)
    v.session.execute(text('SELECT pg_advisory_xact_lock(:key)'),dict(key=planning_key))
    _lock(v,'sites',read=True,site_id=v.principal.site_id)
    _lock(v,'equipment',equipment_id=assets)
    regulation_items=[i for i in row['items'] if i.get('source_kind')=='regulation']
    if regulation_items:
        rules={UUID(i['execution']['rule_id']) for i in regulation_items}
        bindings={UUID(i['execution']['binding_id']) for i in regulation_items}
        editions={UUID(i['execution']['regulation_id']) for i in regulation_items}
        operations={UUID(f['operation']['operation_template_id']) for f in snapshot['source']['facts']['bindings'] if UUID(f['rule']['maintenance_rule_id']) in rules}
        _lock(v,'maintenance_rules',read=True,maintenance_rule_id=rules)
        _lock(v,'regulation_editions',read=True,regulation_edition_id=editions)
        _lock(v,'operation_templates',read=True,operation_template_id=operations)
        _lock(v,'rule_equipment',read=True,binding_id=bindings)
        _lock(v,'checklist_templates',read=True,checklist_template_id={UUID(c) for i in regulation_items for c in i['execution']['checklist_ids']})
        _lock(v,'rule_required_skills',read=True,maintenance_rule_id=rules)
    systems={UUID(snapshot['source']['equipment'][str(a)]['system_id']) for a in assets}
    system_rows=_lock(v,'engineering_systems',read=True,system_id=systems)
    workers={UUID(w) for item in row['items'] for w in item['worker_ids']}
    for table in ('availability_slots','employee_shift_rules','user_skills'):_lock(v,table,read=True,user_id=workers)
    skills={UUID(s) for root in snapshot['occurrences'] for s in root['qualification_ids']}
    if skills:_lock(v,'skills',read=True,skill_id=skills)
    if not v.one('sites').is_active or len(system_rows)!=len(systems) or any(not s.is_active for s in system_rows):
        raise HTTPException(409,'Объект или инженерная система отключены')


def prepare(v,identity,command):
    request_sha=digest(dict(actor=str(v.principal.user_id),draft_id=str(identity),command=command.model_dump(mode='json')))
    old=v.session.execute(text('SELECT '+PUBLIC+",request_sha256,input_snapshot->'policy' AS planning_policy FROM draft_publication_proposals WHERE site_id=:site AND idempotency_key=:key"),dict(site=v.principal.site_id,key=command.idempotency_key)).mappings().first()
    if old:
        if old['request_sha256']!=request_sha:raise HTTPException(409,'Ключ повтора использован с другими параметрами')
        return public(old)
    active=v.session.scalar(text("SELECT count(*) FROM draft_publication_proposals WHERE site_id=:site AND draft_id=:id AND state IN ('prepared','approved') AND expires_at>now()"),dict(site=v.principal.site_id,id=identity))
    if active>=10:raise HTTPException(429,'У черновика уже 10 действующих предложений. Сначала отклоните лишние или дождитесь истечения их срока')
    draft=get_version(v,identity)
    if (draft['import_id'] is None)!=isinstance(command,PreparePortfolioPublication):raise HTTPException(422,'Используйте подтверждение для соответствующего типа плана')
    if draft['revision']!=command.expected_revision:raise HTTPException(409,'Версия изменилась; откройте актуальную')
    snapshot=draft['source_snapshot'];generation=planning_input(snapshot['input'])
    current=clean(source_snapshot(v,generation))
    if digest(current)!=snapshot['source_digest']:raise HTTPException(409,'Источник изменился; нужен актуальный черновик')
    roots=[WorkOccurrence.model_validate(o) for o in draft['occurrences']];segments=[WorkSegment.model_validate(s) for s in draft['segments']]
    if not segments or len(segments)>500:raise HTTPException(422,'Для публикации выберите от 1 до 500 сегментов')
    numbers={r.source_row for r in roots if r.source_kind=='catalog'}
    if {p.row_number for p in command.profiles}!=numbers:raise HTTPException(422,'Нужны инструкции, безопасность и чек-листы для каждой корневой строки выбранного состава')
    report,facts=checked(v,snapshot,roots,segments,capture=True)
    regulations,operations=({}, {})
    if isinstance(command,PreparePortfolioPublication):
        from .regulation_publication import profiles as regulation_profiles
        regulations,operations=regulation_profiles(current,roots,command.regulations)
    items,keys=additions(roots,segments,command.profiles,regulations=regulations,regulation_operations=operations)
    root_index={str(r.occurrence_id):r for r in roots};segment_index={str(s.segment_id):s for s in segments}
    blockers=[i.model_dump(mode='json') for i in report.issues];count=report.total_issues
    def block(code,message):
        nonlocal count
        count+=1
        if len(blockers)<25:blockers.append(dict(code=code,message=message))
    if len({k['key'] for k in keys})!=len(keys):block('DUPLICATE_OBLIGATION','Одно обязательство включено в состав несколько раз; уточните пересекающиеся привязки регламентов')
    if conflicts(v,keys):block('ALREADY_PUBLISHED','Эти исходные обязательства уже выданы. Автоматическое дублирование или замена действующих заданий запрещены')
    active_systems={str(s.system_id) for s in v.rows('engineering_systems') if s.is_active}
    for item in items:
        root=root_index[item['occurrence_id']]
        parts=[segment_index[sid] for sid in item['segment_ids']]
        if root.interpretation=='CONTINUOUS_WORK' and len({tuple(sorted(map(str,s.equipment_ids))) for s in parts})>1:
            block('CONTINUOUS_ASSET_SCOPE','Непрерывное задание требует одинакового состава оборудования во всех частях')
        assets=[current['equipment'][a] for a in item['equipment_ids']]
        if len(assets)>1 and any(c['photo_required'] for c in item['execution']['checklist']):
            block('MULTI_ASSET_PHOTO','Для фотофиксации подготовьте отдельное задание на каждую единицу оборудования, сохранив нормативный объём')
        if len({a['system_id'] for a in assets})!=1:block('CROSS_SYSTEM_SEGMENT','Разделите сегмент на отдельные инженерные системы до публикации')
        if any(str(a['system_id']) not in active_systems for a in assets):block('SYSTEM_INACTIVE','Инженерная система отключена')
        if len({_origin(a) for a in assets})!=1 or any(_origin(a) not in ('customer','synthetic_demo') for a in assets):block('ORIGIN_UNCONFIRMED','Происхождение активов сегмента должно быть единым и подтверждённым')
        if item['start_at'] and (any(d.second or d.microsecond for d in (item['start_at'],item['end_at'])) or item['end_at']-item['start_at']>timedelta(days=32)):
            block('TASK_INTERVAL_UNSUPPORTED','Задание требует целых минут и длительности не более 32 суток')
        if Decimal(item['person_hours'])>=Decimal('1000000000'):block('TASK_HOURS_LIMIT','Объём задания превышает точность рабочего журнала')
    now=datetime.now(timezone.utc);identity_proposal=uuid4();expires=now+timedelta(minutes=30)
    summary=dict(added_tasks=len(items),changed_tasks=0,cancelled_tasks=0,occurrences=len(roots),segments=len(segments),
        total_person_hours=str(report.total_person_hours),selected_rows=len(generation.row_numbers),
        unselected_rows=current['summary']['unselected_catalog_rows'] if isinstance(generation,PortfolioInput) else current['operation_count']-len(generation.row_numbers),
        months=sorted({i['start_at'].astimezone(ZoneInfo(current['timezone'])).strftime('%Y-%m') for i in items if i['start_at']}))
    if isinstance(generation,PortfolioInput):summary['regulation_occurrences']=sum(r.source_kind=='regulation' for r in roots)
    private=clean(dict(source=current,occurrences=draft['occurrences'],segments=draft['segments'],resources=facts,policy=generation.policy.model_dump(mode='json')))
    items=clean(items)
    consent=consent_digest(dict(site_id=v.principal.site_id,draft_id=identity,base_revision=draft['revision'],proposal_id=identity_proposal,
        source_digest=snapshot['source_digest'],resource_digest=report.resource_sha256,items=items,obligation_keys=keys,expires_at=expires,
        scope_note=command.scope_note,reason=command.reason,summary=summary,input_snapshot=private,
        validation_snapshot=report.model_dump(mode='json'),blockers=blockers,blocker_count=count))
    if len(json.dumps(private).encode())+len(json.dumps(items).encode())>24*1024*1024:raise HTTPException(422,'Предложение превышает 24 МиБ; сократите состав')
    v.session.execute(text('''INSERT INTO draft_publication_proposals
        (proposal_id,site_id,draft_id,base_revision,created_by,created_at,expires_at,reason,scope_note,proposal_digest,
         source_digest,resource_digest,input_snapshot,items,obligation_keys,summary,validation_snapshot,blockers,blocker_count,idempotency_key,request_sha256)
        VALUES (:id,:site,:draft,:revision,:actor,:now,:expires,:reason,:scope,:digest,:source,:resources,
          CAST(:input AS jsonb),CAST(:items AS jsonb),CAST(:keys AS jsonb),CAST(:summary AS jsonb),CAST(:validation AS jsonb),CAST(:blockers AS jsonb),:count,:key,:request)'''),
        dict(id=identity_proposal,site=v.principal.site_id,draft=identity,revision=draft['revision'],actor=v.principal.user_id,now=now,expires=expires,
            reason=command.reason,scope=command.scope_note,digest=consent,source=snapshot['source_digest'],resources=report.resource_sha256,
            input=json.dumps(private),items=json.dumps(items),keys=json.dumps(keys),summary=json.dumps(summary),validation=report.model_dump_json(),
            blockers=json.dumps(blockers),count=count,key=command.idempotency_key,request=request_sha))
    _audit(v,'draft_publication_proposals',identity_proposal,'prepare',dict(digest=consent,revision=draft['revision'],blockers=count))
    return public(get(v,identity_proposal))


def materialize(v,proposal,publication_id,roots,segments,facts,*,title):
    """Create finite, explicitly approved rules and tasks, with no recurrence invention."""
    site=v.principal.site_id;actor=v.principal.user_id;tz=ZoneInfo(v.principal.timezone);now=datetime.now(timezone.utc)
    source=proposal['input_snapshot']['source'];by_root={str(r.occurrence_id):r for r in roots};by_segment={str(s.segment_id):s for s in segments}
    catalog_roots=[r for r in roots if r.source_kind=='catalog']
    if catalog_roots:
        document=v.repo.add('regulation_documents',site_id=site,title='План обслуживания: '+title,source_kind='internal',
            source_uri='/api/v1/maintenance/catalog-imports/'+str(catalog_roots[0].import_id)+'/source',external_reference=proposal['scope_note'])
        edition=v.repo.add('regulation_editions',site_id=site,regulation_document_id=document.regulation_document_id,edition_code=f'План v{proposal["base_revision"]}',
            effective_from=min(r.earliest_date for r in catalog_roots),effective_to=max(r.latest_date+timedelta(days=r.source_slot=='night') for r in catalog_roots),
            source_sha256=catalog_roots[0].source_sha256,is_approved=True,approved_by=actor)
    plans={};types={t.name:t.maintenance_type_id for t in v.rows('maintenance_types')}
    created=[];people={w['worker_id']:w for w in facts['workers']}
    tasks_by_segment={sid:uuid5(publication_id,item['item_id']) for item in proposal['items'] for sid in item['segment_ids']}
    notifications=[]
    from sqlalchemy import select
    rule_cls=v.models['maintenance_rules'];binding_cls=v.models['rule_equipment']
    rule_ids={r.rule_id for r in roots if r.source_kind=='regulation'}
    binding_ids={r.binding_id for r in roots if r.source_kind=='regulation'}
    actual_rules={r.maintenance_rule_id:r for r in v.session.scalars(select(rule_cls).where(rule_cls.site_id==site,rule_cls.maintenance_rule_id.in_(rule_ids)))}
    actual_bindings={r.binding_id:r for r in v.session.scalars(select(binding_cls).where(binding_cls.site_id==site,binding_cls.binding_id.in_(binding_ids)))}
    sequence={(r['schedule_plan_id'],r['binding_id'],r['planned_date']):r['sequence_no'] for r in v.session.execute(text('''SELECT schedule_plan_id,binding_id,planned_date,max(sequence_no) AS sequence_no
        FROM schedule_entries WHERE site_id=:site AND binding_id=ANY(CAST(:ids AS uuid[])) GROUP BY schedule_plan_id,binding_id,planned_date'''),dict(site=site,ids=list(binding_ids))).mappings()} if binding_ids else {}
    for item in proposal['items']:
        root=by_root[item['occurrence_id']];profile=item['execution'];a=datetime.fromisoformat(item['start_at']);b=datetime.fromisoformat(item['end_at'])
        local=a.astimezone(tz);period=(local.year,local.month);assets=[source['equipment'][i] for i in item['equipment_ids']]
        system=UUID(assets[0]['system_id']);origin=_origin(assets[0])
        if period not in plans:
            approved=v.rows('schedule_plans',period_year=period[0],period_month=period[1],status='approved')
            if approved:plans[period]=approved[0]
        if period not in plans:
            # Shared with the legacy monthly generator: reserve revision under the site planning lock.
            revision=v.session.scalar(text('SELECT coalesce(max(revision),0)+1 FROM schedule_plans WHERE site_id=:site AND period_year=:year AND period_month=:month'),dict(site=site,year=period[0],month=period[1]))
            plans[period]=v.repo.add('schedule_plans',site_id=site,period_year=period[0],period_month=period[1],revision=revision,status='approved',
                created_by=actor,approved_by=proposal['decided_by'],approved_at=proposal['decided_at'],
                source_snapshot=dict(catalog_publication_id=str(publication_id),proposal_digest=proposal['proposal_digest'],draft_id=str(proposal['draft_id']),revision=proposal['base_revision']))
        if root.maintenance_type not in types:
            code='catalog-'+digest(root.maintenance_type)[:20]
            v.session.execute(text('INSERT INTO maintenance_types(code,name) VALUES (:code,:name) ON CONFLICT(code) DO NOTHING'),dict(code=code,name=root.maintenance_type))
            types[root.maintenance_type]=v.session.scalar(text('SELECT maintenance_type_id FROM maintenance_types WHERE code=:code'),dict(code=code))
        instructions=profile['instructions']+'\n\nМеры безопасности:\n'+profile['safety_notes']
        if profile['engineer_note']:instructions+='\n\nПримечание инженера:\n'+profile['engineer_note']
        duration=int((b-a).total_seconds()/60)
        if root.source_kind=='regulation':
            rule=actual_rules[root.rule_id];bindings=[actual_bindings[root.binding_id]]
            namespace='regulation:'+str(root.regulation_id)
            checks=[dict(id=identity,text=c['text'],answerKind=c['answer_kind'],unit=c['unit'],required=c['required'],
                visualVerifiability=c['visual_verifiability'],photoRequired=c['photo_required'])
                for identity,c in zip(profile['checklist_ids'],profile['checklist'])]
        else:
            operation=v.repo.add('operation_templates',site_id=site,system_id=system,code=f'catalog:{publication_id}:{item["item_id"]}',
                title=root.title,description=instructions,maintenance_type_id=types[root.maintenance_type],is_active=True)
            checks=[]
            for position,c in enumerate(profile['checklist'],1):
                check=v.repo.add('checklist_templates',site_id=site,operation_template_id=operation.operation_template_id,item_code=str(position),
                    template_version=1,prompt=c['text'],input_kind={'boolean':'checkbox','number':'number','text':'text'}[c['answer_kind']],
                    unit_code=c['unit'],is_required=c['required'],position=position)
                checks.append(dict(id=str(check.checklist_template_id),text=c['text'],answerKind=c['answer_kind'],unit=c['unit'],required=c['required'],
                    visualVerifiability=c['visual_verifiability'],photoRequired=c['photo_required']))
            duration=int((b-a).total_seconds()/60)
            namespace='catalog_svik:'+root.source_sha256
            rule=v.repo.add('maintenance_rules',site_id=site,system_id=system,operation_template_id=operation.operation_template_id,
                regulation_edition_id=edition.regulation_edition_id,rule_version=1,period_unit='day',period_count=1,scheduling_mode='calendar_window',
                source_text=root.policy_note,source_ref=f'catalog_svik:{root.source_sha256}:row:{root.source_row}',required_people=root.crew_size,norm_hours=Decimal(item['person_hours']),norm_hours_basis='total_person_hours',
                active_from=root.earliest_date,active_until=root.latest_date+timedelta(days=root.source_slot=='night'),publication_status='published',data_origin=origin,
                schedule_parameters=dict(catalog_publication_id=str(publication_id),finite_occurrence=True,operation_namespace=namespace,
                    operation_metadata=dict(code=root.operation_code,title=root.title,instructions=instructions),norm_ref=root.norm_ref,norm_unit='person_hour',qualifications_confirmed=True,
                    planning_duration_minutes=duration,duration_basis='approved:catalog-segments',checklist_ids=[c['id'] for c in checks]))
            bindings=[]
            for asset in assets:bindings.append(v.repo.add('rule_equipment',site_id=site,system_id=system,maintenance_rule_id=rule.maintenance_rule_id,
                equipment_id=UUID(asset['equipment_id']),valid_from=root.earliest_date,valid_to=root.latest_date+timedelta(days=root.source_slot=='night')))
            for skill in root.qualification_ids:v.repo.add('rule_required_skills',site_id=site,maintenance_rule_id=rule.maintenance_rule_id,skill_id=skill,minimum_holders=root.crew_size)
        deadline=max(w.end_at for w in root.allowed_intervals);due=(deadline.astimezone(tz)-timedelta(microseconds=1)).date()
        task_id=tasks_by_segment[item['segment_ids'][0]]
        sequence_key=(plans[period].schedule_plan_id,bindings[0].binding_id,local.date())
        sequence[sequence_key]=sequence.get(sequence_key,0)+1
        entry=v.repo.add('schedule_entries',site_id=site,system_id=system,schedule_plan_id=plans[period].schedule_plan_id,
            maintenance_rule_id=rule.maintenance_rule_id,binding_id=bindings[0].binding_id,planned_date=local.date(),planned_at=a,
            source_date=root.source_date,source_occurrence_id=root.occurrence_id if root.source_kind=='regulation' else UUID(item['item_id']),earliest_date=root.earliest_date,sequence_no=sequence[sequence_key],
            regulatory_deadline_on=due,regulatory_deadline_at=deadline,rule_snapshot=dict(operation=dict(code=root.operation_code,title=root.title,maintenance_type=root.maintenance_type),
                occurrence=root.model_dump(mode='json'),catalog_publication_id=str(publication_id),segment_ids=item['segment_ids']))
        deps=sorted({str(tasks_by_segment[str(d)]) for sid in item['segment_ids'] for d in by_segment[sid].depends_on_segment_ids
            if str(d) not in item['segment_ids']})
        order=v.repo.add('work_orders',work_order_id=task_id,site_id=site,system_id=system,maintenance_rule_id=rule.maintenance_rule_id,
            schedule_entry_id=entry.schedule_entry_id,origin='scheduled',status='assigned',required_people_snapshot=root.crew_size,
            norm_hours_snapshot=Decimal(item['person_hours']),norm_hours_basis_snapshot='total_person_hours',planned_start_at=a,planned_end_at=b,
            regulatory_deadline_at=deadline,created_by=actor,operation_snapshot=dict(data_origin=origin,code=root.operation_code,title=root.title,
                maintenance_type=root.maintenance_type,instructions=instructions,methodology_ref=profile['methodology_ref'],norm_ref=root.norm_ref,
                engineer_note=profile['engineer_note'],safety_notes=profile['safety_notes'],operation_namespace=namespace,
                catalog_publication_id=str(publication_id),catalog_proposal_id=str(proposal['proposal_id']),source_sha256=root.source_sha256,
                source_row=root.source_row,source_cells=root.source_cells,source_date=str(root.source_date),earliest_date=str(root.earliest_date),
                source_occurrence_id=str(root.occurrence_id),segment_ids=item['segment_ids'],depends_on_task_ids=deps,checklist=checks,
                qualification_ids=list(map(str,root.qualification_ids)),norm_unit='person_hour',planning_duration_minutes=duration,
                duration_basis='approved:catalog-segments',**(dict(publication_source_kind='regulation',binding_id=str(root.binding_id),rule_id=str(root.rule_id),regulation_id=str(root.regulation_id),
                    measurement_requirements=profile['measurement_requirements'],required_acts=profile['required_acts']) if root.source_kind=='regulation' else {}),label='Утверждено главным инженером: '+proposal['decision_reason']))
        for asset in assets:v.repo.add('work_order_equipment',site_id=site,system_id=system,work_order_id=task_id,equipment_id=UUID(asset['equipment_id']),asset_snapshot=asset)
        for worker_id in item['worker_ids']:
            worker=people[worker_id]
            qualifications=[q for q in worker['qualifications'] if q['skill_id'] in {str(s) for s in root.qualification_ids}]
            v.repo.add('work_assignments',site_id=site,work_order_id=task_id,user_id=UUID(worker_id),assigned_by=actor,assigned_at=now,
                status='assigned',start_at=a,end_at=b,qualification_snapshot=qualifications,reason=proposal['decision_reason'])
            notifications.append(dict(site_id=site,user_id=UUID(worker_id),work_order_id=task_id,event_key=f'{task_id}:1:assigned',message='Вам назначено ТО'))
        created.append(dict(site=site,pub=publication_id,item=item['item_id'],task=task_id,root=item['occurrence_id'],segments=json.dumps(item['segment_ids'])))
    v.session.flush()
    v.session.execute(text('INSERT INTO published_catalog_tasks(site_id,publication_id,item_id,work_order_id,occurrence_id,segment_ids) VALUES (:site,:pub,:item,:task,:root,CAST(:segments AS jsonb))'),created)
    if notifications:v.session.execute(insert(v.models['maintenance_notifications'].__table__).on_conflict_do_nothing(index_elements=['site_id','user_id','event_key']),notifications)
    return len(created)


def register_routes(app,views):
    @app.get(BASE+'/{identity}/publication-regulations',response_model=RegulationPublicationChoices)
    def regulations(identity:UUID,response:Response,revision:int=Query(...,ge=1),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);get_version(v,identity,revision,full=False)
        params=dict(site=v.principal.site_id,id=identity,revision=revision,offset=offset)
        body=" FROM planning_draft_versions d,LATERAL jsonb_array_elements(d.occurrences) o WHERE d.site_id=:site AND d.draft_id=:id AND d.revision=:revision AND o->>'source_kind'='regulation'"
        ids=v.session.scalars(text("SELECT DISTINCT o->>'binding_id'"+body+" ORDER BY o->>'binding_id' LIMIT 25 OFFSET :offset"),params).all()
        total=v.session.scalar(text("SELECT count(DISTINCT o->>'binding_id')"+body),params)
        params['bindings']=ids
        facts=v.session.scalar(text('''SELECT jsonb_build_object('bindings',coalesce((SELECT jsonb_agg(b) FROM jsonb_array_elements(d.source_snapshot#>'{source,facts,bindings}') b
                WHERE b#>>'{binding,binding_id}'=ANY(CAST(:bindings AS text[]))),'[]'::jsonb),
            'checklist_templates',coalesce((SELECT jsonb_agg(c) FROM jsonb_array_elements(d.source_snapshot#>'{source,facts,checklist_templates}') c
                WHERE c->>'operation_template_id' IN (SELECT b#>>'{operation,operation_template_id}' FROM jsonb_array_elements(d.source_snapshot#>'{source,facts,bindings}') b
                    WHERE b#>>'{binding,binding_id}'=ANY(CAST(:bindings AS text[])))),'[]'::jsonb))
            FROM planning_draft_versions d WHERE d.site_id=:site AND d.draft_id=:id AND d.revision=:revision'''),params)
        from .regulation_publication import choices
        response.headers['Cache-Control']='private, no-store'
        return dict(items=choices(facts),total=total)

    @app.get(BASE+'/{identity}/publication-profiles',response_model=PublicationProfileChoices)
    def profiles(identity:UUID,response:Response,revision:int=Query(...,ge=1),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);get_version(v,identity,revision,full=False)
        params=dict(site=v.principal.site_id,id=identity,revision=revision,offset=offset)
        rows=v.session.execute(text('''SELECT DISTINCT ON (s->>'source_row') (s->>'source_row')::int AS row_number,s->>'operation_code' AS code,s->>'title' AS title,
            s->'included_rows' AS included_rows FROM planning_draft_versions d,LATERAL jsonb_array_elements(d.occurrences) s
            WHERE d.site_id=:site AND d.draft_id=:id AND d.revision=:revision AND s->>'source_row' IS NOT NULL ORDER BY s->>'source_row' LIMIT 25 OFFSET :offset'''),params).mappings().all()
        total=v.session.scalar(text("SELECT count(DISTINCT s->>'source_row') FROM planning_draft_versions d,LATERAL jsonb_array_elements(d.occurrences) s WHERE d.site_id=:site AND d.draft_id=:id AND d.revision=:revision"),params)
        response.headers['Cache-Control']='private, no-store';return dict(items=[dict(r) for r in rows],total=total)

    @app.post(BASE+'/{identity}/publication-proposals',response_model=PublicationProposal,status_code=201)
    def create(identity:UUID,command:PreparePublication|PreparePortfolioPublication,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):_lock_catalog(v);result=prepare(v,identity,command)
        return result

    @app.get(BASE+'/{identity}/publication-proposals',response_model=PublicationProposalList)
    def history(identity:UUID,response:Response,offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);get_version(v,identity,full=False)
        params=dict(site=v.principal.site_id,id=identity,offset=offset)
        rows=v.session.execute(text('SELECT proposal_id,draft_id,base_revision,state,created_at,expires_at,summary,blocker_count FROM draft_publication_proposals WHERE site_id=:site AND draft_id=:id ORDER BY created_at DESC,proposal_id LIMIT 25 OFFSET :offset'),params).mappings().all()
        total=v.session.scalar(text('SELECT count(*) FROM draft_publication_proposals WHERE site_id=:site AND draft_id=:id'),params)
        response.headers['Cache-Control']='private, no-store';return dict(items=[dict(r) for r in rows],total=total)

    @app.get(PATH+'/{identity}',response_model=PublicationProposal)
    def detail(identity:UUID,response:Response,v=Depends(views)):
        _guard(v,*READ_ROLES);response.headers['Cache-Control']='private, no-store';return public(get(v,identity))

    @app.get(PATH+'/{identity}/changes',response_model=PublicationChangePage)
    def changes(identity:UUID,response:Response,offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);get(v,identity)
        rows=v.session.execute(text('SELECT s FROM draft_publication_proposals p,LATERAL jsonb_array_elements(p.items) s WHERE site_id=:site AND proposal_id=:id ORDER BY s->>\'item_id\' LIMIT 25 OFFSET :offset'),dict(site=v.principal.site_id,id=identity,offset=offset)).scalars().all()
        total=v.session.scalar(text('SELECT jsonb_array_length(items) FROM draft_publication_proposals WHERE site_id=:site AND proposal_id=:id'),dict(site=v.principal.site_id,id=identity))
        workers={UUID(w) for item in rows for w in item['worker_ids']};assets={UUID(a) for item in rows for a in item['equipment_ids']}
        names={str(r['user_id']):r['full_name'] for r in v.session.execute(text('SELECT u.user_id,u.full_name FROM users u JOIN site_memberships m USING(user_id) WHERE m.site_id=:site AND u.user_id=ANY(CAST(:ids AS uuid[]))'),dict(site=v.principal.site_id,ids=list(workers))).mappings()}
        equipment={str(r['equipment_id']):r['name'] for r in v.session.execute(text('SELECT equipment_id,name FROM equipment WHERE site_id=:site AND equipment_id=ANY(CAST(:ids AS uuid[]))'),dict(site=v.principal.site_id,ids=list(assets))).mappings()}
        response.headers['Cache-Control']='private, no-store';return dict(items=rows,total=total,worker_labels=names,equipment_labels=equipment)

    @app.post(PATH+'/{identity}/approve',response_model=PublicationProposal)
    def approve(identity:UUID,command:PublicationDecision,response:Response,v=Depends(views)):
        _guard(v,'chief_engineer')
        response.headers['Cache-Control']='private, no-store';initial=get(v,identity,full=True)
        workers={UUID(w) for item in initial['items'] for w in item['worker_ids']}
        with _edit(v,workers=workers,roles=('chief_engineer',),exact_roles=True):
            lock_facts(v,initial);row=get(v,identity,full=True,lock=True)
            if row['proposal_digest']!=command.expected_digest:raise HTTPException(409,'PLAN_STALE: состав предложения не совпадает')
            if row['state'] in ('approved','published'):return public(row)
            if row['state']!='prepared' or row['blocker_count']:raise HTTPException(409,'Предложение отклонено или содержит блокирующие замечания')
            fresh(v,row)
            v.session.execute(text("UPDATE draft_publication_proposals SET state='approved',decided_by=:actor,decided_at=now(),decision_reason=:reason,approval_token=:token WHERE proposal_id=:id AND site_id=:site"),dict(actor=v.principal.user_id,reason=command.reason,token=uuid4(),id=identity,site=v.principal.site_id))
            _audit(v,'draft_publication_proposals',identity,'approve',dict(digest=row['proposal_digest'],reason=command.reason))
            return public(get(v,identity))

    @app.post(PATH+'/{identity}/reject',response_model=PublicationProposal)
    def reject(identity:UUID,command:PublicationDecision,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=('chief_engineer',),exact_roles=True):
            _lock_catalog(v);row=get(v,identity,lock=True)
            if row['proposal_digest']!=command.expected_digest:raise HTTPException(409,'PLAN_STALE: состав предложения не совпадает')
            if row['state']=='published':raise HTTPException(409,'Опубликованную историю нельзя отклонить задним числом')
            if row['state']!='rejected':
                v.session.execute(text("UPDATE draft_publication_proposals SET state='rejected',decided_by=:actor,decided_at=now(),decision_reason=:reason,approval_token=NULL WHERE proposal_id=:id AND site_id=:site"),dict(actor=v.principal.user_id,reason=command.reason,id=identity,site=v.principal.site_id))
                _audit(v,'draft_publication_proposals',identity,'reject',dict(reason=command.reason))
            return public(get(v,identity))

    @app.post(PATH+'/{identity}/publish',response_model=PublicationProposal)
    def publish(identity:UUID,command:PublishApproved,response:Response,v=Depends(views)):
        _guard(v,'chief_engineer')
        response.headers['Cache-Control']='private, no-store';initial=get(v,identity,full=True)
        workers={UUID(w) for item in initial['items'] for w in item['worker_ids']}
        with _edit(v,workers=workers,roles=('chief_engineer',),exact_roles=True):
            lock_facts(v,initial);row=get(v,identity,full=True,lock=True)
            request_sha=digest(dict(actor=str(v.principal.user_id),proposal=str(identity),command=command.model_dump(mode='json')))
            existing=v.session.execute(text('SELECT proposal_id,request_sha256 FROM draft_publications WHERE site_id=:site AND idempotency_key=:key'),dict(site=v.principal.site_id,key=command.idempotency_key)).mappings().first()
            if existing and existing['request_sha256']!=request_sha:raise HTTPException(409,'Ключ повтора использован с другими параметрами')
            if row['state'] not in ('approved','published') or row['approval_token']!=command.approval_token or row['proposal_digest']!=command.expected_digest:
                raise HTTPException(409,'Требуется явное утверждение этого предложения главным инженером')
            if row['state']=='published':return public(row)
            # Serialize unique monthly revisions with the existing generator.
            draft,roots,segments,facts=fresh(v,row);publication_id=uuid4()
            v.session.execute(text('''INSERT INTO draft_publications(publication_id,site_id,proposal_id,draft_id,revision,published_by,proposal_digest,idempotency_key,request_sha256)
                VALUES (:id,:site,:proposal,:draft,:revision,:actor,:digest,:key,:request)'''),dict(id=publication_id,site=v.principal.site_id,proposal=identity,draft=row['draft_id'],revision=row['base_revision'],actor=v.principal.user_id,digest=row['proposal_digest'],key=command.idempotency_key,request=request_sha))
            v.session.execute(text('INSERT INTO published_catalog_obligations(site_id,obligation_key,publication_id,occurrence_id,equipment_id) VALUES (:site,:key,:pub,:root,:asset)'),
                [dict(site=v.principal.site_id,key=k['key'],pub=publication_id,root=k['occurrence_id'],asset=k['equipment_id']) for k in row['obligation_keys']])
            count=materialize(v,row,publication_id,roots,segments,facts,title=draft['title'])
            v.session.execute(text("UPDATE draft_publication_proposals SET state='published',publication_id=:pub,published_at=now() WHERE proposal_id=:id AND site_id=:site"),dict(pub=publication_id,id=identity,site=v.principal.site_id))
            _audit(v,'draft_publications',publication_id,'publish',dict(proposal_id=str(identity),digest=row['proposal_digest'],created_tasks=count))
            return public(get(v,identity))
