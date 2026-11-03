"""QA audit: regulation schedule generation for the six source operations.

Reference dates are tied to an explicit policy, not to a tester's guess:

* daily operations (1.1-1.3): ``calendar_interval`` day/1, ``fixed_calendar``,
  zero lead (``docs/service/planning.md``, section "Действие, история и
  обязательный срок"; ``tests/fixtures/domain/maintenance_cases.json`` TC-01).
* operation 1.4 (5/year): ``yearly_count`` with ``count_per_year=5`` and the
  anchor year 2026.  The documented distribution uses
  ``floor(i * eligible_days / count_per_year)`` over the real 365/366-day year
  (``docs/service/planning.md``, section "Эталонные календарные сценарии").
  The October fixture date is TC-04: 2026-10-20.
* operation 1.5 (1/quarter): real calendar quarters, quarter end
  (``docs/service/planning.md``, section "Эталонные календарные сценарии";
  TC-02: 2026-12-31).
* operation 1.6 (1/quarter): the fixture policy is ``month``/3 from
  2026-07-04 (TC-03: 2026-10-04), while the source wording also permits a real
  calendar-quarter policy.  The two policies are tested separately; the tests
  never infer one policy from the other.

The tests assert only facts defined by those policies.  Missing input must be
reported as a diagnostic and must not create dates or numeric work.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.scheduling import CalendarGenerationRequest, generate_month
from app.schemas.maintenance import CalendarPattern
from app.scheduling.recurrence import occurrence_dates

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads((ROOT / "tests/fixtures/scheduling/examples.json").read_text(encoding="utf-8"))
BASE_REQUEST = FIXTURES["request"]
BASE_OPERATION = BASE_REQUEST["bindings"][0]["operation"]
BASE_RULE = BASE_REQUEST["bindings"][0]["rule"]
RULE_META = ("schema_version", "data_origin", "rule_version_id", "regulation_version_id",
             "source_text", "confirmed", "source_ref")

DAILY = dict(kind="calendar_interval", interval=1, calendar_unit="day",
             anchor_date="2026-01-01", basis="fixed_calendar", explicit_dates=[],
             yearly_count=None, runtime_interval_hours=None, allowed_lead_days=0)
QUARTER = dict(kind="calendar_pattern", interval=None, calendar_unit=None,
               anchor_date=None, basis=None, explicit_dates=[], yearly_count=None,
               runtime_interval_hours=None, allowed_lead_days=0,
               pattern=dict(frequency="quarter", anchor_date="2026-01-01", interval=1,
                            period_edge="end"))
FIVE_PER_YEAR = dict(kind="calendar_pattern", interval=None, calendar_unit=None,
                     anchor_date=None, basis=None, explicit_dates=[], yearly_count=None,
                     runtime_interval_hours=None, allowed_lead_days=6,
                     pattern=dict(frequency="yearly_count", anchor_date="2026-01-01",
                                  interval=1, count_per_year=5))
MONTH_THREE = dict(kind="calendar_pattern", interval=None, calendar_unit=None,
                   anchor_date=None, basis=None, explicit_dates=[], yearly_count=None,
                   runtime_interval_hours=None, allowed_lead_days=0,
                   pattern=dict(frequency="month", anchor_date="2026-07-04", interval=3))
ANNUAL_EXPLICIT = deepcopy(FIXTURES["rules"]["annual_explicit"])

OPERATIONS = {
    "1.1": dict(code="1.1", maintenance_type="ТО1", crew_size=1,
                raw_norm_value="1.0", norm_unit="unconfirmed",
                planning_duration_minutes=None, duration_basis=None),
    "1.2": dict(code="1.2", maintenance_type="ТО1", crew_size=1,
                raw_norm_value="1.0", norm_unit="unconfirmed",
                planning_duration_minutes=None, duration_basis=None),
    "1.3": dict(code="1.3", maintenance_type="ТО1", crew_size=1,
                raw_norm_value="1.0", norm_unit="unconfirmed",
                planning_duration_minutes=None, duration_basis=None),
    "1.4": dict(code="1.4", maintenance_type="ТО2", crew_size=2,
                raw_norm_value="60.0", norm_unit="unconfirmed",
                planning_duration_minutes=None, duration_basis=None),
    "1.5": dict(code="1.5", maintenance_type="ТО2", crew_size=1,
                raw_norm_value="48.0", norm_unit="unconfirmed",
                planning_duration_minutes=None, duration_basis=None),
    "1.6": dict(code="1.6", maintenance_type="ТО2", crew_size=1,
                raw_norm_value="30.0", norm_unit="unconfirmed",
                planning_duration_minutes=None, duration_basis=None),
}


def request(rule, operation, *, year=2026, month=10, active_from="2026-01-01",
            as_of=None, accepted_events=None):
    data = deepcopy(BASE_REQUEST)
    data["query"].update(year=year, month=month)
    data["as_of"] = as_of or f"{year}-{month:02d}-01T00:00:00+05:00"
    item = data["bindings"][0]
    item["binding"]["effective_from"] = active_from
    item["equipment"]["commissioned_on"] = active_from
    item["operation"].update(operation)
    # Keep the rule identity/version fields and replace only the schedule
    # definition, so every scenario exercises the documented policy.
    item["rule"] = {**{key: BASE_RULE[key] for key in RULE_META}, **deepcopy(rule)}
    item["accepted_events"] = accepted_events or []
    return data


def run(data):
    return generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(data)))


def dates(result):
    return [entry.occurrence.occurrence_date for entry in result.bindings[0].occurrences]


def event(performed, accepted=None):
    return dict(service_event_id="00000000-0000-4000-8000-000000000099",
                performed_at=performed, accepted_at=accepted or performed,
                runtime_hours=None, observed_need_date=None)


@pytest.mark.parametrize("code,rule,month,expected", [
    ("1.1", DAILY, 10, [date(2026, 10, day) for day in range(1, 32)]),
    ("1.2", DAILY, 10, [date(2026, 10, day) for day in range(1, 32)]),
    ("1.3", DAILY, 10, [date(2026, 10, day) for day in range(1, 32)]),
    ("1.4", FIVE_PER_YEAR, 10, [date(2026, 10, 20)]),
    ("1.5", QUARTER, 12, [date(2026, 12, 31)]),
    ("1.6", MONTH_THREE, 10, [date(2026, 10, 4)]),
])
def test_six_source_operations_have_reproducible_dates(code, rule, month, expected):
    result = run(request(rule, OPERATIONS[code], month=month))
    binding = result.bindings[0]
    assert binding.status == "ok", (code, binding.error_code, binding.explanation)
    assert dates(result) == expected
    assert all(item.crew_size == OPERATIONS[code]["crew_size"] for item in result.calendar.items)
    # The source norm unit is unconfirmed, so no total hours may be invented.
    assert binding.total_person_hours is None
    assert binding.total_planning_person_minutes is None


def test_1_4_yearly_count_uses_the_documented_even_distribution():
    # docs/service/planning.md: floor(i * eligible_days / count_per_year).
    full_year = []
    for month in range(1, 13):
        full_year.extend(dates(run(request(FIVE_PER_YEAR, OPERATIONS["1.4"], month=month))))
    assert full_year == [date(2026, 1, 1), date(2026, 3, 15), date(2026, 5, 27),
                         date(2026, 8, 8), date(2026, 10, 20)]
    assert len(full_year) == 5
    gaps = [(right - left).days for left, right in zip(full_year, full_year[1:] + [date(2027, 1, 1)])]
    assert max(gaps) - min(gaps) <= 1


def test_1_4_requires_two_workers_in_the_operation_contract():
    operations = json.loads((ROOT / "tests/fixtures/domain/maintenance_operations.json").read_text(encoding="utf-8"))["maintenance_operations"]
    operation = next(row for row in operations if row["code"] == "1.4")
    assert operation["frequency_value"] == "5/год"
    assert operation["required_workers"] == 2
    result = run(request(FIVE_PER_YEAR, OPERATIONS["1.4"], month=10))
    assert result.calendar.items[0].crew_size == 2
    assert result.calendar.items[0].raw_norm_value == Decimal("60.0")


def test_quarter_boundaries_are_real_calendar_quarters():
    pattern = CalendarPattern.model_validate_json(json.dumps(QUARTER["pattern"]))
    assert occurrence_dates(pattern, date(2026, 1, 1), date(2027, 3, 31)) == [
        date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30),
        date(2026, 12, 31), date(2027, 3, 31),
    ]
    start_edge = pattern.model_copy(update={"period_edge": "start"})
    assert occurrence_dates(start_edge, date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1),
    ]


def test_month_interval_three_keeps_phase_across_the_year_boundary():
    pattern = CalendarPattern.model_validate_json(json.dumps(MONTH_THREE["pattern"]))
    assert occurrence_dates(pattern, date(2026, 7, 4), date(2027, 1, 4)) == [
        date(2026, 7, 4), date(2026, 10, 4), date(2027, 1, 4),
    ]


def test_yearly_count_anchor_is_a_rule_start_and_is_not_backfilled():
    # docs/service/planning.md: dates before the rule start are cut without
    # compacting the rest of the year; the next full year has the full count.
    rule = deepcopy(FIVE_PER_YEAR)
    rule["pattern"]["anchor_date"] = "2026-06-01"
    pattern = CalendarPattern.model_validate_json(json.dumps(rule["pattern"]))
    assert occurrence_dates(pattern, date(2026, 6, 1), date(2026, 12, 31)) == [
        date(2026, 8, 8), date(2026, 10, 20),
    ]
    assert len(occurrence_dates(pattern, date(2027, 1, 1), date(2027, 12, 31))) == 5


def test_explicit_annual_dates_do_not_leak_into_the_next_year():
    result = run(request(ANNUAL_EXPLICIT, OPERATIONS["1.4"], year=2027, month=11))
    binding = result.bindings[0]
    assert binding.status == "needs_input"
    assert binding.error_code == "YEAR_DATES_MISSING"
    assert binding.occurrences == []
    assert binding.total_person_hours is None
    assert binding.total_planning_person_minutes is None


def test_yearly_count_reports_unsatisfiable_season_instead_of_reducing_count():
    rule = deepcopy(FIVE_PER_YEAR)
    rule["pattern"].update(months=[2], month_days=[29], short_month="skip")
    result = run(request(rule, OPERATIONS["1.4"], month=2))
    binding = result.bindings[0]
    assert binding.status == "needs_input"
    assert binding.error_code == "CALENDAR_PATTERN_UNSATISFIABLE"
    assert binding.occurrences == []
    assert binding.total_person_hours is None


def test_short_month_skip_is_explicit_and_does_not_create_a_date():
    rule = dict(MONTH_THREE, pattern=dict(frequency="month", anchor_date="2026-01-31",
                                          interval=1, short_month="skip"))
    result = run(request(rule, OPERATIONS["1.5"], month=2))
    binding = result.bindings[0]
    assert binding.status == "ok"
    assert binding.occurrences == []
    assert "NORM_UNIT_UNCONFIRMED" in binding.warnings


def test_empty_month_reports_missing_norm_inputs_instead_of_zero_values():
    result = run(request(FIVE_PER_YEAR, OPERATIONS["1.4"], month=11))
    binding = result.bindings[0]
    assert binding.status == "ok"
    assert binding.occurrences == []
    assert "NORM_UNIT_UNCONFIRMED" in binding.warnings
    assert "DURATION_UNCONFIRMED" in binding.warnings


@pytest.mark.xfail(strict=True, reason="BUG-04: empty month returns 0 instead of None for unconfirmed norm/duration")
def test_empty_month_does_not_report_zero_when_norm_is_unknown():
    result = run(request(FIVE_PER_YEAR, OPERATIONS["1.4"], month=11))
    binding = result.bindings[0]
    assert binding.total_person_hours is None
    assert binding.total_planning_person_minutes is None


def test_deadline_passed_is_recalculated_at_local_midnight_without_new_ids():
    first_data = request(DAILY, OPERATIONS["1.1"], month=10, as_of="2026-10-01T23:59:00+05:00")
    first = run(first_data)
    assert not first.bindings[0].occurrences[0].deadline_passed
    second_data = request(DAILY, OPERATIONS["1.1"], month=10, as_of="2026-10-02T00:00:00+05:00")
    second = run(second_data)
    assert second.bindings[0].occurrences[0].deadline_passed
    assert not second.bindings[0].occurrences[1].deadline_passed
    assert [entry.occurrence.occurrence_id for entry in first.bindings[0].occurrences] == [
        entry.occurrence.occurrence_id for entry in second.bindings[0].occurrences
    ]


def test_overdue_rolling_obligation_requires_review_and_is_not_rescheduled():
    rolling = dict(kind="calendar_interval", interval=3, calendar_unit="month",
                   anchor_date="2026-01-10", basis="after_accepted_completion",
                   explicit_dates=[], yearly_count=None, runtime_interval_hours=None,
                   allowed_lead_days=0)
    data = request(rolling, OPERATIONS["1.5"], month=12,
                   as_of="2026-12-20T00:00:00+05:00",
                   accepted_events=[event("2026-09-10T09:00:00+05:00",
                                          "2026-09-11T09:00:00+05:00")])
    binding = run(data).bindings[0]
    assert binding.status == "manual_review"
    assert binding.error_code == "OVERDUE_REQUIRES_REVIEW"
    assert binding.next_due_date == date(2026, 12, 10)
    assert [entry.occurrence.occurrence_date for entry in binding.occurrences] == [date(2026, 12, 10)]
    assert binding.occurrences[0].deadline_passed
    assert "ROLLING_NEXT_OCCURRENCE_ONLY" in binding.warnings


@pytest.mark.parametrize("unit,expected", [
    ("person_hour", Decimal("60.0")),
    ("elapsed_hour", Decimal("120.0")),
])
def test_1_4_norm_hours_use_the_declared_unit_and_crew_size(unit, expected):
    operation = dict(OPERATIONS["1.4"], norm_unit=unit)
    binding = run(request(FIVE_PER_YEAR, operation, month=10)).bindings[0]
    assert binding.total_person_hours == expected
    assert binding.occurrences[0].required_person_hours == expected


def test_1_4_planning_minutes_are_crew_size_times_duration():
    operation = dict(OPERATIONS["1.4"], planning_duration_minutes=90,
                     duration_basis="synthetic_demo: confirmed 90 minutes")
    binding = run(request(FIVE_PER_YEAR, operation, month=10)).bindings[0]
    assert binding.total_person_hours is None
    assert binding.total_planning_person_minutes == 180
    assert binding.occurrences[0].planning_person_minutes == 180


def test_daily_norm_hours_sum_all_occurrences_without_merging_ids():
    operation = dict(OPERATIONS["1.1"], norm_unit="person_hour")
    binding = run(request(DAILY, operation, month=10)).bindings[0]
    assert binding.total_person_hours == Decimal("31.0")
    assert len({entry.occurrence.occurrence_id for entry in binding.occurrences}) == 31
