"""ALG01/02 calendar behavior against canonical maintenance-0.1 DTOs."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.maintenance import PlanOccurrence, RecurrenceRule
from app.schemas.maintenance_api import CalendarResponse
from app.scheduling import CalendarGenerationRequest, CalendarGenerationResult, generate_month

EXAMPLES = Path(__file__).resolve().parents[2] / "tests/fixtures/scheduling/examples.json"


def payload(year=2026, month=10, **rule_changes):
    data = deepcopy(json.loads(EXAMPLES.read_text(encoding="utf-8"))["request"])
    data["query"].update(year=year, month=month)
    data["bindings"][0]["rule"].update(rule_changes)
    return data


def run(data):
    return generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(data)))


def dates(result):
    return [item.occurrence_date for item in result.calendar.items]


def event(performed, accepted=None, *, key=None):
    return dict(service_event_id=str(key or uuid4()), performed_at=performed,
                accepted_at=accepted or performed, runtime_hours=None, observed_need_date=None)


def test_documented_request_and_response_match_existing_contracts():
    example = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    result = run(example["request"])
    assert result.calendar.total == example["expected"]["total"] == 31
    assert str(dates(result)[0]) == example["expected"]["first_date"]
    assert str(dates(result)[-1]) == example["expected"]["last_date"]
    assert result.bindings[0].total_person_hours is None
    assert CalendarResponse.model_validate_json(result.calendar.model_dump_json()) == result.calendar
    for entry in result.bindings[0].occurrences:
        assert PlanOccurrence.model_validate_json(entry.occurrence.model_dump_json()) == entry.occurrence
    assert CalendarGenerationResult.model_validate_json(result.model_dump_json()) == result
    assert result.data_origin == "synthetic_demo"
    assert result.bindings[0].is_assumption


@pytest.mark.parametrize("year,month,count", [(2026, 10, 31), (2026, 4, 30), (2026, 2, 28), (2028, 2, 29)])
def test_daily_covers_every_calendar_day_including_weekends(year, month, count):
    result = run(payload(year, month))
    assert dates(result) == [date(year, month, day) for day in range(1, count + 1)]
    assert all(e.occurrence.earliest_date == e.occurrence.mandatory_due_date == e.occurrence.occurrence_date
               for e in result.bindings[0].occurrences)


def test_three_operations_make_93_distinct_obligations():
    data = payload()
    for number in (2, 3):
        item = deepcopy(data["bindings"][0])
        item["binding"]["binding_id"] = str(UUID(int=number))
        item["operation"]["code"] = f"1.{number}"
        item["operation"]["operation_version_id"] = item["binding"]["operation_version_id"] = str(UUID(int=number + 10))
        item["rule"]["rule_version_id"] = item["binding"]["rule_version_id"] = str(UUID(int=number + 20))
        data["bindings"].append(item)
    result = run(data)
    assert result.calendar.total == 93
    assert len({item.occurrence_id for item in result.calendar.items}) == 93
    assert all(len(item.occurrences) == 31 for item in result.bindings)


@pytest.mark.parametrize("target", ["binding", "equipment"])
def test_activation_on_fifteenth_does_not_backfill(target):
    data = payload()
    field = "effective_from" if target == "binding" else "commissioned_on"
    data["bindings"][0][target][field] = "2026-10-15"
    assert dates(run(data)) == [date(2026, 10, day) for day in range(15, 32)]


def test_binding_end_is_inclusive_and_outside_month_is_skipped():
    data = payload()
    data["bindings"][0]["binding"]["effective_to"] = "2026-10-10"
    assert dates(run(data)) == [date(2026, 10, day) for day in range(1, 11)]
    data["query"]["month"] = 11
    result = run(data)
    assert result.calendar.total == 0
    assert result.bindings[0].status == "skipped"
    assert result.bindings[0].error_code == "OUTSIDE_ACTIVE_PERIOD"


def test_missing_activation_does_not_infer_it_from_rule_anchor():
    data = payload()
    data["bindings"][0]["equipment"]["commissioned_on"] = None
    data["bindings"][0]["binding"]["effective_from"] = None
    assert run(data).bindings[0].error_code == "ACTIVATION_DATE_MISSING"


@pytest.mark.parametrize("month,expected", [(1, 31), (4, 30), (7, 31), (10, 31)])
def test_quarterly_dates_preserve_original_anchor_after_short_month(month, expected):
    result = run(payload(month=month, calendar_unit="month", interval=3, anchor_date="2026-01-31"))
    assert dates(result) == [date(2026, month, expected)]


def test_fixed_calendar_keeps_phase_after_activation_and_accepted_late_work():
    data = payload(month=7, calendar_unit="month", interval=3, anchor_date="2026-01-31")
    data["bindings"][0]["binding"]["effective_from"] = "2026-05-01"
    data["bindings"][0]["accepted_events"] = [event("2026-05-10T09:00:00+05:00", "2026-05-15T12:00:00+05:00")]
    assert dates(run(data)) == [date(2026, 7, 31)]


def test_quarterly_crosses_year_without_using_90_days():
    assert dates(run(payload(2027, 1, calendar_unit="month", interval=3, anchor_date="2026-10-31"))) == [date(2027, 1, 31)]


def test_weekly_calendar_keeps_anchor_phase_across_months():
    result = run(payload(interval=7, anchor_date="2026-09-29", source_text="каждые 7 дней"))
    assert dates(result) == [date(2026, 10, day) for day in (6, 13, 20, 27)]


def test_leap_day_anchor_recovers_in_next_leap_year():
    changes = dict(calendar_unit="month", interval=12, anchor_date="2024-02-29")
    data = payload(2025, 2, **changes)
    data["bindings"][0]["equipment"]["commissioned_on"] = "2024-01-01"
    data["bindings"][0]["binding"]["effective_from"] = "2024-01-01"
    assert dates(run(data)) == [date(2025, 2, 28)]
    data["query"]["year"] = 2028
    assert dates(run(data)) == [date(2028, 2, 29)]


def test_after_completion_uses_performed_date_and_only_next_obligation():
    data = payload(month=12, calendar_unit="month", interval=3, basis="after_accepted_completion")
    data["as_of"] = "2026-10-31T12:00:00+05:00"
    data["bindings"][0]["accepted_events"] = [event("2026-09-30T09:00:00+05:00", "2026-10-03T12:00:00+05:00")]
    result = run(data)
    assert dates(result) == [date(2026, 12, 30)]
    assert result.bindings[0].next_due_date == date(2026, 12, 30)
    assert "ROLLING_NEXT_OCCURRENCE_ONLY" in result.bindings[0].warnings


def test_after_completion_does_not_manufacture_future_completions():
    data = payload(calendar_unit="month", interval=1, basis="after_accepted_completion")
    data["bindings"][0]["accepted_events"] = [event("2026-07-10T09:00:00+05:00")]
    result = run(data)
    assert result.calendar.total == 0
    assert result.bindings[0].next_due_date == date(2026, 8, 10)
    assert result.bindings[0].status == "manual_review"


def test_after_completion_selects_latest_performed_fact_not_latest_acceptance():
    data = payload(month=12, calendar_unit="month", interval=3, basis="after_accepted_completion")
    data["bindings"][0]["accepted_events"] = [
        event("2026-09-30T09:00:00+05:00", "2026-10-02T09:00:00+05:00"),
        event("2026-09-01T09:00:00+05:00", "2026-10-20T09:00:00+05:00"),
    ]
    assert dates(run(data)) == [date(2026, 12, 30)]


def test_after_completion_without_history_uses_explicit_first_due():
    result = run(payload(calendar_unit="month", interval=3, basis="after_accepted_completion", anchor_date="2026-10-20"))
    assert dates(result) == [date(2026, 10, 20)]
    assert result.bindings[0].status == "manual_review"


def test_acceptance_cutoff_and_performed_day_use_site_timezone():
    data = payload(month=12, calendar_unit="month", interval=3, basis="after_accepted_completion")
    data["as_of"] = "2026-10-01T00:00:00+05:00"
    data["bindings"][0]["accepted_events"] = [
        event("2026-08-31T20:30:00Z", "2026-09-02T00:00:00Z"),
        event("2026-09-20T12:00:00Z", "2026-10-01T01:00:00+05:00"),
    ]
    result = run(data)
    assert dates(result) == [date(2026, 12, 1)]
    assert "HISTORY_AFTER_CUTOFF_IGNORED" in result.bindings[0].warnings


def test_deadline_passed_is_local_and_not_a_fulfilled_or_cancelled_status():
    data = payload()
    data["as_of"] = "2026-10-01T20:30:00Z"  # October 2 at the site.
    result = run(data)
    assert result.bindings[0].occurrences[0].deadline_passed
    assert not result.bindings[0].occurrences[1].deadline_passed
    assert all(item.status == "draft" and item.planned_task_id is None and item.actual_execution_id is None
               for item in result.calendar.items)


def annual_payload(year=2026, month=10):
    data = payload(year, month)
    rule = deepcopy(json.loads(EXAMPLES.read_text(encoding="utf-8"))["rules"]["annual_explicit"])
    data["bindings"][0]["rule"] = rule
    data["bindings"][0]["operation"].update(code="1.4", maintenance_type="ТО2", crew_size=2, raw_norm_value="60.000")
    return data


def test_explicit_annual_dates_are_not_spread_over_empty_months():
    assert run(annual_payload()).calendar.total == 0
    result = run(annual_payload(month=11))
    assert dates(result) == [date(2026, 11, 1)]
    occurrence = result.bindings[0].occurrences[0].occurrence
    assert occurrence.earliest_date == date(2026, 10, 26)
    assert occurrence.mandatory_due_date == date(2026, 11, 1)
    assert result.calendar.items[0].crew_size == 2
    assert result.calendar.items[0].raw_norm_value == Decimal("60.000")
    assert result.bindings[0].total_person_hours is None


def test_annual_window_is_clipped_to_activation_without_moving_due():
    data = annual_payload(month=11)
    data["bindings"][0]["binding"]["effective_from"] = "2026-10-30"
    entry = run(data).bindings[0].occurrences[0].occurrence
    assert entry.earliest_date == date(2026, 10, 30)
    assert entry.mandatory_due_date == date(2026, 11, 1)


def test_explicit_annual_rule_does_not_repeat_last_year_dates():
    result = run(annual_payload(year=2027))
    assert result.bindings[0].error_code == "YEAR_DATES_MISSING"
    assert result.calendar.total == 0


@pytest.mark.parametrize("count", [4, 6])
def test_confirmed_five_per_year_rejects_incomplete_or_extra_dates(count):
    data = annual_payload()
    data["bindings"][0]["rule"]["explicit_dates"] = [f"2026-01-{day:02d}" for day in range(1, count + 1)]
    with pytest.raises(ValidationError, match="yearly_count"):
        run(data)


def test_unconfirmed_rule_is_reported_without_invented_dates():
    data = annual_payload()
    data["bindings"][0]["rule"].update(confirmed=False, explicit_dates=[])
    result = run(data)
    assert result.bindings[0].status == "needs_input"
    assert result.bindings[0].error_code == "RULE_UNCONFIRMED"
    assert result.calendar.total == 0
    assert result.bindings[0].total_person_hours is None


def test_quarterly_rule_without_anchor_or_basis_requests_input():
    data = payload(confirmed=False, calendar_unit="month", interval=3, anchor_date=None, basis=None)
    assert run(data).bindings[0].error_code == "RULE_UNCONFIRMED"


def test_confirmed_customer_input_keeps_origin_without_demo_assumptions():
    data = payload()
    data["site"]["data_origin"] = "customer"
    item = data["bindings"][0]
    for key in ("binding", "equipment", "operation", "rule"):
        item[key]["data_origin"] = "customer"
    item["assumptions"] = []
    result = run(data)
    assert result.calendar.total == 31
    assert result.data_origin == "customer"
    assert not result.bindings[0].is_assumption
    assert "SYNTHETIC_DATA" not in result.bindings[0].warnings


def test_runtime_hours_are_not_extrapolated_to_a_calendar_date():
    data = payload()
    data["bindings"][0]["rule"] = json.loads(EXAMPLES.read_text(encoding="utf-8"))["rules"]["runtime_without_calendar_date"]
    result = run(data)
    assert result.calendar.total == 0
    assert result.bindings[0].error_code == "RUNTIME_DATE_UNAVAILABLE"


@pytest.mark.parametrize("changes", [{"allowed_lead_days": 1}, {"basis": "after_accepted_completion"}])
def test_daily_obligations_cannot_be_combined_or_made_rolling(changes):
    assert run(payload(**changes)).bindings[0].error_code == "INVALID_DAILY_RULE"


@pytest.mark.parametrize("unit,expected", [("person_hour", "60.000"), ("elapsed_hour", "120.000")])
def test_known_norm_units_and_confirmed_duration_compute_workload(unit, expected):
    data = annual_payload(month=11)
    data["bindings"][0]["operation"].update(norm_unit=unit, planning_duration_minutes=90,
                                            duration_basis="synthetic_demo: explicitly confirmed duration")
    result = run(data).bindings[0]
    assert result.total_person_hours == Decimal(expected)
    assert result.total_planning_person_minutes == 180


def test_unknown_norm_can_keep_explicit_duration_without_guessing_hours():
    data = annual_payload(month=11)
    data["bindings"][0]["operation"].update(planning_duration_minutes=90, duration_basis="synthetic_demo:duration")
    result = run(data).bindings[0]
    assert result.total_person_hours is None
    assert result.total_planning_person_minutes == 180


def test_monthly_workload_is_decimal_sum_for_all_occurrences():
    data = payload()
    data["bindings"][0]["operation"].update(raw_norm_value="1.125", norm_unit="person_hour")
    assert run(data).bindings[0].total_person_hours == Decimal("34.875")


def test_repeatability_input_order_and_input_immutability():
    data = payload()
    other = deepcopy(data["bindings"][0])
    other["binding"]["binding_id"] = str(UUID(int=99))
    other["equipment"]["equipment_id"] = other["binding"]["equipment_id"] = str(UUID(int=100))
    data["bindings"].append(other)
    request = CalendarGenerationRequest.model_validate_json(json.dumps(data))
    before = request.model_dump_json()
    first = generate_month(request)
    assert generate_month(request) == first
    assert request.model_dump_json() == before
    data["bindings"].reverse()
    assert run(data) == first
    with localcontext() as context:
        context.prec = 4
        assert run(data) == first


def test_rule_version_changes_identity_and_preserves_previous_result():
    data = payload()
    before = run(data)
    new_version = str(uuid4())
    data["bindings"][0]["rule"]["rule_version_id"] = new_version
    data["bindings"][0]["binding"]["rule_version_id"] = new_version
    after = run(data)
    assert dates(before) == dates(after)
    assert {x.occurrence_id for x in before.calendar.items}.isdisjoint(x.occurrence_id for x in after.calendar.items)


def test_clock_changes_only_deadline_flags_not_fixed_occurrence_identity():
    data = payload()
    first = run(data)
    data["as_of"] = "2026-11-01T12:00:00+05:00"
    second = run(data)
    assert [e.occurrence_id for e in first.calendar.items] == [e.occurrence_id for e in second.calendar.items]
    assert all(e.deadline_passed for e in second.bindings[0].occurrences)


def test_huge_interval_does_not_overflow_fixed_calendar():
    assert run(payload(interval=10**12)).calendar.total == 0


def test_unrepresentable_rolling_date_is_diagnostic():
    data = payload(calendar_unit="month", interval=10**12, basis="after_accepted_completion")
    data["bindings"][0]["accepted_events"] = [event("2026-09-01T12:00:00Z")]
    assert run(data).bindings[0].error_code == "DATE_OUT_OF_RANGE"


def test_rolling_first_due_before_activation_needs_explicit_resolution():
    data = payload(calendar_unit="month", interval=3, basis="after_accepted_completion")
    data["bindings"][0]["binding"]["effective_from"] = "2026-10-01"
    assert run(data).bindings[0].error_code == "DUE_BEFORE_ACTIVATION"


def test_duplicate_annual_date_is_rejected_by_existing_contract():
    data = annual_payload()
    rule = data["bindings"][0]["rule"]
    rule["explicit_dates"][1] = rule["explicit_dates"][0]
    with pytest.raises(ValidationError, match="duplicate recurrence date"):
        run(data)


@pytest.mark.parametrize("mutation,match", [
    (lambda d: d["bindings"].append(deepcopy(d["bindings"][0])), "duplicate binding"),
    (lambda d: d["bindings"][0]["binding"].update(equipment_id=str(uuid4())), "binding references"),
    (lambda d: d["bindings"][0]["equipment"].update(site_id=str(uuid4())), "another site"),
    (lambda d: d["bindings"][0]["operation"].update(data_origin="customer"), "mixed binding"),
    (lambda d: d["query"].update(site_id=str(uuid4())), "another site"),
    (lambda d: d["site"].update(timezone="Invalid/Zone"), "unknown site timezone"),
    (lambda d: d["query"].update(include_cancelled=True), "cancelled"),
    (lambda d: d.update(as_of="2026-10-01T00:00:00"), "timezone"),
])
def test_invalid_scope_or_ambiguous_input_is_rejected(mutation, match):
    data = payload()
    mutation(data)
    with pytest.raises(ValidationError, match=match):
        run(data)


def test_invalid_or_duplicated_history_is_rejected():
    data = payload()
    fact = event("2026-09-30T12:00:00Z", "2026-09-29T12:00:00Z")
    data["bindings"][0]["accepted_events"] = [fact]
    with pytest.raises(ValidationError, match="performed_at"):
        run(data)
    fact["accepted_at"] = fact["performed_at"]
    data["bindings"][0]["accepted_events"] = [fact, fact]
    with pytest.raises(ValidationError, match="duplicate accepted event"):
        run(data)


def test_partial_result_preserves_valid_binding_when_another_rule_needs_input():
    data = payload()
    other = deepcopy(data["bindings"][0])
    other["binding"]["binding_id"] = str(UUID(int=99))
    other["rule"]["confirmed"] = False
    data["bindings"].append(other)
    result = run(data)
    assert result.calendar.total == 31
    assert {item.status for item in result.bindings} == {"ok", "needs_input"}


@pytest.mark.parametrize("state,expected", [("retired", "skipped"), ("out_of_service", "ok")])
def test_equipment_state_does_not_silently_reschedule_obligations(state, expected):
    data = payload()
    data["bindings"][0]["equipment"]["state"] = state
    result = run(data)
    assert result.bindings[0].status == expected
    assert result.calendar.total == (0 if state == "retired" else 31)


def test_operation_must_be_approved_and_an_empty_site_is_valid():
    data = payload()
    data["bindings"][0]["operation"]["status"] = "draft"
    assert run(data).bindings[0].error_code == "OPERATION_UNAPPROVED"
    data["bindings"] = []
    assert run(data).calendar.total == 0


def test_all_documented_rule_examples_validate():
    for rule in json.loads(EXAMPLES.read_text(encoding="utf-8"))["rules"].values():
        RecurrenceRule.model_validate_json(json.dumps(rule))
