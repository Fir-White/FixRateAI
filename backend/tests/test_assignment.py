from copy import deepcopy
from datetime import datetime
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.assignment import AssignmentRequest, AssignmentSelection, select_crew
from app.schemas.maintenance import AssignmentCommand

SITE = str(UUID(int=100))
TASK = str(UUID(int=200))
SKILL = str(UUID(int=300))


def at(clock, day="2026-11-01", offset="+05:00"):
    return f"{day}T{clock}:00{offset}"


def interval(start, end, **extra):
    return dict(start_at=at(start), end_at=at(end), **extra)


def worker(number, **extra):
    return dict(worker_id=str(UUID(int=number)), site_id=SITE, name=f"Работник {number}",
        active=True, membership_active=True, can_execute=True,
        qualifications=[dict(skill_id=SKILL, verified_at=at("00:00", "2026-01-01"), valid_until=None, validity_required=False)],
        availability=[interval("09:00", "18:00", status="available")], bookings=[], **extra)


def payload():
    return dict(schema_version="maintenance-0.1", data_origin="synthetic_demo", task_id=TASK, site_id=SITE,
        expected_revision=7, timezone="Asia/Yekaterinburg", as_of=at("08:00"),
        window=interval("09:00", "18:00"), earliest_at=at("00:00"), deadline_at=at("23:59"),
        duration_minutes=60, duration_basis="synthetic_demo: confirmed 60 minutes", crew_size=2,
        qualification_ids=[SKILL], workers=[worker(1), worker(2), worker(3)], crews=[], crew_id=None)


def run(data):
    return select_crew(AssignmentRequest.model_validate_json(json.dumps(data)))


def ids(result):
    return [value.int for value in result.command.executor_ids] if result.command else []


def test_complete_team_and_canonical_command_round_trip():
    result = run(payload())
    assert result.status == "ok" and ids(result) == [1, 2]
    assert result.command.start_at == datetime.fromisoformat(at("09:00"))
    assert result.command.end_at == datetime.fromisoformat(at("10:00"))
    assert result.command.expected_revision == 7
    assert result.planning_person_minutes == 120
    assert AssignmentCommand.model_validate_json(result.command.model_dump_json()) == result.command
    assert AssignmentSelection.model_validate_json(result.model_dump_json()) == result


def test_one_worker_never_satisfies_two_person_operation():
    data = payload()
    data["workers"] = data["workers"][:1]
    result = run(data)
    assert result.status == "unavailable" and result.error_code == "INSUFFICIENT_CAPACITY"
    assert result.command is None and result.planning_person_minutes is None


def test_choose_least_daily_minutes_instead_of_number_of_jobs():
    data = payload()
    data["workers"][0]["bookings"] = [interval("12:00", "16:00", task_id=str(UUID(int=400)))]
    data["workers"][1]["bookings"] = [interval("12:00", "12:30", task_id=str(UUID(int=401))), interval("13:00", "13:30", task_id=str(UUID(int=402)))]
    result = run(data)
    assert ids(result) == [3, 2]
    assert [item.load_minutes for item in result.workers] == [240, 60, 0]


def test_busy_worker_rejoins_at_end_of_half_open_booking():
    data = payload()
    data["workers"] = data["workers"][:2]
    data["workers"][0]["bookings"] = [interval("09:00", "10:00", task_id=str(UUID(int=400)))]
    assert run(data).command.start_at == datetime.fromisoformat(at("10:00"))


def test_adjacent_availability_merges_and_unavailability_overrides_it():
    data = payload()
    for item in data["workers"]:
        item["availability"] = [interval("09:00", "09:30", status="available"),
            interval("09:30", "12:00", status="available"), interval("09:00", "10:00", status="unavailable")]
    assert run(data).command.start_at == datetime.fromisoformat(at("10:00"))


def test_workers_need_a_common_interval_not_individual_free_slots():
    data = payload()
    data["workers"] = data["workers"][:2]
    data["workers"][0]["availability"] = [interval("09:00", "10:00", status="available")]
    data["workers"][1]["availability"] = [interval("10:00", "11:00", status="available")]
    assert run(data).command is None


