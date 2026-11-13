"""Common model: true calendar semantics, conserved effort and scoped versions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from uuid import UUID,uuid4
import json
import pytest
from sqlalchemy import text,event
from app.schemas.draft_plans import WorkOccurrence,WorkSegment,DraftPolicy
from app.assignment.schemas import Worker
from app.scheduling.draft_validator import validate
from tests.backend.test_catalog_decisions import catalog,decision,write
from tests.backend.test_management import managed,equipment
from tests.backend.test_runtime_integration import runtime,login

BASE='/api/v1/maintenance/draft-plans'
UTC=timezone.utc

def moment(day,hour=0): return datetime(2027,1,day,hour,tzinfo=UTC)

def pure_case():
    root=WorkOccurrence(occurrence_id=uuid4(),site_id=uuid4(),import_id=uuid4(),source_sha256='a'*64,parser_version='test',source_row=8,
        decision_revision=1,source_cells=['B8','H8'],source_date=date(2027,1,10),source_slot='whole_day',title='TEST ONLY continuous job',operation_code='1.4',maintenance_type='ТО2',
        interpretation='CONTINUOUS_WORK',equipment_ids=[uuid4()],earliest_date=date(2027,1,1),latest_date=date(2027,1,10),
        allowed_intervals=[dict(start_at=moment(1),end_at=moment(11))],total_person_hours='48',crew_size=2,splittable=True,
        min_segment_minutes=60,qualification_ids=[],qualifications_confirmed=True,included_rows=[],norm_ref='TEST ONLY',norm_scope='whole_binding',policy_note='TEST ONLY')
    people=[Worker.model_validate_json(json.dumps(dict(worker_id=str(uuid4()),site_id=str(root.site_id),name='TEST ONLY worker',active=True,membership_active=True,can_execute=True,
        availability=[dict(start_at=moment(1).isoformat(),end_at=moment(11).isoformat(),status='available')],qualifications=[],bookings=[]))) for _ in range(2)]
    segments=[WorkSegment(segment_id=uuid4(),occurrence_id=root.occurrence_id,equipment_ids=root.equipment_ids,person_hours='24',start_at=a,end_at=b,worker_ids=[w.worker_id for w in people])
        for a,b in ((moment(2),moment(2,12)),(moment(2,12),moment(3)))]
    policy=DraftPolicy(capacity_hours_per_24h='24',capacity_confirmed=True,capacity_ref='TEST ONLY synthetic policy')
    return root,segments,people,policy

def check(root,segments,people,policy,**kwargs):
    return validate([root],segments,people,policy,date(2027,1,1),date(2027,1,10),'UTC',moment(1),**kwargs)

def test_continuous_segments_conserve_48_hours_and_one_crew():
    root,segments,people,policy=pure_case()
    report=check(root,segments,people,policy)
    assert report.status=='valid' and report.total_person_hours==48 and report.placed_person_hours==48
    assert sum(d.planned_person_hours for d in report.days)==48
    assert not report.ready_for_real_plan
    assert check(root.model_copy(update={'splittable':False}),segments,people,policy).issue_counts['SEGMENTATION_FORBIDDEN']==1
    wrong=[segments[0].model_copy(update={'person_hours':Decimal(23)}),segments[1]]
    assert 'HOURS_NOT_CONSERVED' in check(root,wrong,people,policy).issue_counts
    gap=[segments[0],segments[1].model_copy(update={'start_at':moment(2,13),'end_at':moment(3,1)})]
    assert 'CONTINUITY_BROKEN' in check(root,gap,people,policy).issue_counts

def test_validator_capacity_absence_global_bookings_skills_locks_and_unknowns():
    root,segments,people,policy=pure_case()
    assert 'CAPACITY_EXCEEDED' in check(root,segments,people,policy.model_copy(update={'capacity_hours_per_24h':Decimal(8)})).issue_counts
    unknown=check(root,segments,people,policy.model_copy(update={'capacity_confirmed':False}))
    assert unknown.status=='incomplete' and unknown.days[1].available_person_hours is None
    booked=deepcopy(people)
    from app.assignment.schemas import Booking,Availability,Qualification
    booked[0].bookings=[Booking(task_id=uuid4(),start_at=moment(2),end_at=moment(3),blocks_time=True)]
    assert 'WORKER_BUSY_OR_ABSENT' in check(root,segments,booked,policy).issue_counts
    absent=deepcopy(people);absent[0].availability.append(Availability(start_at=moment(2),end_at=moment(3),status='unavailable'))
    assert 'WORKER_BUSY_OR_ABSENT' in check(root,segments,absent,policy).issue_counts
    qualified=deepcopy(people);skill=uuid4()
    qualified[0].qualifications=[Qualification(skill_id=skill,verified_at=moment(1),valid_until=date(2027,1,1),validity_required=True)]
    assert 'QUALIFICATION_MISSING' in check(root.model_copy(update={'qualification_ids':[skill]}),segments,qualified,policy).issue_counts
    locked=segments[0].model_copy(update={'locked':True})
    assert 'LOCKED_SEGMENT' in check(root,segments,people,policy,previous_segments=[locked]).issue_counts
    assert check(root,segments,people,policy,previous_segments=[locked],unlock=True).status=='valid'
    unknown_people=deepcopy(people);unknown_people[0].booking_data_complete=False
    assert check(root,segments,unknown_people,policy).status=='incomplete'
    foreign=deepcopy(people);foreign[0].site_id=uuid4()
    assert 'WORKER_UNAVAILABLE' in check(root,segments,foreign,policy).issue_counts

def test_dependencies_overlap_and_window_checks_do_not_change_hours():
    root,segments,people,policy=pure_case()
    cycle=[segments[0].model_copy(update={'depends_on_segment_ids':[segments[1].segment_id]}),segments[1].model_copy(update={'depends_on_segment_ids':[segments[0].segment_id]})]
    assert 'DEPENDENCY_CYCLE' in check(root,cycle,people,policy).issue_counts
    overlap=[segments[0],segments[1].model_copy(update={'start_at':moment(2,11),'end_at':moment(2,23)})]
    report=check(root,overlap,people,policy)
    assert {'WORKER_OVERLAP','EQUIPMENT_OVERLAP'}.issubset(report.issue_counts)
    beyond=[segments[0],segments[1].model_copy(update={'start_at':moment(11),'end_at':moment(11,12)})]
    assert 'OUTSIDE_WINDOW' in check(root,beyond,people,policy).issue_counts

def prepare(managed,**overrides):
    engine,_,admin,_,ids=managed;eq=equipment(admin,ids);identity,_,content=catalog(admin,217)
    row=admin.get('/api/v1/maintenance/catalog-imports/'+identity+'/operations?q=0190').json()['items'][0]['row']
    payload=decision([eq['equipment_id']],qualifications_confirmed=True,qualification_note='TEST ONLY no special qualifications',**overrides)
    response=write(admin.chief,identity,row,payload,confirm=True)
    assert response.status_code==200,response.text
    request=dict(import_id=identity,starts_on='2027-01-01',ends_on='2027-12-31',row_numbers=[row],expansion='source_january',
        policy=dict(capacity_hours_per_24h='24',capacity_confirmed=True,capacity_ref='TEST ONLY synthetic capacity'))
    return admin,eq,identity,row,payload,request

def save(admin,request):
    preview=admin.post(BASE+'/preview',json=request)
    assert preview.status_code==200,preview.text
    body=dict(input=request,preview_sha256=preview.json()['input_sha256'],idempotency_key=str(uuid4()),title='TEST ONLY plan',reason='TEST ONLY reviewed source')
    response=admin.post(BASE,json=body)
    assert response.status_code==201,response.text
    return response.json(),body,preview.json()

def test_ten_monthly_marks_are_one_obligation_idempotent_source_and_versions(managed):
    engine,_,_,_,ids=managed;admin,eq,identity,row,payload,request=prepare(managed)
    with engine.connect() as c:
        before={t:c.scalar(text(f'SELECT count(*) FROM {t} WHERE site_id=:site'),ids) for t in ('schedule_plans','schedule_entries','work_orders','work_assignments')}
    record,body,preview=save(admin,request)
    assert preview['total_occurrences']==1 and preview['total_segments']==1 and Decimal(preview['total_person_hours'])==3
    assert preview['items'][0]['earliest_date']=='2027-01-01' and preview['items'][0]['latest_date']=='2027-01-10'
    assert admin.post(BASE,json=body).status_code==200
    assert admin.post(BASE,json=dict(body,title='other')).status_code==409
    draft=record['draft_id'];root=preview['items'][0]['occurrence_id']
    details=admin.get(BASE+'/'+draft).json()
    assert details['validation']['status']=='incomplete' and details['months'][0]['due_person_hours']=='3.000'
    original=admin.get(BASE+f'/{draft}/occurrences/{root}/segments').json()['items'][0]
    command=dict(expected_revision=1,occurrence_id=root,segments=[dict(original,person_hours='2')],reason='TEST ONLY invalid volume')
    assert admin.post(BASE+f'/{draft}/segments',json=command).status_code==422
    assert admin.get(BASE+f'/{draft}/versions').json()['total']==1
    assert admin.post(BASE+f'/{draft}/segments',json=dict(command,segments=[original])).status_code==200
    assert admin.post(BASE+f'/{draft}/segments',json=dict(command,segments=[original])).status_code==409
    assert admin.get(BASE+f'/{draft}?revision=1').json()['record']['revision']==1
    assert admin.get(BASE+f'/{draft}/versions').json()['total']==2
    assert admin.get(BASE+f'/{draft}/occurrences?period=2027-02').json()['total']==0
    assert admin.get(BASE+f'/{draft}/occurrences?period=0000-01').status_code==422
    with engine.connect() as c:
        assert before=={t:c.scalar(text(f'SELECT count(*) FROM {t} WHERE site_id=:site'),ids) for t in before}

def test_unknowns_annual_anchor_and_stale_preview_are_blocked(managed):
    admin,_,_,row,payload,request=prepare(managed)
    unready=dict(request,row_numbers=[5])
    assert not admin.post(BASE+'/preview',json=unready).json()['can_save']
    annual=dict(request,expansion='confirmed_rule')
    preview=admin.post(BASE+'/preview',json=annual).json()
    assert not preview['can_save'] and preview['issues'][0]['code']=='CALENDAR_ANCHOR_REQUIRED'
    record,body,_=save(admin,request)
    assert write(admin.chief,request['import_id'],row,dict(payload,norm_value='4'),1,True).status_code==200
    assert admin.post(BASE,json=dict(body,idempotency_key=str(uuid4()))).status_code==409
    report=admin.post(BASE+f"/{record['draft_id']}/validate").json()
    assert report['status']=='incomplete' and report['issue_counts']['SOURCE_STALE']==1
    assert Decimal(report['total_person_hours'])==3

def test_confirmed_calendar_uses_shared_recurrence_and_date_identity(managed):
    pattern=dict(frequency='month',anchor_date='2027-01-31',interval=1,short_month='last_day',weekend_policy='none')
    admin,_,_,_,_,request=prepare(managed,interpretation='FIXED_EXECUTION',calendar_pattern=pattern)
    request['expansion']='confirmed_rule'
    first=admin.post(BASE+'/preview',json=request).json();second=admin.post(BASE+'/preview',json=request).json()
    assert first['can_save'] and first['total_occurrences']==12 and first['input_sha256']==second['input_sha256']
    assert first['items'][1]['source_date']=='2027-02-28'
    assert first['items']==second['items']
    assert Decimal(first['total_person_hours'])==36

def test_recurring_window_requires_explicit_anchor_and_lead_policy(managed):
    pattern=dict(frequency='month',anchor_date='2027-01-10',interval=1,weekend_policy='none')
    admin,_,_,_,_,request=prepare(managed,calendar_pattern=pattern,allowed_lead_days=9)
    request['expansion']='confirmed_rule'
    preview=admin.post(BASE+'/preview',json=request).json()
    assert preview['can_save'] and preview['total_occurrences']==12
    feb=preview['items'][1]
    assert feb['earliest_date']=='2027-02-01' and feb['latest_date']=='2027-02-10'
    assert feb['date_basis']=='confirmed_rule' and feb['source_cells']==[f"B{feb['source_row']}",f"D{feb['source_row']}",f"E{feb['source_row']}"]

def test_explicit_dates_cannot_silently_replace_a_monthly_rule(managed):
    _,_,admin,_,ids=managed;eq=equipment(admin,ids);identity,rows,_=catalog(admin)
    pattern=dict(frequency='dates',anchor_date='2027-01-05',dates=['2027-01-05'])
    assert write(admin.chief,identity,rows[0],decision([eq['equipment_id']],calendar_pattern=pattern),confirm=True).status_code==422

def test_roles_site_scope_concurrent_versions_and_bounded_reads(managed):
    engine,app,_,_,ids=managed;admin,_,_,_,_,request=prepare(managed)
    record,_,preview=save(admin,request);identity=record['draft_id'];root=preview['items'][0]['occurrence_id']
    segment=admin.get(BASE+f'/{identity}/occurrences/{root}/segments').json()['items'][0]
    command=dict(expected_revision=1,occurrence_id=root,segments=[segment],reason='TEST ONLY concurrent edit')
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(lambda _:admin.post(BASE+f'/{identity}/segments',json=command),range(2)))
    assert sorted(r.status_code for r in responses)==[200,409]
    with closing(login(app,'chief_engineer')) as other:
        for tail in ('','/versions','/occurrences','/occurrences/'+root+'/segments'):
            assert other.get(BASE+'/'+identity+tail).status_code==404
        assert other.post(BASE+f'/{identity}/validate').status_code==404
    with closing(login(app,'director')) as director: assert director.post(BASE+'/preview',json=request).status_code==403
    with closing(login(app,'executor')) as executor: assert executor.get(BASE+'?import_id='+request['import_id']).status_code==403
    statements=[]
    def count(conn,cursor,statement,params,context,many):
        if statement.lstrip().upper().startswith('SELECT'): statements.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try:
        response=admin.get(BASE+f'/{identity}/occurrences')
        assert response.status_code==200 and len(response.json()['items'])<=25 and len(statements)<=10
    finally:event.remove(engine,'before_cursor_execute',count)

def worker(managed,label):
    engine,_,_,_,ids=managed;identity=uuid4()
    with engine.begin() as c:
        c.execute(text('''INSERT INTO users(user_id,full_name,email,password_hash)
            SELECT :id,:name,:email,password_hash FROM users WHERE user_id=:actor'''),dict(id=identity,name=label,email=f'{identity}@example.test',actor=ids['user']))
        c.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:id,'technician')"),dict(site=ids['site'],id=identity))
        c.execute(text("INSERT INTO availability_slots(site_id,user_id,starts_at,ends_at,status) VALUES (:site,:id,'2027-01-01T00:00:00+05:00','2027-01-11T00:00:00+05:00','available')"),dict(site=ids['site'],id=identity))
    return str(identity)

def test_real_crew_local_time_split_locks_and_immutable_versions(managed):
    admin,_,_,_,_,request=prepare(managed,interpretation='CONTINUOUS_WORK',norm_value='48',crew_size=2,splittable=True,min_segment_minutes=60)
    workers=[worker(managed,f'TEST ONLY crew {i}') for i in range(2)]
    record,_,preview=save(admin,request);identity=record['draft_id'];root=preview['items'][0]['occurrence_id']
    old=admin.get(BASE+f'/{identity}/occurrences/{root}/segments').json()['items'][0]
    first=dict(old,person_hours='24',start_at='2027-01-01T08:00:00+05:00',end_at='2027-01-01T20:00:00+05:00',worker_ids=workers,locked=True)
    second=dict(old,segment_id=str(uuid4()),person_hours='24',start_at='2027-01-01T20:00:00+05:00',end_at='2027-01-02T08:00:00+05:00',worker_ids=workers,depends_on_segment_ids=[first['segment_id']])
    command=dict(expected_revision=1,occurrence_id=root,segments=[first,second],reason='TEST ONLY split 48 hours')
    saved=admin.post(BASE+f'/{identity}/segments',json=command)
    assert saved.status_code==200,saved.text
    report=admin.post(BASE+f'/{identity}/validate').json()
    assert report['status']=='valid' and Decimal(report['total_person_hours'])==48
    assert sum(Decimal(d['planned_person_hours']) for d in report['days'])==48
    engine=managed[0]
    with engine.connect() as c:
        stored=c.execute(text('SELECT source_snapshot,resource_snapshot,occurrences,segments,validation_snapshot FROM planning_draft_versions WHERE draft_id=:id AND revision=2'),dict(id=identity)).mappings().one()
    facts=stored['resource_snapshot'];generation=stored['source_snapshot']['input']
    replay=validate([WorkOccurrence.model_validate(o) for o in stored['occurrences']],
        [WorkSegment.model_validate(s) for s in stored['segments']],[Worker.model_validate_json(json.dumps(w)) for w in facts['workers']],
        DraftPolicy.model_validate(generation['policy']),date.fromisoformat(generation['starts_on']),date.fromisoformat(generation['ends_on']),
        stored['source_snapshot']['source']['timezone'],datetime.fromisoformat(facts['as_of']),
        equipment_bookings={UUID(k):[(datetime.fromisoformat(a),datetime.fromisoformat(b)) for a,b in values] for k,values in facts['equipment_bookings'].items()},
        equipment_unknown=[UUID(i) for i in facts['equipment_unknown']])
    assert replay.input_sha256==stored['validation_snapshot']['input_sha256']
    # Unlock is explicit; rejected edits never append a revision.
    change=dict(command,expected_revision=2,segments=[dict(first,locked=False),second])
    assert admin.post(BASE+f'/{identity}/segments',json=change).status_code==422
    assert admin.post(BASE+f'/{identity}/segments',json=dict(change,unlock=True)).status_code==200
    prior=admin.get(BASE+f'/{identity}/occurrences/{root}/segments?revision=2').json()
    assert any(s['locked'] for s in prior['items'])
    # Local timestamps are interpreted by the site, not by the browser timezone.
    place=dict(expected_revision=3,segment_id=first['segment_id'],start_local='2027-01-01T08:00',end_local='2027-01-01T20:00',worker_ids=workers,reason='TEST ONLY local placement')
    result=admin.post(BASE+f'/{identity}/placements',json=place)
    assert result.status_code==200,result.text
    assert admin.post(BASE+f'/{identity}/placements',json=dict(place,expected_revision=4,end_local=None)).status_code==422

def test_two_daily_events_and_real_equipment_batch_do_not_multiply_by_marks(managed):
    engine,_,_,_,ids=managed;admin,eq,identity,_,payload,request=prepare(managed)
    daily=admin.get('/api/v1/maintenance/catalog-imports/'+identity+'/operations?q=0161').json()['items'][0]['row']
    d=decision([eq['equipment_id']],interpretation='FIXED_EXECUTION',frequency_kind='daily_events',frequency_interval=2,mark_slots='day_night')
    assert write(admin.chief,identity,daily,d,confirm=True).status_code==200
    daily_request=dict(request,row_numbers=[daily])
    assert not admin.post(BASE+'/preview',json=daily_request).json()['can_save']
    daily_request['policy']=dict(request['policy'],day_start_minute=480,night_start_minute=1200)
    preview=admin.post(BASE+'/preview',json=daily_request).json()
    assert preview['can_save'] and preview['total_occurrences']==62 and Decimal(preview['total_person_hours'])==186
    with engine.begin() as c:
        second=c.scalar(text("INSERT INTO equipment(site_id,system_id,equipment_type_id,asset_code,name) VALUES (:site,:system,:type,:code,'TEST ONLY second asset') RETURNING equipment_id"),dict(ids,code='BATCH-'+ids['marker']))
    row=request['row_numbers'][0]
    batch=dict(payload,interpretation='EQUIPMENT_BATCH',equipment_ids=[eq['equipment_id'],str(second)],splittable=True,min_segment_minutes=60)
    assert write(admin.chief,identity,row,batch,1,True).status_code==200
    preview=admin.post(BASE+'/preview',json=request).json()
    assert preview['total_occurrences']==1 and preview['total_segments']==2 and Decimal(preview['total_person_hours'])==6

def test_global_booking_is_private_and_blocks_a_second_site(managed):
    engine,_,_,_,ids=managed;admin,_,_,_,_,request=prepare(managed)
    identity=worker(managed,'TEST ONLY shared technician')
    with engine.begin() as c:
        foreign=c.execute(text("SELECT work_order_id,site_id FROM work_orders WHERE site_id<>:site AND status IN ('draft','assigned','rework') AND completed_at IS NULL LIMIT 1"),ids).mappings().one()
        actor=c.scalar(text('SELECT user_id FROM site_memberships WHERE site_id=:site LIMIT 1'),dict(site=foreign['site_id']))
        c.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:id,'technician')"),dict(site=foreign['site_id'],id=identity))
        assignment=c.scalar(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,start_at,end_at)
            VALUES (:site,:order,:id,:actor,'2027-01-01T09:00:00+05:00','2027-01-01T12:00:00+05:00') RETURNING work_assignment_id'''),
            dict(site=foreign['site_id'],order=foreign['work_order_id'],id=identity,actor=actor))
    try:
        record,_,preview=save(admin,request);draft=record['draft_id'];root=preview['items'][0]['occurrence_id']
        segment=admin.get(BASE+f'/{draft}/occurrences/{root}/segments').json()['items'][0]
        response=admin.post(BASE+f'/{draft}/placements',json=dict(expected_revision=1,segment_id=segment['segment_id'],
            start_local='2027-01-01T09:00',end_local='2027-01-01T12:00',worker_ids=[identity],reason='TEST ONLY overlapping other site'))
        assert response.status_code==422,response.text
        assert str(foreign['work_order_id']) not in response.text and str(foreign['site_id']) not in response.text
    finally:
        with engine.begin() as c:
            c.execute(text('DELETE FROM work_assignments WHERE work_assignment_id=:id'),dict(id=assignment))
            c.execute(text('DELETE FROM site_memberships WHERE site_id=:site AND user_id=:id'),dict(site=foreign['site_id'],id=identity))

def test_included_steps_are_attached_without_a_second_obligation(managed):
    admin,_,identity,row,payload,request=prepare(managed)
    child=admin.get('/api/v1/maintenance/catalog-imports/'+identity+'/operations?q=0191').json()['items'][0]['row']
    child_payload=dict(payload,frequency_kind='included_in',included_in_row=row,norm_value=None)
    assert write(admin.chief,identity,child,child_payload,confirm=True).status_code==200
    request['row_numbers']=[row,child]
    result=admin.post(BASE+'/preview',json=request).json()
    assert result['can_save'] and result['total_occurrences']==1 and Decimal(result['total_person_hours'])==3
    assert result['items'][0]['included_rows']==[child]

@pytest.mark.parametrize('interval',[4,5])
def test_multiyear_anchor_is_explicit_and_event_rules_do_not_generate(managed,interval):
    pattern=dict(frequency='year',anchor_date='2024-01-05',interval=interval,weekend_policy='none')
    admin,_,identity,row,payload,request=prepare(managed,interpretation='FIXED_EXECUTION',frequency_kind='year',frequency_interval=interval,calendar_pattern=pattern)
    request.update(expansion='confirmed_rule',starts_on=f'{2024+interval}-01-01',ends_on=f'{2024+interval}-12-31')
    response=admin.post(BASE+'/preview',json=request).json()
    assert response['total_occurrences']==1 and response['items'][0]['source_date']==f'{2024+interval}-01-05'
    request.update(starts_on=f'{2025+interval}-01-01',ends_on=f'{2025+interval}-12-31')
    assert admin.post(BASE+'/preview',json=request).json()['total_occurrences']==0
    assert write(admin.chief,identity,row,dict(payload,frequency_kind='event',calendar_pattern=None),1,True).status_code==200
    assert admin.post(BASE+'/preview',json=request).json()['issues'][0]['code']=='EVENT_TRIGGER_REQUIRED'

def test_large_version_has_bounded_reads_and_compact_overview(managed):
    engine,_,admin,_,ids=managed;eq=equipment(admin,ids);identity,_,_=catalog(admin,500)
    from app.schemas.catalog_decisions import DecisionInput
    payload=DecisionInput.model_validate(decision([eq['equipment_id']],interpretation='FIXED_EXECUTION',frequency_kind='dates',frequency_interval=None,
        calendar_pattern=dict(frequency='dates',anchor_date='2027-01-05',dates=['2027-01-05','2027-02-05']),
        qualifications_confirmed=True,qualification_note='TEST ONLY no special requirements')).model_dump_json()
    with engine.begin() as c:
        rows=c.scalar(text("SELECT array_agg((o->>'row')::int) FROM regulation_catalog_imports,LATERAL jsonb_array_elements(catalog_data->'operations') o WHERE import_id=:id"),dict(id=identity))
        chief=c.scalar(text("SELECT user_id FROM site_memberships WHERE site_id=:site AND role='chief_engineer'"),ids)
        c.execute(text('''INSERT INTO catalog_operation_decisions
            (decision_id,site_id,import_id,row_number,revision,created_by,confirmed,reason,payload,binding_snapshot)
            SELECT gen_random_uuid(),c.site_id,c.import_id,(o->>'row')::int,1,:actor,true,'TEST ONLY synthetic confirmed bulk',CAST(:payload AS jsonb),
            jsonb_build_array(jsonb_build_object('equipment_id',CAST(:asset AS text),'revision',1,'status','active'))
            FROM regulation_catalog_imports c,LATERAL jsonb_array_elements(c.catalog_data->'operations') o WHERE c.import_id=:id'''),dict(id=identity,actor=chief,payload=payload,asset=eq['equipment_id']))
    request=dict(import_id=identity,starts_on='2027-01-01',ends_on='2027-12-31',row_numbers=rows,expansion='confirmed_rule',policy=dict(capacity_hours_per_24h=None))
    record,_,preview=save(admin,request)
    assert preview['total_occurrences']==1000 and len(preview['items'])==25
    raw=admin.post(BASE+'/preview',json=dict(request,expansion='source_january')).json()
    assert not raw['can_save'] and raw['issues'][0]['code']=='EXPLICIT_DATES_REQUIRED'
    statements=[]
    def count(conn,cursor,statement,params,context,many):
        if statement.lstrip().upper().startswith('SELECT'): statements.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try:
        response=admin.get(BASE+f"/{record['draft_id']}/occurrences?offset=900")
        assert response.status_code==200 and len(response.json()['items'])==25 and len(statements)<=10
        statements.clear()
        response=admin.get(BASE+'/'+record['draft_id'])
        assert response.status_code==200 and len(response.content)<200000 and len(statements)<=8
        assert 'resource_snapshot' not in response.text and 'source_snapshot' not in response.text
    finally:event.remove(engine,'before_cursor_execute',count)
