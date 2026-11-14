"""Real regulations and Excel share immutable drafts and the same solver."""
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
import json
import pytest
from sqlalchemy import text
from app.scheduling.optimization import calculate
from app.schemas.draft_plans import WorkOccurrence
from tests.backend.test_requirements import setup_rule,YEAR,history_task
from tests.backend.test_draft_plans import prepare,worker,BASE
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login
from tests.backend.test_optimization_api import queued,finish,PATH as RUNS

PATH='/api/v1/maintenance/portfolio-plans'
POLICY=dict(format_version=2,capacity_hours_per_24h=None,capacity_confirmed=False,capacity_status='unknown')


def request_for(requirements=None,policy=None):
    return dict(kind='portfolio',requirements=requirements or YEAR,policy=policy or POLICY)


def extra_rule(managed,**changes):
    return setup_rule((*managed[:4],dict(managed[4],marker=uuid4().hex)),**changes)


def save_portfolio(admin,request):
    response=admin.post(PATH+'/preview',json=request);assert response.status_code==200,response.text
    preview=response.json();assert preview['can_save'],preview
    command=dict(input=request,preview_sha256=preview['input_sha256'],idempotency_key=str(uuid4()),title='TEST ONLY shared portfolio',reason='TEST ONLY reviewed source scope')
    response=admin.post(PATH,json=command);assert response.status_code==201,response.text
    return response.json(),command,preview


def active_counts(engine):
    with engine.connect() as c:return {t:c.scalar(text('SELECT count(*) FROM '+t)) for t in ('regulation_documents','regulation_editions','maintenance_rules','rule_equipment','work_orders','schedule_entries','schedule_plans','work_assignments')}


def test_regulation_draft_has_actual_lineage_and_no_fake_excel_or_live_writes(managed):
    engine,_,_,_,ids=managed;admin,eq,configured=setup_rule(managed,duration_minutes=120)
    before=active_counts(engine);record,command,preview=save_portfolio(admin,request_for())
    root=preview['items'][0]
    assert record['import_id'] is None and record['source_kind']=='portfolio'
    assert root['binding_id']==configured['binding_id'] and root['source_kind']=='regulation'
    with engine.connect() as c:
        assert root['rule_id']==str(c.scalar(text('SELECT maintenance_rule_id FROM rule_equipment WHERE binding_id=:id'),dict(id=configured['binding_id'])))
    assert root['minimum_duration_minutes']==120 and root['date_basis']=='regulation_rule'
    assert root['import_id'] is None and root['source_row'] is None and root['source_cells']==[]
    assert Decimal(root['total_person_hours'])==2 and root['equipment_ids']==[eq['equipment_id']]
    assert admin.post(PATH,json=command).status_code==200
    assert admin.post(PATH,json=dict(command,title='TEST ONLY changed repeat')).status_code==409
    assert admin.post(PATH+'/preview',json=request_for()).json()['input_sha256']==preview['input_sha256']
    assert admin.get(PATH).json()['items'][0]['draft_id']==record['draft_id']
    report=admin.get(BASE+'/'+record['draft_id']).json()['validation']
    assert report['status']=='incomplete' and report['issue_counts']['ACCESS_UNCONFIRMED']==1
    assert active_counts(engine)==before


def test_mixed_scope_preserves_catalog_snapshots_and_exact_hour_totals(managed):
    admin,_,_,_,_,catalog=prepare(managed)
    extra_rule(managed,code='TEST-REG-02')
    old=admin.post(BASE+'/preview',json=catalog).json()
    record,_,preview=save_portfolio(admin,request_for(YEAR|dict(catalog=catalog),catalog['policy']))
    assert record['occurrence_count']==2 and Decimal(record['total_person_hours'])==5
    excel=next(x for x in preview['items'] if x.get('source_kind','catalog')=='catalog')
    assert excel==old['items'][0]
    assert WorkOccurrence.model_validate(excel).model_dump(mode='json')==excel
    assert admin.post(BASE+'/preview',json=catalog).json()==old
    assert len(admin.get(BASE+'/'+record['draft_id']+'/occurrences').json()['items'])==2


def test_unknown_sources_filters_and_source_changes_cannot_be_saved(managed):
    engine,_,admin,_,ids=managed;setup_rule(managed)
    record,command,_=save_portfolio(admin,request_for())
    for change in (dict(q='missing'),dict(offset=25),dict(state='new')):
        assert admin.post(PATH+'/preview',json=request_for(YEAR|change)).status_code==422
    with engine.begin() as c:c.execute(text('UPDATE maintenance_rules SET norm_hours=NULL WHERE site_id=:site'),ids)
    response=admin.post(PATH+'/preview',json=request_for());assert response.status_code==200,response.text
    assert not response.json()['can_save']
    assert admin.post(PATH,json=dict(command,idempotency_key=str(uuid4()))).status_code==409
    report=admin.post(BASE+'/'+record['draft_id']+'/validate').json()
    assert report['issue_counts']['SOURCE_STALE']==1 and Decimal(report['total_person_hours'])==2


