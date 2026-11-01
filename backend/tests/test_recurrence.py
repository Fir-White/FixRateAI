from datetime import date
import json

import pytest
from pydantic import ValidationError

from app.schemas.maintenance import CalendarPattern
from app.scheduling.recurrence import occurrence_dates


def pattern(**values):
    return CalendarPattern.model_validate_json(json.dumps({"frequency":"week","anchor_date":"2026-01-01",**values}))


def test_iso_parity_across_iso_year_and_week_53():
    rule=pattern(weekdays=[1],week_parity="odd")
    assert occurrence_dates(rule,date(2026,12,21),date(2027,1,11))==[date(2026,12,28),date(2027,1,4)]
    assert occurrence_dates(rule.model_copy(update={"week_parity":"even"}),date(2026,12,21),date(2027,1,11))==[date(2026,12,21),date(2027,1,11)]


def test_two_week_cycle_is_continuous_across_year_unlike_iso_parity():
    rule=CalendarPattern.model_validate_json('{"frequency":"week","anchor_date":"2026-12-21","interval":2,"weekdays":[1,3]}')
    assert occurrence_dates(rule,date(2026,12,21),date(2027,1,10))==[date(2026,12,21),date(2026,12,23),date(2027,1,4),date(2027,1,6)]


def test_quarters_are_actual_calendar_quarters():
    rule=CalendarPattern.model_validate_json('{"frequency":"quarter","anchor_date":"2026-01-01"}')
    assert occurrence_dates(rule,date(2026,1,1),date(2026,12,31))==[date(2026,3,31),date(2026,6,30),date(2026,9,30),date(2026,12,31)]
    first=rule.model_copy(update={"period_edge":"start"})
    assert occurrence_dates(first,date(2026,1,1),date(2026,12,31))==[date(2026,m,1) for m in (1,4,7,10)]


@pytest.mark.parametrize("year",[2026,2028])
def test_five_per_calendar_year_use_actual_year_length(year):
    rule=CalendarPattern.model_validate_json('{"frequency":"yearly_count","anchor_date":"2026-01-01","count_per_year":5}')
    days=occurrence_dates(rule,date(year,1,1),date(year,12,31))
    assert len(days)==len(set(days))==5 and days[0]==date(year,1,1)
    intervals=[(b-a).days for a,b in zip(days,days[1:]+[date(year+1,1,1)])]
    assert max(intervals)-min(intervals)<=1


def test_short_month_does_not_accumulate_anchor_drift():
    rule=CalendarPattern.model_validate_json('{"frequency":"month","anchor_date":"2028-01-31"}')
    assert occurrence_dates(rule,date(2028,1,1),date(2028,4,30))==[date(2028,1,31),date(2028,2,29),date(2028,3,31),date(2028,4,30)]
    assert occurrence_dates(rule.model_copy(update={"short_month":"skip"}),date(2028,1,1),date(2028,4,30))==[date(2028,1,31),date(2028,3,31)]


def test_annual_exclusion_redistributes_without_losing_required_count():
    rule=CalendarPattern.model_validate_json('{"frequency":"yearly_count","anchor_date":"2026-01-01","count_per_year":5,"excluded_dates":["2026-01-01","2026-10-20"]}')
    days=occurrence_dates(rule,date(2026,1,1),date(2026,12,31))
    assert len(days)==5 and not set(days)&set(rule.excluded_dates)


def test_seasons_month_days_exclusions_and_date_lists():
    rule=CalendarPattern.model_validate_json('{"frequency":"year","anchor_date":"2026-01-01","months":[3,6,9,12],"month_days":[15,-1],"excluded_dates":["2026-06-15"]}')
    result=occurrence_dates(rule,date(2026,1,1),date(2026,12,31))
    assert len(result)==7 and date(2026,6,15) not in result and date(2026,12,31) in result
    dates=CalendarPattern.model_validate_json('{"frequency":"dates","anchor_date":"2026-01-01","dates":["2026-02-01","2026-06-15"]}')
    assert occurrence_dates(dates,date(2026,1,1),date(2026,12,31))==[date(2026,2,1),date(2026,6,15)]


@pytest.mark.parametrize("change",[{"weekdays":[1,1]},{"month_days":[0]},{"frequency":"yearly_count"},{"frequency":"dates"},{"frequency":"month","months":[1]}])
def test_ambiguous_or_contradictory_patterns_are_rejected(change):
    with pytest.raises(ValidationError):
        pattern(**change)


def test_pattern_flows_through_real_calendar_contract_and_alg02():
    from pathlib import Path
    from app.scheduling import CalendarGenerationRequest,generate_month
    payload=json.loads(Path('docs/algorithms/examples.json').read_text(encoding='utf-8'))['request']
    rule=payload['bindings'][0]['rule']
    rule.update(kind='calendar_pattern',interval=None,calendar_unit=None,anchor_date=None,basis=None,
        pattern=dict(frequency='week',anchor_date='2026-10-01',weekdays=[1,3],week_parity='even'))
    result=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(payload)))
    assert [str(o.occurrence.occurrence_date) for o in result.bindings[0].occurrences]==['2026-10-12','2026-10-14','2026-10-26','2026-10-28']


def test_annual_count_combines_seasons_iso_parity_and_weekdays():
    rule=CalendarPattern.model_validate_json('{"frequency":"yearly_count","anchor_date":"2026-01-01","count_per_year":5,"months":[3,4,5,9,10],"weekdays":[2],"week_parity":"even"}')
    days=occurrence_dates(rule,date(2026,1,1),date(2026,12,31))
    assert len(days)==5 and all(d.isoweekday()==2 and d.isocalendar().week%2==0 and d.month in rule.months for d in days)


def test_annual_pattern_reports_insufficient_days_instead_of_reducing_count():
    rule=CalendarPattern.model_validate_json('{"frequency":"yearly_count","anchor_date":"2026-01-01","count_per_year":5,"months":[2],"month_days":[29],"short_month":"skip"}')
    with pytest.raises(ValueError,match='Недостаточно'):
        occurrence_dates(rule,date(2026,1,1),date(2026,12,31))
