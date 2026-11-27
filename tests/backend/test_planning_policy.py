"""Versioned planning parameters, real access constraints and legacy safety."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from app.schemas.draft_plans import DraftPolicy
from app.scheduling.planning_policy import access_intervals
from app.scheduling.draft_validator import digest
from app.scheduling.optimization import calculate
from tests.backend.test_draft_plans import pure_case,check,prepare,save,worker,BASE
from tests.backend.test_optimization import case
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login
from tests.backend.test_publication import prepared,approve,publishing,PATH

def policy(**changes):
    return DraftPolicy(format_version=2,capacity_hours_per_24h=changes.pop('capacity_hours_per_24h','24'),
        capacity_confirmed=changes.pop('capacity_confirmed',True),capacity_ref='TEST ONLY explicit capacity',
        capacity_status=changes.pop('capacity_status','confirmed'),access_status=changes.pop('access_status','confirmed'),
        access_mode=changes.pop('access_mode','weekly'),access_ref='TEST ONLY approved access',
        service_windows=changes.pop('service_windows',[dict(weekday=6,start_minute=9*60,end_minute=17*60)]),**changes)

def test_legacy_snapshot_and_hash_stay_byte_equivalent_and_cannot_drop_new_constraints():
    original=dict(capacity_hours_per_24h='24',capacity_confirmed=True,capacity_ref='TEST ONLY',day_start_minute=None,night_start_minute=None)
    parsed=DraftPolicy.model_validate(original)
    assert parsed.format_version==1 and parsed.model_dump(mode='json')==original
    assert digest(parsed.model_dump(mode='json'))==digest(original)
    with pytest.raises(ValidationError):DraftPolicy.model_validate(dict(original,access_status='confirmed',access_mode='unrestricted',access_ref='TEST ONLY'))
    with pytest.raises(ValidationError):policy(capacity_confirmed=False)
    assert policy().model_dump(mode='json')['format_version']==2

def test_legacy_policy_requires_review_but_existing_published_snapshot_can_be_checked():
    root,segments,people,_=pure_case()
    legacy=DraftPolicy(capacity_hours_per_24h='24',capacity_confirmed=True,capacity_ref='TEST ONLY legacy approval')
    report=check(root,segments,people,legacy)
    assert 'ACCESS_UNCONFIRMED' in report.issue_counts
    from app.scheduling.draft_validator import validate
    report=validate([root],segments,people,legacy,date(2027,1,1),date(2027,1,3),'UTC',datetime(2026,12,1,tzinfo=timezone.utc),allow_legacy_policy=True)
    assert 'ACCESS_UNCONFIRMED' not in report.issue_counts

def test_published_v2_work_rechecks_object_access_at_actual_start(managed,monkeypatch):
    import app.main as main_module
    import app.integration.published_execution as execution
    import app.integration.analyst as analyst
    engine,_,_,local_login,ids=managed
    admin,record,_,preparation,worker_id=prepared(managed)
    # Site timezone is +05:00; this window allows the planned 09:00–12:00.
    changed=admin.post(BASE+f"/{record['draft_id']}/policy",json=change(record,policy(service_windows=[dict(weekday=6,start_minute=540,end_minute=720)])))
    assert changed.status_code==200,changed.text
    preparation.update(expected_revision=changed.json()['revision'],idempotency_key=str(uuid4()))
    proposal=admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=preparation).json()
    proposal=approve(admin,proposal)
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    with engine.connect() as c:task=str(c.scalar(text('SELECT work_order_id FROM work_orders WHERE site_id=:site'),ids))
    instant=[datetime(2027,1,2,5,tzinfo=timezone.utc)]  # 10:00, finishing at 13:00 is outside access.
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return instant[0].astimezone(tz) if tz else instant[0].replace(tzinfo=None)
    for module in (execution,main_module,analyst):monkeypatch.setattr(module,'datetime',Clock)
    with closing(local_login(worker_id+'@example.test')) as technician:
        response=technician.post('/api/v1/maintenance/tasks/'+task+'/start',json=dict(expected_revision=1))
        assert response.status_code==409,response.text
        assert 'доступ' in response.text.lower(),response.text
        instant[0]=datetime(2027,1,2,4,tzinfo=timezone.utc)
        response=technician.post('/api/v1/maintenance/tasks/'+task+'/start',json=dict(expected_revision=1))
        assert response.status_code==200,response.text

@pytest.mark.parametrize('windows',[
    [dict(weekday=True,start_minute=0,end_minute=60)],
    [dict(weekday=1,start_minute=600,end_minute=600)],
    [dict(weekday=1,start_minute=600,end_minute=2041)],
    [dict(weekday=1,start_minute=600,end_minute=720),dict(weekday=1,start_minute=660,end_minute=780)],
    [dict(weekday=7,start_minute=1380,end_minute=1500),dict(weekday=1,start_minute=0,end_minute=120)],
])
def test_invalid_or_overlapping_windows_cannot_be_confirmed(windows):
    with pytest.raises(ValidationError):policy(service_windows=windows)

def test_validator_distinguishes_unknown_access_from_real_conflict_and_bounds_capacity():
    root,segments,people,_=pure_case()
    report=check(root,segments,people,policy())
    assert report.status=='invalid' and report.issue_counts['OUTSIDE_ACCESS_WINDOW']==2
    assert report.days[1].available_person_hours==16
    # A 24h presence with 8h useful capacity and 8h object access has 8h,
    # not 8/24 * 8; useful capacity is never multiplied by access twice.
    report=check(root,[],people,policy(capacity_hours_per_24h='8'))
    assert report.days[1].available_person_hours==16
    root=root.model_copy(update={'total_person_hours':Decimal('3'),'crew_size':1,'interpretation':'ALLOWED_WINDOW'})
    candidate=segments[0].model_copy(update={'person_hours':Decimal('3'),'start_at':datetime(2027,1,2,9,tzinfo=timezone.utc),
        'end_at':datetime(2027,1,2,12,tzinfo=timezone.utc),'worker_ids':[people[0].worker_id]})
    assert check(root,[candidate],people,policy()).status=='valid'
    unknown=policy(access_status='provisional')
    report=check(root,[candidate],people,unknown)
    assert report.status=='incomplete' and 'ACCESS_UNCONFIRMED' in report.issue_counts
    assert all(day.available_person_hours is None for day in report.days)

def test_overnight_week_boundary_and_timezone_are_not_cut_at_midnight():
    p=policy(service_windows=[dict(weekday=7,start_minute=22*60,end_minute=30*60)])
    values=access_intervals(p,date(2027,1,4),date(2027,1,4),ZoneInfo('Asia/Yekaterinburg'))
    assert values==[(datetime(2027,1,3,17,tzinfo=timezone.utc),datetime(2027,1,4,1,tzinfo=timezone.utc))]
    assert access_intervals(policy(access_mode='unrestricted',service_windows=[]),date(2027,1,1),date(2027,1,2),ZoneInfo('UTC'))

@pytest.mark.parametrize('day,start',[(date(2027,3,28),150),(date(2027,10,31),150)])
def test_dst_gap_or_ambiguity_is_explicit_not_a_guessed_offset(day,start):
    with pytest.raises(ValueError):access_intervals(policy(service_windows=[dict(weekday=7,start_minute=start,end_minute=240)]),day,day,ZoneInfo('Europe/Berlin'))

def test_baseline_and_cp_sat_use_the_same_access_including_off_grid_boundaries():
    payload=case(1);p=policy(service_windows=[dict(weekday=6,start_minute=9*60+7,end_minute=13*60)])
    payload['source_snapshot']['input']['policy']=p.model_dump(mode='json')
    result=calculate(payload)
    for kind in ('baseline','optimized'):
        assert result['result'][kind]['validation']['status']=='valid'
        segment=result[kind+'_segments'][0]
        start=datetime.fromisoformat(segment['start_at']);end=datetime.fromisoformat(segment['end_at'])
        assert start.date()==end.date()==date(2027,1,2) and start.hour>=9 and end.hour<=13
    payload['source_snapshot']['input']['policy']['access_status']='provisional'
    result=calculate(payload)
    assert result['result']['completion_reason']=='needs_input' and result['result']['optimized'] is None

def change(record,p=None,**changes):
    return dict(expected_revision=record['revision'],idempotency_key=str(uuid4()),reason='TEST ONLY reviewed policy',policy=(p or policy()).model_dump(mode='json'),**changes)

def test_policy_edit_creates_immutable_version_and_does_not_touch_active_schedule(managed):
    engine,_,_,_,ids=managed;admin,_,_,_,_,request=prepare(managed)
    record,_,_=save(admin,request);identity=record['draft_id']
    before=admin.get(BASE+f'/{identity}/policy').json()
    assert before['policy']['format_version']==2
    with engine.connect() as c:counts={t:c.scalar(text(f'SELECT count(*) FROM {t} WHERE site_id=:site'),ids) for t in ('work_orders','work_assignments','schedule_entries')}
    command=change(record);response=admin.post(BASE+f'/{identity}/policy',json=command)
    assert response.status_code==200,response.text
    assert response.json()['revision']==2
    assert admin.get(BASE+f'/{identity}/policy?revision=1').json()==before
    assert admin.get(BASE+f'/{identity}/policy').json()['policy']['access_status']=='confirmed'
    assert admin.post(BASE+f'/{identity}/policy',json=command).json()['revision']==2
    assert admin.post(BASE+f'/{identity}/policy',json=dict(command,reason='Different request')).status_code==409
    assert admin.post(BASE+f'/{identity}/policy',json=change(record)).status_code==409
    with engine.connect() as c:assert counts=={t:c.scalar(text(f'SELECT count(*) FROM {t} WHERE site_id=:site'),ids) for t in counts}

def test_policy_edit_rechecks_revision_site_role_csrf_source_and_event_boundaries(managed):
    _,app,_,_,_=managed;admin,_,_,_,_,request=prepare(managed);record,_,_=save(admin,request);identity=record['draft_id'];command=change(record)
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:admin.post(BASE+f'/{identity}/policy',json=change(record)),range(2)))
    assert sorted(r.status_code for r in responses)==[200,409]
    current=admin.get(BASE+f'/{identity}/policy').json()['record']
    with closing(login(app,'director')) as other:
        assert other.post(BASE+f'/{identity}/policy',json=change(current)).status_code==403
        assert other.get(BASE+f'/{identity}/policy').status_code==404
    token=admin.headers.pop('X-CSRF-Token')
    try:assert admin.post(BASE+f'/{identity}/policy',json=change(current)).status_code==403
    finally:admin.headers['X-CSRF-Token']=token
    changed=policy(day_start_minute=480,night_start_minute=1200)
    assert admin.post(BASE+f'/{identity}/policy',json=change(current,changed)).status_code==422
    record_source=admin.get(BASE+f'/{identity}/occurrences').json()['items'][0]
    source=admin.get('/api/v1/maintenance/catalog-imports/'+record_source['import_id']+'/operations?q=0190').json()['items'][0]
    # A changed source must not be refreshed by a parameters-only command.
    engine=managed[0]
    with engine.begin() as c:c.execute(text('UPDATE equipment SET revision=revision+1 WHERE site_id=:site'),managed[4])
    assert admin.post(BASE+f'/{identity}/policy',json=change(current)).status_code==409

def test_new_policy_invalidates_consent_and_is_visible_in_the_exact_proposal(managed):
    admin,record,proposal,preparation,_=prepared(managed)
    row=preparation['profiles'][0]['row_number']
    proposal=approve(admin,proposal)
    identity=record['draft_id'];command=change(record,policy(access_mode='unrestricted',service_windows=[]))
    response=admin.post(BASE+f'/{identity}/policy',json=command)
    assert response.status_code==200,response.text
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==409
    from tests.backend.test_publication import profile
    body=dict(expected_revision=response.json()['revision'],idempotency_key=str(uuid4()),reason='TEST ONLY',scope_note='TEST ONLY',profiles=[profile(row)])
    response=admin.post(BASE+f'/{identity}/publication-proposals',json=body)
    assert response.status_code==201,response.text
    assert response.json()['planning_policy']==command['policy'] and response.json()['blocker_count']==0
    assert admin.get(PATH+response.json()['proposal_id']).json()['planning_policy']==command['policy']
    # Idempotent retries must expose exactly the same consent parameters too.
    assert admin.post(BASE+f'/{identity}/publication-proposals',json=body).json()['planning_policy']==command['policy']