def test_roles_csrf_site_scope_and_publication_boundary(managed):
    _,app,_,_,_=managed;admin,_,_=setup_rule(managed)
    record,command,_=save_portfolio(admin,request_for());identity=record['draft_id']
    assert admin.post(PATH,json=command,headers={'X-CSRF-Token':'bad'}).status_code==403
    with closing(login(app,'executor')) as executor:
        assert executor.get(PATH).status_code==403
        assert executor.post(PATH+'/preview',json=request_for()).status_code==403
    with closing(login(app,'director')) as director:assert director.post(PATH,json=command).status_code==403
    with closing(login(app,'chief_engineer')) as other:
        assert other.get(PATH).json()['total']==0
        assert other.get(BASE+'/'+identity).status_code==404
        assert other.post(PATH,json=command).status_code!=200
    response=admin.get(BASE+'/'+identity+'/publication-profiles?revision=1')
    assert response.status_code==200 and response.json()['total']==0
    body=dict(expected_revision=1,idempotency_key=str(uuid4()),reason='TEST ONLY explicit boundary',scope_note='TEST ONLY',profiles=[dict(row_number=1,instructions='TEST ONLY',safety_notes='TEST ONLY',methodology_ref='TEST ONLY',checklist=[dict(text='TEST ONLY check')])])
    response=admin.post(BASE+'/'+identity+'/publication-proposals',json=body)
    assert response.status_code==422


def test_policy_versions_manual_cas_and_freshness_for_regulations(managed):
    engine,_,_,_,ids=managed;admin,_,_=setup_rule(managed)
    record,_,preview=save_portfolio(admin,request_for());identity=record['draft_id'];root=preview['items'][0]['occurrence_id']
    segment=admin.get(BASE+f'/{identity}/occurrences/{root}/segments').json()['items'][0]
    command=dict(expected_revision=1,occurrence_id=root,segments=[segment],reason='TEST ONLY preserve volume')
    assert admin.post(BASE+f'/{identity}/segments',json=command).json()['revision']==2
    assert admin.post(BASE+f'/{identity}/segments',json=command).status_code==409
    policy=POLICY|dict(access_status='confirmed',access_mode='unrestricted',access_ref='TEST ONLY reviewed access')
    response=admin.post(BASE+f'/{identity}/policy',json=dict(expected_revision=2,idempotency_key=str(uuid4()),policy=policy,reason='TEST ONLY explicit access'))
    assert response.status_code==200,response.text
    assert response.json()['revision']==3 and response.json()['source_kind']=='portfolio'
    assert admin.get(BASE+f'/{identity}?revision=1').json()['validation']['issue_counts']['ACCESS_UNCONFIRMED']==1
    assert admin.get(BASE+f'/{identity}/policy?revision=3').json()['policy']['access_status']=='confirmed'
    with engine.begin() as c:c.execute(text('UPDATE equipment SET revision=revision+1 WHERE site_id=:site'),ids)
    assert admin.post(BASE+f'/{identity}/segments',json=dict(command,expected_revision=3)).status_code==409


def test_common_solver_adoption_preserves_regulation_duration_and_old_revisions(queued):
    engine,_,_,_,_=queued;admin,_,_,_,_,catalog=prepare(queued)
    extra_rule(queued,code='TEST-REG-SOLVER',crew_size=1,duration_minutes=240)
    worker(queued,'TEST ONLY common solver worker')
    record,_,preview=save_portfolio(admin,request_for(YEAR|dict(catalog=catalog),catalog['policy']))
    before=active_counts(engine);identity=record['draft_id']
    response=admin.post(BASE+f'/{identity}/optimization-runs',json=dict(expected_revision=1,idempotency_key=str(uuid4()),options=dict(time_limit_seconds=10)))
    assert response.status_code==202,response.text
    run=response.json();result=finish(engine,run['run_id'])
    assert result['result']['optimized']['validation']['status']=='valid',result['result']
    root=next(x for x in preview['items'] if x.get('source_kind')=='regulation')
    piece=next(s for s in result['optimized_segments'] if s['occurrence_id']==root['occurrence_id'])
    assert (datetime.fromisoformat(piece['end_at'])-datetime.fromisoformat(piece['start_at'])).total_seconds()>=240*60
    response=admin.post(RUNS+run['run_id']+'/apply',json=dict(expected_revision=1,kind='optimized',reason='TEST ONLY reviewed common placement'))
    assert response.status_code==200,response.text
    assert response.json()['revision']==2 and response.json()['source_kind']=='portfolio'
    assert admin.get(BASE+f'/{identity}?revision=1').json()['validation']['unplaced_segments']==2
    assert active_counts(engine)==before


