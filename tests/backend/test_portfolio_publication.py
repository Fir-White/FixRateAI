"""The common gateway must reuse real rules, preserve consent and never reissue work."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
import json
import pytest
from sqlalchemy import text,event
from tests.backend.test_portfolio_plans import request_for,save_portfolio,extra_rule,active_counts
from tests.backend.test_requirements import setup_rule,YEAR,history_task,PATH as REQUIREMENTS
from tests.backend.test_publication import profile,approve,publishing,PATH
from tests.backend.test_draft_plans import prepare,worker,pure_case,BASE
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login,PREFIX


def prepared_common(managed,*,mixed=False,place=True,**configuration):
    engine,_,admin,_,_=managed;catalog=None
    if mixed:admin,_,_,_,_,catalog=prepare(managed)
    admin,_,configured=(extra_rule if mixed else setup_rule)(managed,**(dict(crew_size=1,duration_minutes=120)|configuration))
    technician=worker(managed,'TEST ONLY regulation publication technician')
    request=request_for(YEAR|dict(catalog=catalog),pure_case()[3].model_dump(mode='json'))
    record,_,preview=save_portfolio(admin,request)
    if place:
        for root in preview['items']:
            segment=admin.get(BASE+f"/{record['draft_id']}/occurrences/{root['occurrence_id']}/segments").json()['items'][0]
            day='2027-01-02' if root.get('source_kind','catalog')=='catalog' else root['latest_date']
            start=day+'T09:00';end=day+('T12:00' if root.get('source_kind','catalog')=='catalog' else 'T11:00')
            response=admin.post(BASE+f"/{record['draft_id']}/placements",json=dict(expected_revision=record['revision'],segment_id=segment['segment_id'],start_local=start,end_local=end,worker_ids=[technician],reason='TEST ONLY reviewed real-rule placement'))
            assert response.status_code==200,response.text
            record=response.json()
    identity=record['draft_id'];choices=admin.get(BASE+f'/{identity}/publication-regulations?revision='+str(record['revision']))
    assert choices.status_code==200,choices.text
    body=dict(kind='portfolio',expected_revision=record['revision'],idempotency_key=str(uuid4()),reason='TEST ONLY reviewed common scope',scope_note='TEST ONLY exact finite additions; real rules preserved',
        profiles=[profile(catalog['row_numbers'][0])] if catalog else [],regulations=[dict(binding_id=r['binding_id'],safety_notes='TEST ONLY disconnect and verify isolation under the approved procedure',engineer_note='TEST ONLY inspect identification first') for r in choices.json()['items']])
    response=admin.post(BASE+f'/{identity}/publication-proposals',json=body)
    assert response.status_code==201,response.text
    return admin,record,response.json(),body,technician,configured


@pytest.mark.parametrize('mixed',[False,True])
def test_approved_common_publication_reuses_real_rules_and_freezes_exact_procedures(managed,mixed):
    engine,_,_,_,ids=managed;admin,record,proposal,body,_,configured=prepared_common(managed,mixed=mixed)
    assert proposal['can_approve'] and proposal['summary']['regulation_occurrences']==1
    assert proposal['summary']['added_tasks']==(2 if mixed else 1)
    changes=admin.get(PATH+proposal['proposal_id']+'/changes').json()['items']
    reg=next(i for i in changes if i.get('source_kind')=='regulation')
    assert reg['row_number'] is None and reg['execution']['binding_id']==configured['binding_id']
    assert reg['execution']['instructions']=='Inspect configured pump'
    before=active_counts(engine);proposal=approve(admin,proposal)
    assert active_counts(engine)==before
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal))
    assert response.status_code==200,response.text
    with engine.connect() as c:
        binding=c.execute(text('SELECT * FROM rule_equipment WHERE binding_id=:id'),dict(id=configured['binding_id'])).mappings().one()
        order=c.execute(text('SELECT o.*,s.binding_id,s.source_date,s.source_occurrence_id FROM work_orders o JOIN schedule_entries s USING(site_id,schedule_entry_id) WHERE o.site_id=:site AND o.maintenance_rule_id=:rule'),dict(site=ids['site'],rule=binding['maintenance_rule_id'])).mappings().one()
        assert str(order['binding_id'])==configured['binding_id'] and str(order['source_date'])=='2027-01-10'
        frozen=order['operation_snapshot'];assert frozen['checklist'][0]['id']==reg['execution']['checklist_ids'][0]
        assert frozen['checklist'][0]['text']=='Inspect pump' and frozen['engineer_note']=='TEST ONLY inspect identification first'
        assert frozen['source_row'] is None and frozen['publication_source_kind']=='regulation'
        assert frozen['measurement_requirements']==[] and frozen['required_acts']==[]
        assert Decimal(order['norm_hours_snapshot'])==2 and len(frozen['qualification_ids'])==0
        assert c.scalar(text('SELECT count(*) FROM maintenance_notifications WHERE site_id=:site'),ids)==(2 if mixed else 1)
    after=active_counts(engine)
    for table in ('regulation_documents','regulation_editions','maintenance_rules','rule_equipment'):
        assert after[table]-before[table]==(1 if mixed else 0)
    ledger=admin.post(REQUIREMENTS,json=YEAR).json()
    assert ledger['items'][0]['state']=='existing' and Decimal(ledger['summary']['new_person_hours'])==0


def test_common_concurrent_publication_and_legacy_generation_do_not_duplicate_work(managed):
    engine,_,_,_,ids=managed;admin,_,proposal,body,_,_=prepared_common(managed)
    proposal=approve(admin,proposal);command=publishing(proposal)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=command),range(2)))
    assert [r.status_code for r in responses]==[200,200],[r.text for r in responses]
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==1
    calendar=admin.chief.get(PREFIX+'/ui/calendar/preview?year=2027&month=1').json()
    generated=admin.chief.post(PREFIX+'/calendar/generate',json=dict(year=2027,month=1,preview_token=calendar['generationToken'],idempotency_key=str(uuid4())))
    assert generated.status_code==200,generated.text
    assert generated.json()['createdCount']==0
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==1
    ledger=admin.post(REQUIREMENTS,json=YEAR).json()
    assert ledger['summary']['state_counts']==dict(existing=1)
    duplicate=admin.post(BASE+f"/{proposal['draft_id']}/publication-proposals",json=dict(body,idempotency_key=str(uuid4())))
    assert duplicate.status_code==409


@pytest.mark.parametrize('change',['rule','history','availability','checklist'])
def test_common_approval_cannot_publish_stale_facts(managed,change):
    engine,_,_,_,ids=managed;admin,_,proposal,_,technician,_=prepared_common(managed)
    proposal=approve(admin,proposal)
    with engine.begin() as c:
        if change=='rule':c.execute(text('UPDATE maintenance_rules SET norm_hours=norm_hours+1 WHERE site_id=:site'),ids)
        elif change=='history':c.execute(text("UPDATE rule_equipment SET baseline_runtime_hours=1 WHERE site_id=:site"),ids)
        elif change=='checklist':c.execute(text("UPDATE checklist_templates SET prompt=prompt||' changed' WHERE site_id=:site"),ids)
        else:c.execute(text("UPDATE availability_slots SET status='unavailable' WHERE user_id=:id"),dict(id=technician))
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal))
    assert response.status_code==409,response.text
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==0


def test_common_no_client_procedure_injection_and_approval_rights(managed):
    _,app,_,_,_=managed;admin,record,proposal,body,_,_=prepared_common(managed)
    injected=dict(body,idempotency_key=str(uuid4()),regulations=[dict(body['regulations'][0],instructions='CLIENT REPLACEMENT')])
    assert admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=injected).status_code==422
    assert admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=dict(body,regulations=[],idempotency_key=str(uuid4()))).status_code==422
    assert admin.post(PATH+proposal['proposal_id']+'/approve',json=dict(expected_digest=proposal['proposal_digest'],reason='TEST ONLY forbidden approval')).status_code==403
    with closing(login(app,'chief_engineer')) as other:
        assert other.get(BASE+f"/{record['draft_id']}/publication-regulations?revision=1").status_code==404
        assert other.get(PATH+proposal['proposal_id']).status_code==404


def test_common_failure_rolls_back_every_live_write(managed,monkeypatch):
    import app.integration.publication as module
    engine,_,_,_,_=managed;admin,_,proposal,_,_,_=prepared_common(managed,mixed=True)
    before=active_counts(engine);proposal=approve(admin,proposal);original=module.materialize
    def failure(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('TEST ONLY atomic rollback')
    monkeypatch.setattr(module,'materialize',failure)
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==500
    assert active_counts(engine)==before


def test_unplaced_common_draft_is_an_inspectable_blocked_proposal(managed):
    admin,_,proposal,_,_,_=prepared_common(managed,place=False)
    assert not proposal['can_approve'] and proposal['blocker_count']>0
    assert admin.chief.post(PATH+proposal['proposal_id']+'/approve',json=dict(expected_digest=proposal['proposal_digest'],reason='TEST ONLY unplaced')).status_code==409


def test_legacy_generation_between_approval_and_publish_blocks_common_release(managed):
    engine,_,_,_,ids=managed;admin,_,proposal,_,_,_=prepared_common(managed)
    proposal=approve(admin,proposal)
    calendar=admin.chief.get(PREFIX+'/ui/calendar/preview?year=2027&month=1').json()
    response=admin.chief.post(PREFIX+'/calendar/generate',json=dict(year=2027,month=1,preview_token=calendar['generationToken'],idempotency_key=str(uuid4())))
    assert response.status_code==200,response.text
    assert response.json()['createdCount']==1,response.json()
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==409
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==1


def test_common_task_uses_existing_executor_report_and_acceptance(managed,monkeypatch):
    import app.main as main_module
    import app.integration.published_execution as execution
    import app.integration.analyst as analyst
    engine,_,_,local_login,ids=managed;admin,_,proposal,_,technician,_=prepared_common(managed)
    proposal=approve(admin,proposal)
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    with engine.connect() as c:task=str(c.scalar(text('SELECT work_order_id FROM work_orders WHERE site_id=:site'),ids))
    instant=[datetime(2027,1,10,4,tzinfo=timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return instant[0].astimezone(tz) if tz else instant[0].replace(tzinfo=None)
    for module in (execution,main_module,analyst):monkeypatch.setattr(module,'datetime',Clock)
    with closing(local_login(technician+'@example.test')) as person:
        response=person.post(PREFIX+'/tasks/'+task+'/start',json=dict(expected_revision=1))
        assert response.status_code==200,response.text
        data=response.json();check=data['execution']['checklist'][0]
        assert check['text']=='Inspect pump'
        instant[0]+=timedelta(hours=2)
        response=person.put(PREFIX+'/tasks/'+task+'/report',json=dict(expected_revision=data['task']['revision'],narrative='TEST ONLY actual inspection',answers={check['id']:'done'},actual=dict(started_at='2027-01-10T04:00:00Z',performed_at='2027-01-10T06:00:00Z',person_hours='2'),readings=[]))
        assert response.status_code==200,response.text
        response=person.post(PREFIX+'/tasks/'+task+'/submit',json=dict(expected_revision=response.json()['task']['revision']))
        assert response.status_code==200,response.text
        data=response.json()
    response=admin.chief.post(PREFIX+'/tasks/'+task+'/review',json=dict(expected_revision=data['task']['revision'],execution_id=data['execution']['id'],verdict='accepted',reason='TEST ONLY human acceptance'))
    assert response.status_code==200,response.text
    assert response.json()['task']['state']=='accepted'


def test_distinct_original_dates_may_share_one_planned_day_without_sequence_collision(managed):
    engine,_,_,_,ids=managed
    admin,_,configured=setup_rule(managed,crew_size=1,duration_minutes=120,valid_from='2027-01-01',allowed_lead_days=2,
        pattern=dict(frequency='dates',anchor_date='2027-01-09',dates=['2027-01-09','2027-01-10'],weekend_policy='none'))
    technician=worker(managed,'TEST ONLY same-day obligations')
    record,_,preview=save_portfolio(admin,request_for(YEAR,pure_case()[3].model_dump(mode='json')))
    for index,root in enumerate(preview['items']):
        segment=admin.get(BASE+f"/{record['draft_id']}/occurrences/{root['occurrence_id']}/segments").json()['items'][0]
        response=admin.post(BASE+f"/{record['draft_id']}/placements",json=dict(expected_revision=record['revision'],segment_id=segment['segment_id'],start_local=f'2027-01-08T{8+index*2:02d}:00',end_local=f'2027-01-08T{10+index*2:02d}:00',worker_ids=[technician],reason='TEST ONLY distinct source dates'))
        assert response.status_code==200,response.text
        record=response.json()
    response=admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=dict(kind='portfolio',expected_revision=record['revision'],idempotency_key=str(uuid4()),reason='TEST ONLY',scope_note='TEST ONLY two real original dates',regulations=[dict(binding_id=configured['binding_id'],safety_notes='TEST ONLY safety')]))
    assert response.status_code==201,response.text
    proposal=approve(admin,response.json())
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal));assert response.status_code==200,response.text
    with engine.connect() as c:
        rows=c.execute(text('SELECT source_date,planned_date,sequence_no FROM schedule_entries WHERE site_id=:site ORDER BY sequence_no'),ids).all()
        assert len(rows)==2 and rows[0].planned_date==rows[1].planned_date and rows[0].source_date!=rows[1].source_date
        assert [r.sequence_no for r in rows]==[1,2]


def test_accepted_published_rolling_requirement_advances_exactly_one_next_service(managed,monkeypatch):
    from app.integration import requirements
    engine,_,_,_,ids=managed
    admin,_,configured=setup_rule(managed,crew_size=1,duration_minutes=120,valid_from='2026-01-01',basis='after_accepted_completion',
        pattern=dict(frequency='month',anchor_date='2026-11-30',interval=3,short_month='last_day',weekend_policy='none'))
    history_task(managed,configured['binding_id'])
    technician=worker(managed,'TEST ONLY rolling published worker')
    with engine.begin() as c:c.execute(text("UPDATE availability_slots SET ends_at='2028-01-01T00:00:00+05:00' WHERE user_id=:id"),dict(id=technician))
    record,_,preview=save_portfolio(admin,request_for(YEAR,pure_case()[3].model_dump(mode='json')))
    assert len(preview['items'])==1 and preview['items'][0]['source_date']=='2027-01-31'
    segment=admin.get(BASE+f"/{record['draft_id']}/occurrences/{preview['items'][0]['occurrence_id']}/segments").json()['items'][0]
    response=admin.post(BASE+f"/{record['draft_id']}/placements",json=dict(expected_revision=1,segment_id=segment['segment_id'],start_local='2027-01-31T09:00',end_local='2027-01-31T11:00',worker_ids=[technician],reason='TEST ONLY rolling placement'))
    assert response.status_code==200,response.text
    record=response.json()
    response=admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=dict(kind='portfolio',expected_revision=record['revision'],idempotency_key=str(uuid4()),reason='TEST ONLY',scope_note='TEST ONLY one rolling obligation',regulations=[dict(binding_id=configured['binding_id'],safety_notes='TEST ONLY approved safety')]))
    assert response.status_code==201,response.text
    proposal=approve(admin,response.json())
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    # The accepted fact is attached to the actual published rule/asset; it is
    # not a separate cloned finite procedure. The report lifecycle is exercised above.
    with engine.begin() as c:
        task=c.scalar(text("SELECT work_order_id FROM work_orders WHERE site_id=:site AND status='assigned'"),ids)
        report=uuid4()
        c.execute(text("UPDATE work_orders SET status='completed',completed_at='2027-01-31T06:00:00Z' WHERE work_order_id=:id"),dict(id=task))
        c.execute(text("INSERT INTO work_reports(work_report_id,site_id,work_order_id,submitted_by,status) VALUES (:report,:site,:task,:user,'reviewed')"),ids|dict(task=task,report=report))
        c.execute(text("""INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision,reviewed_at,decision_context)
            VALUES (:site,:task,:report,:user,'accepted','2027-01-31T07:00:00Z','{"performed_at":"2027-01-31T06:00:00Z"}')"""),ids|dict(task=task,report=report))
    original=requirements.preview
    monkeypatch.setattr(requirements,'preview',lambda v,request,**kw:original(v,request,now=datetime(2027,1,31,8,tzinfo=timezone.utc),**kw))
    ledger=admin.post(REQUIREMENTS,json=YEAR).json()
    assert ledger['summary']['total']==1 and ledger['items'][0]['state']=='new'
    assert ledger['items'][0]['source_date']=='2027-04-30'


def test_incomplete_regulation_procedure_cannot_be_silently_replaced(managed):
    engine,_,_,_,ids=managed;admin,record,_,body,_,_=prepared_common(managed)
    with engine.begin() as c:c.execute(text("UPDATE maintenance_rules SET schedule_parameters=schedule_parameters-'methodology_ref' WHERE site_id=:site"),ids)
    # An old draft is stale first, rather than accepting a client-written substitute.
    response=admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=dict(body,idempotency_key=str(uuid4())))
    assert response.status_code==409
    fresh,_,_=save_portfolio(admin,request_for(YEAR,pure_case()[3].model_dump(mode='json')))
    choices=admin.get(BASE+f"/{fresh['draft_id']}/publication-regulations?revision=1").json()
    assert not choices['items'][0]['source_complete']
    response=admin.post(BASE+f"/{fresh['draft_id']}/publication-proposals",json=dict(body,expected_revision=1,idempotency_key=str(uuid4())))
    assert response.status_code==422


def test_overlapping_bindings_cannot_issue_the_same_asset_operation_date_twice(managed):
    engine,_,_,_,_=managed;admin,_,configured=setup_rule(managed)
    with engine.begin() as c:
        rule=c.scalar(text('SELECT maintenance_rule_id FROM rule_equipment WHERE binding_id=:id'),dict(id=configured['binding_id']))
        overlapping_rule=uuid4()
        c.execute(text('''INSERT INTO maintenance_rules SELECT (jsonb_populate_record(NULL::maintenance_rules,to_jsonb(r)||CAST(:override AS jsonb))).*
            FROM maintenance_rules r WHERE r.maintenance_rule_id=:id'''),dict(id=rule,override=json.dumps(dict(maintenance_rule_id=str(overlapping_rule),rule_version=2))))
        c.execute(text('''INSERT INTO rule_equipment SELECT (jsonb_populate_record(NULL::rule_equipment,to_jsonb(b)||CAST(:override AS jsonb))).*
            FROM rule_equipment b WHERE b.binding_id=:id'''),dict(id=configured['binding_id'],override=json.dumps(dict(binding_id=str(uuid4()),maintenance_rule_id=str(overlapping_rule)))))
    record,_,preview=save_portfolio(admin,request_for(YEAR,pure_case()[3].model_dump(mode='json')))
    assert preview['total_occurrences']==2
    choices=admin.get(BASE+f"/{record['draft_id']}/publication-regulations?revision=1").json()
    response=admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=dict(kind='portfolio',expected_revision=1,idempotency_key=str(uuid4()),reason='TEST ONLY',scope_note='TEST ONLY duplicate overlap',regulations=[dict(binding_id=r['binding_id'],safety_notes='TEST ONLY safety') for r in choices['items']]))
    assert response.status_code==201,response.text
    assert not response.json()['can_approve'] and any(i['code']=='DUPLICATE_OBLIGATION' for i in response.json()['blockers'])
