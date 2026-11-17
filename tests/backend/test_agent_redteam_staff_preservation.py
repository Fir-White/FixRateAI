from datetime import date
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed,join,PREFIX
from tests.backend.test_assistant import assistant_case,thread,proposal,confirm

@pytest.mark.parametrize('change,status,expected',[
    ({},200,('2026-01-01','2027-01-01')),
    ({'employed_from':None},200,(None,'2027-01-01')),
    ({'employed_until':None},200,('2026-01-01',None)),
    ({'employed_until':'2025-12-31'},422,('2026-01-01','2027-01-01')),
    ({'employed_from':'2027-01-02'},422,('2026-01-01','2027-01-01')),
])
def test_staff_role_edit_preserves_omitted_dates_and_checks_merged_range(managed,change,status,expected):
    engine,app,admin,_,ids=managed
    identity,_=join(managed)
    path=PREFIX+f'/management/staff/{identity}'
    setup=admin.put(path,json=dict(expected_revision=1,role='executor',is_active=True,employed_from='2026-01-01',employed_until='2027-01-01'))
    assert setup.status_code==200,setup.text
    response=admin.put(path,json=dict(expected_revision=2,role='engineer',is_active=True,**change))
    assert response.status_code==status,response.text
    with engine.connect() as db:
        row=db.execute(text('SELECT employed_from,employed_until,revision FROM site_memberships WHERE site_id=:site AND user_id=:id'),dict(site=ids['site'],id=identity)).one()
        actual=tuple(day.isoformat() if day else None for day in row[:2])
        assert actual==expected
        assert row[2]==(3 if status==200 else 2)


def test_assistant_role_proposal_preserves_dates_and_replays_once(assistant_case):
    engine,_,admin,_,ids=assistant_case
    identity,_=join(assistant_case)
    def state():
        with engine.connect() as db:return db.execute(text('SELECT role,is_active,employed_from,employed_until,revision FROM site_memberships WHERE site_id=:site AND user_id=:id'),dict(site=ids['site'],id=identity)).one()
    before=state()
    record=proposal(admin,thread(admin),'staff_edit',dict(path=dict(user_id=str(identity)),body=dict(expected_revision=1,role='engineer',is_active=True)))
    assert state()==before
    for _ in range(2):
        result=confirm(admin,record)
        assert result.status_code==200 and result.json()['status']=='succeeded',result.text
    after=state()
    assert after[0]=='engineer' and after[1] is True and after[2:4]==before[2:4] and after[4]==2
