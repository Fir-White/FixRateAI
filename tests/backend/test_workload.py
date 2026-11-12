"""Workload lower bounds: exact units, missing facts, reservations and local days."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from uuid import UUID
import json

import pytest
from pydantic import ValidationError

from app.schemas.planning import WorkloadRequest
from app.scheduling.workload import calculate_workload

SITE = UUID(int=1)
DAY = date(2027, 1, 5)


def worker(number=10, **changes):
    return dict(dict(worker_id=UUID(int=number), site_id=SITE, name='Test worker', active=True,
        membership_active=True, can_execute=True, availability=[dict(
            start_at='2027-01-05T00:00:00+05:00', end_at='2027-01-06T00:00:00+05:00', status='available')]),
        **changes)


def demand(number=100, **changes):
    return dict(dict(occurrence_id=UUID(int=number), date=DAY, equipment_name='Test equipment',
        operation_title='Test maintenance', data_origin='synthetic_demo', person_hours='40', crew_size=1), **changes)


def request(*, demands=None, workers=None, **changes):
    payload = dict(site_id=SITE, timezone='Asia/Yekaterinburg', year=2027, month=1,
        as_of='2027-01-01T00:00:00Z', capacity_hours_per_24h='24',
        demands=[demand()] if demands is None else demands, workers=[worker()] if workers is None else workers)
    payload.update(changes)
    return WorkloadRequest.model_validate_json(json.dumps(payload, default=str))


def result(**kwargs):
    return calculate_workload(request(**kwargs)).days[4]


@pytest.mark.parametrize('hours,expected', [('24', 1), ('40', 2), ('46', 2), ('56', 3)])
def test_customer_hours_are_rounded_up_as_a_lower_bound(hours, expected):
    row = result(demands=[demand(person_hours=hours)])
    assert row.required_workers_lower_bound == expected
    assert row.free_person_hours == Decimal(24)
    assert row.deficit_person_hours == max(Decimal(0), Decimal(hours) - 24)


def test_capacity_is_separate_from_workload_and_shift_duration():
    full, half = result(), result(capacity_hours_per_24h='12')
    assert full.total_person_hours == half.total_person_hours == Decimal(40)
    assert half.free_person_hours == 12
    assert half.required_workers_lower_bound == 4
    assert half.deficit_person_hours == 28


def test_minimum_crew_is_not_replaced_by_a_division_of_hours():
    row = result(demands=[demand(person_hours='1', crew_size=2)])
    assert row.required_workers_lower_bound == 2
    assert row.status == 'hours_sufficient'  # This is intentionally not a feasible-plan verdict.


def test_overlaps_absences_and_bookings_are_subtracted_without_double_counting():
    person = worker()
    person['availability'] += [dict(start_at='2027-01-05T00:00:00+05:00',
        end_at='2027-01-06T00:00:00+05:00', status='available'), dict(start_at='2027-01-05T08:00:00+05:00',
        end_at='2027-01-05T12:00:00+05:00', status='unavailable')]
    person['bookings'] = [dict(task_id=UUID(int=300), start_at='2027-01-05T10:00:00+05:00',
                              end_at='2027-01-05T14:00:00+05:00')]
    row = result(workers=[person])
    assert row.free_person_hours == 18
    assert row.deficit_person_hours == 22


def test_overnight_capacity_is_clipped_at_local_day_boundaries():
    person = worker()
    person['availability'] = [dict(start_at='2027-01-04T08:00:00+05:00',
        end_at='2027-01-05T08:00:00+05:00', status='available')]
    assert result(workers=[person]).free_person_hours == 8
    assert result(workers=[person], capacity_hours_per_24h='12').free_person_hours == 4


def test_known_zero_availability_differs_from_missing_calendar():
    person = worker()
    person['availability'] = []
    row = result(workers=[person])
    assert row.free_person_hours == 0 and row.status == 'hours_deficit'
    person['availability_data_complete'] = False
    row = result(workers=[person])
    assert row.free_person_hours is None and row.status == 'incomplete'
    assert row.deficit_person_hours is None


@pytest.mark.parametrize('missing', ['booking_data_complete', 'workload_data_complete'])
def test_unknown_bookings_never_turn_into_free_capacity(missing):
    row = result(workers=[worker(**{missing: False})])
    assert row.status == 'incomplete' and row.free_person_hours is None
    assert row.unknown_workers == 1


def test_unknown_norm_preserves_known_subtotal_without_fabricated_demand():
    row = result(demands=[demand(person_hours=None), demand(number=101, person_hours='1.125')])
    assert row.total_person_hours is None and row.unassigned_person_hours is None
    assert row.required_workers_lower_bound is None and row.deficit_person_hours is None
    assert row.known_person_hours == Decimal('1.125') and row.unknown_norms == 1


def test_assigned_work_and_its_reservation_are_not_demanded_twice():
    person = worker()
    person['bookings'] = [dict(task_id=UUID(int=300), start_at='2027-01-05T00:00:00+05:00',
        end_at='2027-01-06T00:00:00+05:00')]
    row = result(workers=[person], demands=[demand(person_hours='24', state='assigned', assigned_worker_ids=[UUID(int=10)]),
                                          demand(number=101, person_hours='8')])
    assert row.total_person_hours == 32 and row.unassigned_person_hours == 8
    assert row.assigned_workers == 1 and row.free_person_hours == 0
    assert row.deficit_person_hours == 8


def test_partial_assignment_and_incomplete_sources_require_input():
    assert result(demands=[demand(state='incomplete')]).status == 'incomplete'
    assert result(source_incomplete=True).deficit_person_hours is None


def test_a_worker_booked_elsewhere_cannot_supply_two_sites():
    person = worker()
    person['bookings'] = [dict(task_id=UUID(int=999), start_at='2027-01-05T00:00:00+05:00',
        end_at='2027-01-06T00:00:00+05:00')]
    assert result(workers=[person]).free_person_hours == 0
    assert result(workers=[]).deficit_person_hours == 40


def test_snapshot_and_result_are_order_independent_and_input_is_unchanged():
    a = request(workers=[worker(10), worker(11)], demands=[demand(), demand(101)])
    before = a.model_dump_json()
    b = a.model_copy(update={'workers': list(reversed(a.workers)), 'demands': list(reversed(a.demands))})
    assert calculate_workload(a) == calculate_workload(b)
    assert a.model_dump_json() == before


def test_assignment_order_does_not_change_the_snapshot():
    a = request(demands=[demand(state='assigned', assigned_worker_ids=[UUID(int=11), UUID(int=10)])])
    b = request(demands=[demand(state='assigned', assigned_worker_ids=[UUID(int=10), UUID(int=11)])])
    assert calculate_workload(a) == calculate_workload(b)


@pytest.mark.parametrize('changes', [dict(capacity_hours_per_24h='0'), dict(capacity_hours_per_24h='25'),
    dict(capacity_hours_per_24h='NaN'), dict(capacity_hours_per_24h='1.0001'), dict(timezone='Unknown/Zone'),
    dict(workers=[worker(site_id=UUID(int=2))])])
def test_invalid_policy_or_scope_is_rejected(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_dst_days_use_elapsed_hours_and_leap_month_has_all_days():
    person = worker()
    person['availability'] = [dict(start_at='2027-03-28T00:00:00+01:00',
        end_at='2027-03-29T00:00:00+02:00', status='available')]
    value = calculate_workload(request(timezone='Europe/Berlin', year=2027, month=3, workers=[person], demands=[]))
    assert value.days[27].free_person_hours == 23
    assert len(calculate_workload(request(year=2028, month=2, demands=[])).days) == 29


def test_a_skipped_local_day_is_diagnostic_instead_of_dividing_by_zero():
    value = calculate_workload(request(timezone='Pacific/Apia', year=2011, month=12,
        demands=[demand(date=date(2011, 12, 30))], workers=[]))
    assert value.days[29].status == 'incomplete'
    assert value.days[29].required_workers_lower_bound is None


def test_source_excel_is_preserved_without_accepting_its_norms():
    root = Path(__file__).resolve().parents[2]
    provenance = json.loads((root/'data/provenance/intelligent_planning_2027.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((root/provenance['repository_path']).read_bytes()).hexdigest() == provenance['sha256']
    assert len(provenance['operations']) == 8
    assert provenance['status'] == 'source_example_requires_normalization'
    assert provenance['prototype_policy']['status'] == 'provisional'