@pytest.mark.parametrize("field,value,reason", [
    ("active", False, "INACTIVE_USER"), ("membership_active", False, "SITE_ACCESS_MISSING"),
    ("site_id", str(UUID(int=101)), "SITE_ACCESS_MISSING"), ("can_execute", False, "EXECUTOR_ROLE_REQUIRED"),
    ("booking_data_complete", False, "BOOKING_UNCONFIRMED"),
    ("workload_data_complete", False, "WORKLOAD_UNCONFIRMED"),
    ("qualifications", [], "QUALIFICATION_MISMATCH"), ("availability", [], "NO_AVAILABILITY"),
])
def test_candidate_rejections_are_diagnostic(field, value, reason):
    data = payload()
    data["workers"][0][field] = value
    result = run(data)
    assert 1 not in ids(result)
    assert reason in result.workers[0].reasons
    if field in ("booking_data_complete", "workload_data_complete"):
        assert result.workers[0].load_minutes is None


@pytest.mark.parametrize("update,reason", [
    ({"verified_at": None}, "QUALIFICATION_UNVERIFIED"),
    ({"valid_until": "2026-10-31"}, "QUALIFICATION_OUTSIDE_WINDOW"),
    ({"validity_required": True}, "QUALIFICATION_EXPIRY_MISSING"),
])
def test_unverified_expired_or_incomplete_qualifications_are_not_used(update, reason):
    data = payload()
    data["workers"][0]["qualifications"][0].update(update)
    assert reason in run(data).workers[0].reasons


def test_qualification_must_cover_entire_cross_midnight_job():
    data = payload()
    data.update(crew_size=1, window=dict(start_at=at("23:00"), end_at=at("02:00", "2026-11-02")),
                deadline_at=at("03:00", "2026-11-02"), duration_minutes=120)
    data["workers"] = [worker(1)]
    data["workers"][0]["availability"] = [dict(start_at=at("23:00"), end_at=at("02:00", "2026-11-02"), status="available")]
    data["workers"][0]["qualifications"][0]["valid_until"] = "2026-11-01"
    assert run(data).command is None
    data["duration_minutes"] = 60
    assert run(data).command.end_at == datetime.fromisoformat(at("00:00", "2026-11-02"))


def test_future_verification_is_not_an_existing_verified_fact():
    data = payload()
    for item in data["workers"]:
        item["qualifications"][0]["verified_at"] = at("11:00")
    result = run(data)
    assert result.command is None
    assert all("QUALIFICATION_UNVERIFIED" in item.reasons for item in result.workers)


@pytest.mark.parametrize("update,expected", [
    ({"duration_minutes": None}, "DURATION_UNCONFIRMED"),
    ({"duration_basis": None}, "DURATION_UNCONFIRMED"),
    ({"earliest_at": None}, "MAINTENANCE_WINDOW_UNCONFIRMED"),
    ({"deadline_at": at("07:00")}, "DEADLINE_EXCEEDED"),
    ({"deadline_at": at("09:30")}, "WINDOW_TOO_SHORT"),
])
def test_missing_inputs_and_deadlines_never_produce_a_partial_proposal(update, expected):
    data = payload()
    data.update(update)
    result = run(data)
    assert result.command is None and result.error_code == expected


def test_current_time_is_rounded_up_without_planning_in_the_past():
    data = payload()
    data["as_of"] = "2026-11-01T09:00:01+05:00"
    assert run(data).command.start_at == datetime.fromisoformat(at("09:01"))


def test_existing_target_assignments_do_not_penalize_reassignment():
    data = payload()
    data["workers"][0]["bookings"] = [interval("09:00", "18:00", task_id=TASK)]
    result = run(data)
    assert ids(result) == [1, 2] and result.workers[0].load_minutes == 0


def test_overlapping_bookings_are_counted_once_for_daily_load():
    data = payload()
    data["workers"][0]["bookings"] = [interval("12:00", "14:00", task_id=str(UUID(int=400))), interval("13:00", "15:00", task_id=str(UUID(int=401)))]
    assert run(data).workers[0].load_minutes == 180


def crew(number, members=(1, 2), **extra):
    return dict(crew_id=str(UUID(int=number)), site_id=SITE, name=f"Бригада {number}", active=True,
        members=[dict(worker_id=str(UUID(int=member)), valid_from="2026-01-01", valid_to=None) for member in members], **extra)


def test_existing_crew_wins_tie_for_the_same_workers_and_interval():
    data = payload()
    data["crews"] = [crew(500)]
    result = run(data)
    assert ids(result) == [1, 2] and result.crew_id == UUID(int=500)