def test_accepted_history_provenance_and_review_cannot_be_flattened(managed):
    engine,_,_,_,ids=managed
    admin,_,configured=setup_rule(managed,pattern=dict(frequency='month',anchor_date='2026-11-30',interval=3,weekend_policy='none'),basis='after_accepted_completion',valid_from='2026-01-01')
    history_task(managed,configured['binding_id'])
    record,command,preview=save_portfolio(admin,request_for())
    assert preview['items'][0]['date_basis']=='accepted_history' and preview['items'][0]['source_date']=='2027-01-31'
    with engine.begin() as c:c.execute(text("UPDATE acceptance_reviews SET reviewed_at=reviewed_at+interval '1 day' WHERE site_id=:site"),ids)
    assert admin.post(PATH,json=dict(command,idempotency_key=str(uuid4()))).status_code==409


def test_already_published_catalog_is_excluded_from_saved_common_plan(managed):
    from tests.backend.test_publication import prepared,approve,publishing,PATH as PUBLICATIONS
    engine,_,_,_,_=managed;admin,old,proposal,_,_=prepared(managed)
    proposal=approve(admin,proposal)
    assert admin.chief.post(PUBLICATIONS+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    extra_rule(managed,code='TEST-REG-NEW')
    with engine.connect() as c:
        catalog=c.scalar(text("SELECT source_snapshot->'input' FROM planning_draft_versions WHERE draft_id=:id AND revision=:rev"),dict(id=old['draft_id'],rev=old['revision']))
    before=active_counts(engine)
    record,_,preview=save_portfolio(admin,request_for(YEAR|dict(catalog=catalog),catalog['policy']))
    assert preview['excluded_occurrences']==1 and record['occurrence_count']==1 and Decimal(record['total_person_hours'])==2
    assert preview['items'][0]['source_kind']=='regulation' and active_counts(engine)==before


def test_snapshot_contains_all_requirements_instead_of_the_first_page(managed):
    admin,_,_=setup_rule(managed,pattern=dict(frequency='day',anchor_date='2027-01-01',interval=1,weekend_policy='none'),valid_from='2027-01-01',maintenance_type='ТО1')
    record,_,preview=save_portfolio(admin,request_for())
    assert record['occurrence_count']==365 and len(preview['items'])==25
    assert Decimal(record['total_person_hours'])==730
    response=admin.get(BASE+'/'+record['draft_id']+'/occurrences?offset=350').json()
    assert response['total']==365 and len(response['items'])==15


def test_manual_placement_cannot_shorten_the_confirmed_regulation_duration(managed):
    admin,_,_,_,_,catalog=prepare(managed)
    extra_rule(managed,code='TEST-REG-MANUAL',crew_size=1,duration_minutes=240)
    technician=worker(managed,'TEST ONLY common manual worker')
    record,_,preview=save_portfolio(admin,request_for(YEAR|dict(catalog=catalog),catalog['policy']))
    identity=record['draft_id'];root=next(x for x in preview['items'] if x.get('source_kind')=='regulation')
    segment=admin.get(BASE+f"/{identity}/occurrences/{root['occurrence_id']}/segments").json()['items'][0]
    body=dict(expected_revision=1,segment_id=segment['segment_id'],start_local='2027-01-10T08:00',end_local='2027-01-10T10:00',worker_ids=[technician],reason='TEST ONLY explicit manual placement')
    assert admin.post(BASE+f'/{identity}/placements',json=body).status_code==422
    response=admin.post(BASE+f'/{identity}/placements',json=dict(body,end_local='2027-01-10T12:00'))
    assert response.status_code==200,response.text
    assert response.json()['revision']==2 and Decimal(response.json()['total_person_hours'])==5


def test_midnight_without_changed_facts_does_not_invalidate_future_draft(managed,monkeypatch):
    from app.integration import requirements
    admin,_,_=setup_rule(managed)
    observation=datetime(2026,11,14,tzinfo=timezone.utc)
    original=requirements.preview
    monkeypatch.setattr(requirements,'preview',lambda v,request,**kw:original(v,request,now=observation,**kw))
    record,_,first=save_portfolio(admin,request_for())
    observation=datetime(2026,11,15,tzinfo=timezone.utc)
    second=admin.post(PATH+'/preview',json=request_for()).json()
    assert second['input_sha256']==first['input_sha256']
    report=admin.post(BASE+'/'+record['draft_id']+'/validate').json()
    assert 'SOURCE_STALE' not in report['issue_counts']
    observation=datetime(2027,1,11,tzinfo=timezone.utc)
    assert not admin.post(PATH+'/preview',json=request_for()).json()['can_save']
    assert 'SOURCE_STALE' in admin.post(BASE+'/'+record['draft_id']+'/validate').json()['issue_counts']
