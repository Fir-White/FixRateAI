"""A rollback appends a version and cannot erase another author or live consent."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from decimal import Decimal
import pytest
from sqlalchemy import text
from tests.backend.test_draft_plans import prepare,save,worker,BASE,pure_case
from tests.backend.test_portfolio_plans import save_portfolio,request_for,active_counts
from tests.backend.test_requirements import setup_rule
from tests.backend.test_publication import prepared,approve,publishing,PATH
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login
from tests.backend.test_optimization_api import queued,enqueue,finish,PATH as RUNS


def edited(managed,*,locked=False):
    admin,_,_,_,_,request=prepare(managed);person=worker(managed,'TEST ONLY undo worker')
    record,_,preview=save(admin,request);identity=record['draft_id'];root=preview['items'][0]['occurrence_id']
    segment=admin.get(BASE+f'/{identity}/occurrences/{root}/segments').json()['items'][0]
    response=admin.post(BASE+f'/{identity}/placements',json=dict(expected_revision=1,segment_id=segment['segment_id'],start_local='2027-01-02T09:00',end_local='2027-01-02T12:00',worker_ids=[person],locked=locked,reason='TEST ONLY own manual placement'))
    assert response.status_code==200,response.text
    return admin,response.json(),segment


def command(revision=2,**kw):return dict(expected_revision=revision,idempotency_key=str(uuid4()),reason='TEST ONLY undo my last change',**kw)


def test_undo_preserves_both_versions_and_appends_the_checked_parent(managed):
    engine,_,_,_,_=managed;admin,record,original=edited(managed)
    before=active_counts(engine);identity=record['draft_id'];url=BASE+f'/{identity}/undo'
    choice=admin.get(url+'?revision=2').json();assert choice['can_undo'] and choice['restores_revision']==1 and not choice['requires_unlock']
    body=command();response=admin.post(url,json=body);assert response.status_code==200,response.text
    result=response.json();assert result['revision']==3 and result['change_kind']=='undo' and result['undone_revision']==2 and result['restored_revision']==1
    root=original['occurrence_id']
    assert admin.get(BASE+f'/{identity}/occurrences/{root}/segments?revision=3').json()['items'][0]==original
    assert admin.get(BASE+f'/{identity}/occurrences/{root}/segments?revision=2').json()['items'][0]['start_at'] is not None
    assert admin.post(url,json=body).json()==result
    assert admin.post(url,json=dict(body,reason='changed repeat')).status_code==409
    assert admin.get(url).json()['blocker']=='ALREADY_UNDONE'
    assert active_counts(engine)==before


def test_undo_own_policy_change_restores_original_policy_without_silent_confirmation(managed):
    admin,_,_,_,_,request=prepare(managed)
    request['policy']=dict(capacity_hours_per_24h=None,capacity_confirmed=False)
    record,_,_=save(admin,request);identity=record['draft_id']
    response=admin.post(BASE+f'/{identity}/policy',json=dict(expected_revision=1,idempotency_key=str(uuid4()),reason='TEST ONLY policy change',policy=pure_case()[3].model_dump(mode='json')))
    assert response.status_code==200,response.text
    response=admin.post(BASE+f'/{identity}/undo',json=command());assert response.status_code==200,response.text
    policy=admin.get(BASE+f'/{identity}/policy?revision=3').json()['policy']
    assert policy==admin.get(BASE+f'/{identity}/policy?revision=1').json()['policy']
    assert not policy['capacity_confirmed'] and policy.get('format_version',1)==1


def test_undo_regulation_policy_uses_same_immutable_history(managed):
    admin,_,_=setup_rule(managed)
    record,_,_=save_portfolio(admin,request_for());identity=record['draft_id']
    response=admin.post(BASE+f'/{identity}/policy',json=dict(expected_revision=1,idempotency_key=str(uuid4()),reason='TEST ONLY explicit policy',policy=pure_case()[3].model_dump(mode='json')))
    assert response.status_code==200,response.text
    response=admin.post(BASE+f'/{identity}/undo',json=command());assert response.status_code==200,response.text
    assert response.json()['source_kind']=='portfolio' and response.json()['revision']==3
    assert admin.get(BASE+f'/{identity}/policy?revision=3').json()['policy']['capacity_status']=='unknown'


def test_locks_require_explicit_consent_and_cas_serializes_competing_undos(managed):
    admin,record,_=edited(managed,locked=True);url=BASE+f"/{record['draft_id']}/undo"
    assert admin.get(url).json()['requires_unlock']
    assert admin.post(url,json=command()).status_code==422
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:admin.post(url,json=command(unlock=True)),range(2)))
    assert sorted(r.status_code for r in responses)==[200,409]


def test_first_historical_other_author_roles_and_csrf_are_not_undoable(managed):
    _,app,_,_,_=managed;admin,record,_=edited(managed);identity=record['draft_id'];url=BASE+f'/{identity}/undo'
    assert admin.get(url+'?revision=1').json()['blocker']=='NOT_HEAD'
    assert admin.post(url,json=command(),headers={'X-CSRF-Token':'bad'}).status_code==403
    with closing(login(app,'executor')) as person:assert person.get(url).status_code==403
    with closing(login(app,'director')) as person:assert person.post(url,json=command()).status_code==403
    with closing(login(app,'chief_engineer')) as foreign:assert foreign.get(url).status_code==404
    assert admin.chief.get(url).json()['blocker']=='OTHER_AUTHOR'
    assert admin.chief.post(url,json=command()).status_code==409
    assert admin.post(url,json=command(3)).status_code==409


def test_changed_sources_or_resources_cannot_restore_an_unsafe_parent(managed):
    engine,_,_,_,ids=managed;admin,record,_=edited(managed);identity=record['draft_id']
    with engine.begin() as c:c.execute(text('UPDATE equipment SET revision=revision+1 WHERE site_id=:site'),ids)
    assert admin.post(BASE+f'/{identity}/undo',json=command()).status_code==409
    assert admin.get(BASE+f'/{identity}/versions').json()['total']==2


def test_any_published_version_blocks_undo_without_touching_live_tasks(managed):
    engine,_,_,_,_=managed;admin,record,proposal,_,_=prepared(managed)
    proposal=approve(admin,proposal)
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    before=active_counts(engine);url=BASE+f"/{record['draft_id']}/undo"
    assert admin.get(url).json()['blocker']=='PUBLISHED_PLAN'
    assert admin.post(url,json=command(record['revision'])).status_code==409
    assert active_counts(engine)==before


def test_solver_adoption_can_be_undone_to_the_same_unplaced_roots(queued):
    engine,_,_,_,_=queued;admin,record,_,run,_=enqueue(queued);finish(engine,run['run_id'])
    response=admin.post(RUNS+run['run_id']+'/apply',json=dict(expected_revision=1,kind='optimized',reason='TEST ONLY solver adoption'))
    assert response.status_code==200,response.text
    response=admin.post(BASE+f"/{record['draft_id']}/undo",json=command());assert response.status_code==200,response.text
    assert response.json()['revision']==3
    report=admin.get(BASE+f"/{record['draft_id']}?revision=3").json()['validation']
    assert report['unplaced_segments']==1 and Decimal(report['total_person_hours'])==3


def test_current_absence_prevents_restoring_an_old_placement(managed):
    engine,_,_,_,ids=managed;admin,record,original=edited(managed);identity=record['draft_id']
    placed=admin.get(BASE+f"/{identity}/occurrences/{original['occurrence_id']}/segments").json()['items'][0]
    response=admin.post(BASE+f'/{identity}/placements',json=dict(expected_revision=2,segment_id=placed['segment_id'],start_local='2027-01-03T09:00',end_local='2027-01-03T12:00',worker_ids=placed['worker_ids'],reason='TEST ONLY second placement'))
    assert response.status_code==200,response.text
    with engine.begin() as c:c.execute(text("INSERT INTO availability_slots(site_id,user_id,starts_at,ends_at,status) VALUES (:site,:worker,'2027-01-02T00:00:00+05:00','2027-01-03T00:00:00+05:00','unavailable')"),dict(site=ids['site'],worker=placed['worker_ids'][0]))
    response=admin.post(BASE+f'/{identity}/undo',json=command(3));assert response.status_code==422,response.text
    assert admin.get(BASE+f'/{identity}/versions').json()['total']==3