def test_requested_crew_does_not_borrow_workers_from_other_crews():
    data = payload()
    data["crews"] = [crew(500, members=(1,))]
    data["crew_id"] = str(UUID(int=500))
    assert run(data).command is None


@pytest.mark.parametrize("change", ["inactive", "expired", "other_site"])
def test_crew_membership_and_site_must_cover_the_interval(change):
    data = payload()
    data["crews"] = [crew(500)]
    data["crew_id"] = str(UUID(int=500))
    if change == "inactive":
        data["crews"][0]["active"] = False
    elif change == "other_site":
        data["crews"][0]["site_id"] = str(UUID(int=101))
    else:
        data["crews"][0]["members"][0]["valid_to"] = "2026-10-31"
    assert run(data).command is None


def test_crew_membership_start_can_delay_selection():
    data = payload()
    data["crews"] = [crew(500)]
    data["crew_id"] = str(UUID(int=500))
    for member in data["crews"][0]["members"]:
        member["valid_from"] = "2026-11-02"
    assert run(data).command is None


def test_order_independence_and_no_input_mutation():
    data = payload()
    data["crews"] = [crew(501), crew(500)]
    request = AssignmentRequest.model_validate_json(json.dumps(data))
    before = request.model_dump_json()
    result = select_crew(request)
    assert request.model_dump_json() == before
    data["workers"].reverse()
    data["crews"].reverse()
    assert run(data) == result


@pytest.mark.parametrize("change", ["naive", "empty_window", "duplicate_worker", "huge_duration"])
def test_invalid_contract_is_rejected(change):
    data = payload()
    if change == "naive":
        data["window"]["start_at"] = "2026-11-01T09:00:00"
    elif change == "empty_window":
        data["window"]["end_at"] = data["window"]["start_at"]
    elif change == "duplicate_worker":
        data["workers"].append(deepcopy(data["workers"][0]))
    else:
        data["duration_minutes"] = 10**12
    with pytest.raises(ValidationError):
        run(data)


@pytest.mark.parametrize("value", ["2026-03-29T02:30", "2026-10-25T02:30", "2026-11-01T09:00+01:00"])
def test_http_local_time_rejects_dst_gaps_folds_and_offset_input(value):
    from fastapi import HTTPException
    from zoneinfo import ZoneInfo
    from app.integration.assignment import local_time
    with pytest.raises(HTTPException) as error:
        local_time(datetime.fromisoformat(value), ZoneInfo("Europe/Berlin"))
    assert error.value.status_code == 422


def test_http_local_time_uses_site_timezone():
    from zoneinfo import ZoneInfo
    from app.integration.assignment import local_time
    assert local_time(datetime(2026, 11, 1, 9), ZoneInfo("Asia/Yekaterinburg")).isoformat() == at("09:00")


def test_day_load_is_clipped_in_site_timezone_and_elapsed_dst_minutes():
    data = payload()
    data.update(timezone="Europe/Berlin", as_of="2026-10-25T00:00:00+02:00",
                window=dict(start_at="2026-10-25T09:00:00+01:00", end_at="2026-10-25T18:00:00+01:00"),
                earliest_at="2026-10-25T00:00:00+02:00", deadline_at="2026-10-26T00:00:00+01:00")
    for item in data["workers"]:
        item["availability"] = [dict(**data["window"], status="available")]
    data["workers"][0]["bookings"] = [dict(task_id=str(UUID(int=400)), start_at="2026-10-24T23:00:00+02:00", end_at="2026-10-25T04:00:00+01:00")]
    result = run(data)
    assert result.workers[0].load_minutes == 300
    assert ids(result) == [2, 3]


def test_every_member_needs_every_required_qualification():
    data = payload()
    second_skill = str(UUID(int=301))
    data["qualification_ids"].append(second_skill)
    data["workers"][0]["qualifications"].append({**data["workers"][0]["qualifications"][0], "skill_id": second_skill})
    result = run(data)
    assert result.command is None
    assert all("QUALIFICATION_MISMATCH" in item.reasons for item in result.workers[1:])


def test_earlier_complete_team_has_priority_over_less_load_later():
    data = payload()
    data["crew_size"] = 1
    data["workers"] = data["workers"][:2]
    data["workers"][0]["bookings"] = [interval("12:00", "17:00", task_id=str(UUID(int=400)))]
    data["workers"][1]["availability"] = [interval("10:00", "18:00", status="available")]
    result = run(data)
    assert ids(result) == [1] and result.command.start_at.hour == 9
