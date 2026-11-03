"""QA audit: ALG03 impossible-assignment behavior for the two-worker operation.

Operation 1.4 explicitly requires two workers
(``tests/fixtures/domain/maintenance_operations.json``).  A proposal is
acceptable only when it contains the complete team on one common interval.
Partial teams, borrowing workers from another crew, expired qualifications and
a passed deadline must remain explicit refusals with no command.
"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from uuid import UUID

import pytest

from app.assignment import AssignmentRequest, select_crew

ROOT = Path(__file__).resolve().parents[2]
SITE = str(UUID(int=100))
TASK = str(UUID(int=200))
SKILL = str(UUID(int=300))


def at(clock, day="2026-11-01", offset="+05:00"):
    return f"{day}T{clock}:00{offset}"


def interval(start, end, **extra):
    return dict(start_at=at(start), end_at=at(end), **extra)


def worker(number, **extra):
    value = dict(
        worker_id=str(UUID(int=number)), site_id=SITE, name=f"Работник {number}",
        active=True, membership_active=True, can_execute=True,
        qualifications=[dict(skill_id=SKILL, verified_at=at("00:00", "2026-01-01"),
                             valid_until=None, validity_required=False)],
        availability=[interval("09:00", "18:00", status="available")],
        bookings=[],
    )
    value.update(extra)
    return value


def payload(*, crew_size=2, workers=None):
    return dict(
        schema_version="maintenance-0.1", data_origin="synthetic_demo",
        task_id=TASK, site_id=SITE, expected_revision=7,
        timezone="Asia/Yekaterinburg", as_of=at("08:00"),
        window=interval("09:00", "18:00"), earliest_at=at("00:00"),
        deadline_at=at("23:59"), duration_minutes=60,
        duration_basis="synthetic_demo: confirmed 60 minutes",
        crew_size=crew_size, qualification_ids=[SKILL],
        workers=workers if workers is not None else [worker(1), worker(2), worker(3)],
        crews=[], crew_id=None,
    )


def run(data):
    return select_crew(AssignmentRequest.model_validate_json(json.dumps(data)))


def ids(result):
    return [value.int for value in result.command.executor_ids] if result.command else []


def operation_1_4():
    operations = json.loads(
        (ROOT / "tests/fixtures/domain/maintenance_operations.json").read_text(encoding="utf-8")
    )["maintenance_operations"]
    return next(row for row in operations if row["code"] == "1.4")


def test_operation_1_4_contract_requires_two_workers():
    operation = operation_1_4()
    assert operation["required_workers"] == 2
    result = run(payload(crew_size=operation["required_workers"]))
    assert result.status == "ok"
    assert ids(result) == [1, 2]
    assert len(result.command.executor_ids) == 2
    assert result.planning_person_minutes == 120


def test_one_worker_cannot_be_doubled_for_operation_1_4():
    result = run(payload(crew_size=operation_1_4()["required_workers"], workers=[worker(1)]))
    assert result.status == "unavailable"
    assert result.error_code == "INSUFFICIENT_CAPACITY"
    assert result.command is None
    assert result.planning_person_minutes is None
    assert ids(result) == []


def test_two_workers_without_a_common_interval_do_not_form_a_team():
    first = worker(1, availability=[interval("09:00", "10:00", status="available")])
    second = worker(2, availability=[interval("10:00", "11:00", status="available")])
    result = run(payload(crew_size=2, workers=[first, second]))
    assert result.status == "unavailable"
    assert result.error_code == "INSUFFICIENT_CAPACITY"
    assert result.command is None


def test_unqualified_or_expired_member_blocks_the_complete_team():
    missing = worker(1, qualifications=[])
    expired = worker(2, qualifications=[dict(skill_id=SKILL, verified_at=at("00:00", "2026-01-01"),
                                             valid_until="2026-10-31", validity_required=True)])
    result = run(payload(crew_size=2, workers=[missing, expired, worker(3)]))
    assert result.status == "unavailable"
    assert result.error_code == "INSUFFICIENT_CAPACITY"
    reasons = {item.worker_id: item.reasons for item in result.workers}
    assert "QUALIFICATION_MISMATCH" in reasons[UUID(int=1)]
    assert "QUALIFICATION_OUTSIDE_WINDOW" in reasons[UUID(int=2)]
    assert result.command is None


def test_passed_deadline_requires_manual_review_without_a_partial_command():
    data = payload(crew_size=2)
    data["deadline_at"] = at("07:00")
    result = run(data)
    assert result.status == "manual_review"
    assert result.error_code == "DEADLINE_EXCEEDED"
    assert result.command is None
    assert result.planning_person_minutes is None


def test_unknown_duration_does_not_turn_norm_hours_into_a_duration():
    data = payload(crew_size=2)
    data["duration_minutes"] = None
    data["duration_basis"] = None
    result = run(data)
    assert result.status == "needs_input"
    assert result.error_code == "DURATION_UNCONFIRMED"
    assert result.command is None


def test_requested_two_person_team_is_revalidated_without_substitution():
    data = payload(crew_size=2)
    data["requested_worker_ids"] = [str(UUID(int=1)), str(UUID(int=2))]
    data["workers"][1]["availability"] = [interval("12:00", "18:00", status="available")]
    result = run(data)
    # Worker 1 starts at 09:00, worker 2 only at 12:00: no common interval for
    # the full duration at 09:00; the algorithm may still find 12:00, but it
    # must never replace the requested team with worker 3.
    assert result.command is not None
    assert ids(result) == [1, 2]
    assert result.command.start_at == datetime.fromisoformat(at("12:00"))
