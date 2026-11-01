from datetime import date,time,datetime
from zoneinfo import ZoneInfo

from app.scheduling.shifts import expand_shift,employment_availability


def shift(**values):
    return dict(is_active=True,valid_from=date(2026,1,1),valid_until=None,
        calendar_pattern=dict(frequency='week',anchor_date='2026-01-01',weekdays=[1,2,3,4,5]),
        starts_local=time(9),ends_local=time(17),status='available',**values)


def test_shift_uses_the_same_iso_week_rules_as_maintenance():
    rule=shift()
    rule['calendar_pattern']['week_parity']='even'
    rows,diagnostics=expand_shift(rule,date(2026,10,1),date(2026,10,31),'Asia/Yekaterinburg')
    assert len(rows)==12 and not diagnostics
    assert all(row['start_at'].isocalendar().week%2==0 for row in rows)


def test_overnight_shift_and_inclusive_employment_end():
    rule=shift()
    rule.update(starts_local=time(22),ends_local=time(6),valid_until=date(2026,11,2))
    rows,_=expand_shift(rule,date(2026,11,2),date(2026,11,3),'Asia/Yekaterinburg')
    assert rows[0]['start_at'].isoformat()=='2026-11-02T22:00:00+05:00'
    assert rows[0]['end_at'].isoformat()=='2026-11-03T00:00:00+05:00'
    unlimited=dict(rule,valid_until=None)
    rows,_=expand_shift(unlimited,date(2026,11,3),date(2026,11,3),'Asia/Yekaterinburg')
    assert rows[0]['start_at'].day==2 and rows[0]['end_at'].day==3


def test_dst_ambiguous_and_missing_times_are_blocked_not_guessed():
    rule=shift()
    rule.update(calendar_pattern=dict(frequency='day',anchor_date='2026-01-01'),starts_local=time(2,30),ends_local=time(4))
    for day,code in [(date(2026,3,29),'DST_GAP'),(date(2026,10,25),'DST_AMBIGUOUS')]:
        rows,issues=expand_shift(rule,day,day,'Europe/Berlin')
        assert any(i['code']==code for i in issues)
        assert any(r['status']=='unavailable' and r['start_at'].date()==day for r in rows)


def test_availability_is_clipped_to_employment_not_only_shift_dates():
    tz=ZoneInfo('Asia/Yekaterinburg')
    rows=[dict(start_at=datetime(2026,11,1,22,tzinfo=tz),end_at=datetime(2026,11,3,6,tzinfo=tz),status='available')]
    result=employment_availability(rows,date(2026,11,2),date(2026,11,2),str(tz))
    assert result[0]['start_at']==datetime(2026,11,2,0,tzinfo=tz)
    assert result[0]['end_at']==datetime(2026,11,3,0,tzinfo=tz)
