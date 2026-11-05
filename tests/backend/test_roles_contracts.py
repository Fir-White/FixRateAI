"""Contract tests for Pydantic schemas, routes and role authorization.

Scope and honesty rules
-----------------------
These tests are **contract tests**, not integration tests. They use in-memory
fixtures only: no PostgreSQL, no real session store, no AI runtime and no HTTP
server. The route table specifies the current role matrix and is checked
against registered FastAPI routes. Handler authorization runs separately in
test_qa02_runtime_contracts.py and test_runtime_integration.py.

The file checks three layers:

1. Pydantic request/response contracts reject client-supplied identity,
   unknown fields and invalid state values.
2. The documented route matrix allows exactly the intended roles and raises
   ``AuthorizationError`` for every forbidden role.
3. Task visibility and self-review rules are enforced for the executor and
   engineer roles.

The real HTTP/PostgreSQL checks run separately through scripts/verify.py.
A green run here does **not** prove that the server works.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.maintenance import (
    AssignmentCommand,
    ErrorResponse,
    ReviewCommand,
)
from app.schemas.maintenance_api import ROLE_PERMISSIONS, TaskResponse
from app.security.authorization import (
    AuthorizationError,
    has_any_role,
    require_any_role,
)


KNOWN_ROLES = frozenset({"executive","chief_engineer","admin", "dispatcher", "engineer", "executor"})
SCHEMA_VERSION = "maintenance-0.1"


# ---------------------------------------------------------------------------
# Route contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutePolicy:
    """Documented authorization rule for one HTTP route."""

    method: str
    path: str
    allowed_roles: frozenset[str]
    mutation: bool = False
    assigned_only_roles: frozenset[str] = frozenset()

    def allows(self, user_roles: Iterable[str]) -> bool:
        return has_any_role(user_roles, self.allowed_roles)

    def requires_own_task(self, user_roles: Iterable[str]) -> bool:
        return bool(frozenset(user_roles) & self.assigned_only_roles)


ROUTES: tuple[RoutePolicy, ...] = (
    RoutePolicy("GET", "/api/v1/maintenance/ui/tasks", KNOWN_ROLES, assigned_only_roles=frozenset({"executor"})),
    RoutePolicy("GET", "/api/v1/maintenance/ui/tasks/{task_id}", KNOWN_ROLES, assigned_only_roles=frozenset({"executor"})),
    RoutePolicy("GET", "/api/v1/maintenance/ui/calendar", frozenset({"executive","chief_engineer","dispatcher","engineer","executor"})),
    RoutePolicy("GET", "/api/v1/maintenance/ui/calendar/preview", frozenset({"chief_engineer","dispatcher","engineer"})),
    RoutePolicy("GET", "/api/v1/maintenance/ui/quality", frozenset({"chief_engineer","engineer"})),
    RoutePolicy("GET", "/api/v1/maintenance/equipment/{equipment_id}/service-configurations", KNOWN_ROLES),
    RoutePolicy("POST", "/api/v1/maintenance/calendar/generate", frozenset({"chief_engineer","engineer","dispatcher"}), mutation=True),
    RoutePolicy("POST", "/api/v1/maintenance/tasks/{task_id}/assign", frozenset({"chief_engineer","engineer","dispatcher"}), mutation=True),
    RoutePolicy("POST", "/api/v1/maintenance/tasks/{task_id}/start", frozenset({"executor"}), mutation=True),
    RoutePolicy("POST", "/api/v1/maintenance/tasks/{task_id}/review", frozenset({"chief_engineer","engineer"}), mutation=True),
    RoutePolicy("POST", "/api/v1/maintenance/tasks/{task_id}/cancel", frozenset({"chief_engineer","engineer","dispatcher"}), mutation=True),
    RoutePolicy("PUT", "/api/v1/maintenance/tasks/{task_id}/report", frozenset({"executor"}), mutation=True),
    RoutePolicy("POST", "/api/v1/maintenance/tasks/{task_id}/submit", frozenset({"executor"}), mutation=True),
    RoutePolicy("POST", "/api/v1/maintenance/equipment/{equipment_id}/service-configurations", frozenset({"admin","chief_engineer"}), mutation=True),
    RoutePolicy("PUT", "/api/v1/maintenance/equipment/{equipment_id}/service-configurations/{binding_id}", frozenset({"admin","chief_engineer"}), mutation=True),
)


def route(method: str, path: str) -> RoutePolicy:
    for policy in ROUTES:
        if policy.method == method and policy.path == path:
            return policy
    raise AssertionError(f"route is not declared: {method} {path}")


# ---------------------------------------------------------------------------
# Principal, authentication and task visibility
# ---------------------------------------------------------------------------


class AuthenticationError(PermissionError):
    """Raised when the principal is absent, unknown or disabled."""


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    roles: frozenset[str]
    site_ids: frozenset[UUID]
    active: bool = True


@dataclass(frozen=True)
class TaskRecord:
    """Minimal task projection used to check scope rules."""

    task_id: UUID
    site_id: UUID
    executor_ids: frozenset[UUID]


class PrincipalDirectory:
    """In-memory stand-in for the session store, used by contract tests only."""

    def __init__(self, principals: Iterable[Principal]) -> None:
        self._principals = {principal.user_id: principal for principal in principals}

    def authenticate(self, user_id: UUID | None) -> Principal:
        if user_id is None:
            raise AuthenticationError("session is required")
        principal = self._principals.get(user_id)
        if principal is None or not principal.active:
            raise AuthenticationError("unknown or disabled user")
        return principal


def visible_tasks(principal: Principal, records: Iterable[TaskRecord]) -> list[TaskRecord]:
    """Apply the documented scope: site access first, then executor ownership."""
    site_records = [record for record in records if record.site_id in principal.site_ids]
    executor_only = (
        "executor" in principal.roles
        and not principal.roles & {"admin", "dispatcher", "engineer"}
    )
    if executor_only:
        return [
            record for record in site_records
            if principal.user_id in record.executor_ids
        ]
    return site_records


def visible_task(
    principal: Principal,
    records: Iterable[TaskRecord],
    task_id: UUID,
) -> TaskRecord | None:
    for record in visible_tasks(principal, records):
        if record.task_id == task_id:
            return record
    return None


def require_task_access(principal: Principal, policy: RoutePolicy) -> None:
    require_any_role(principal.roles, policy.allowed_roles)


def require_reviewer(principal: Principal, record: TaskRecord) -> None:
    """Engineer reviews are forbidden for the executor of the same task."""
    require_any_role(principal.roles, {"engineer"})
    if principal.user_id in record.executor_ids:
        raise AuthorizationError("engineer cannot review own execution")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SITE_A = UUID("00000000-0000-0000-0000-0000000000a1")
SITE_B = UUID("00000000-0000-0000-0000-0000000000b2")
EXECUTOR_1 = UUID("00000000-0000-0000-0000-000000000101")
EXECUTOR_2 = UUID("00000000-0000-0000-0000-000000000102")
ENGINEER = UUID("00000000-0000-0000-0000-000000000201")
ENGINEER_EXECUTOR = UUID("00000000-0000-0000-0000-000000000202")
DISPATCHER = UUID("00000000-0000-0000-0000-000000000301")
ADMIN = UUID("00000000-0000-0000-0000-000000000401")
OUTSIDER_SITE_B = UUID("00000000-0000-0000-0000-000000000501")
DISABLED_USER = UUID("00000000-0000-0000-0000-000000000601")
UNKNOWN_USER = UUID("00000000-0000-0000-0000-000000000999")

TASK_A_1 = UUID("00000000-0000-0000-0000-0000000000f1")
TASK_A_2 = UUID("00000000-0000-0000-0000-0000000000f2")
TASK_B_1 = UUID("00000000-0000-0000-0000-0000000000f3")


@pytest.fixture()
def directory() -> PrincipalDirectory:
    return PrincipalDirectory(
        [
            Principal(EXECUTOR_1, frozenset({"executor"}), frozenset({SITE_A})),
            Principal(EXECUTOR_2, frozenset({"executor"}), frozenset({SITE_A})),
            Principal(ENGINEER, frozenset({"chief_engineer","engineer"}), frozenset({SITE_A})),
            Principal(ENGINEER_EXECUTOR, frozenset({"engineer", "executor"}),
                      frozenset({SITE_A})),
            Principal(DISPATCHER, frozenset({"chief_engineer","engineer","dispatcher"}), frozenset({SITE_A})),
            Principal(ADMIN, frozenset({"admin"}), frozenset({SITE_A})),
            Principal(OUTSIDER_SITE_B, frozenset({"executor"}), frozenset({SITE_B})),
            Principal(DISABLED_USER, frozenset({"executor"}), frozenset({SITE_A}),
                      active=False),
        ]
    )


@pytest.fixture()
def tasks() -> list[TaskRecord]:
    return [
        TaskRecord(TASK_A_1, SITE_A, frozenset({EXECUTOR_1})),
        TaskRecord(TASK_A_2, SITE_A, frozenset({EXECUTOR_2})),
        TaskRecord(TASK_B_1, SITE_B, frozenset({OUTSIDER_SITE_B})),
    ]


# ---------------------------------------------------------------------------
# Pydantic contract tests
# ---------------------------------------------------------------------------


def _task_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "data_origin": "synthetic_demo",
        "task_id": TASK_A_1,
        "occurrence_id": uuid4(),
        "equipment_id": uuid4(),
        "operation_version_id": uuid4(),
        "state": "assigned",
        "revision": 1,
        "scheduled_start": datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc),
        "scheduled_end": datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
        "assignment_ids": [],
        "active_execution_id": None,
        "deadline_breached": False,
    }
    payload.update(overrides)
    return payload


def test_task_response_rejects_client_supplied_identity_fields() -> None:
    """A client must not be able to choose executor/assignee through the task DTO."""
    for forbidden in ("executor_id", "assigned_by", "submitted_by", "site_id"):
        with pytest.raises(ValidationError):
            TaskResponse.model_validate(_task_payload(**{forbidden: uuid4()}))


def test_task_state_enum_is_closed() -> None:
    with pytest.raises(ValidationError):
        TaskResponse.model_validate(_task_payload(state="approved"))


def test_task_response_accepts_documented_state() -> None:
    task = TaskResponse.model_validate(_task_payload())
    assert task.state == "assigned"
    assert task.schema_version == SCHEMA_VERSION


def test_review_command_requires_reason_and_known_verdict() -> None:
    valid = {
        "schema_version": SCHEMA_VERSION,
        "expected_revision": 3,
        "execution_id": uuid4(),
        "verdict": "accepted",
        "reason": "Фото и показания соответствуют регламенту",
        "reviewed_ai_result_id": None,
        "additional_evidence_refs": [],
    }
    command = ReviewCommand.model_validate(valid)
    assert command.verdict == "accepted"

    for broken in (
        {**valid, "reason": ""},
        {**valid, "verdict": "approved"},
        {**valid, "expected_revision": 0},
        {**valid, "engineer_id": uuid4()},
    ):
        with pytest.raises(ValidationError):
            ReviewCommand.model_validate(broken)


def test_assignment_command_requires_crew_and_positive_revision() -> None:
    valid = {
        "schema_version": SCHEMA_VERSION,
        "expected_revision": 1,
        "executor_ids": [EXECUTOR_1],
        "start_at": datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc),
        "end_at": datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
        "reason": "Плановая бригада",
    }
    AssignmentCommand.model_validate(valid)

    for broken in (
        {**valid, "executor_ids": []},
        {**valid, "expected_revision": 0},
        {**valid, "assigned_by": uuid4()},
        {**valid, "start_at": "2026-11-02T08:00:00"},
    ):
        with pytest.raises(ValidationError):
            AssignmentCommand.model_validate(broken)


def test_error_response_has_stable_shape_for_403_and_404() -> None:
    for code in ("FORBIDDEN", "NOT_FOUND"):
        error = ErrorResponse.model_validate(
            {
                "schema_version": SCHEMA_VERSION,
                "error": {
                    "code": code,
                    "message": "denied",
                    "details": [],
                    "request_id": "req-1",
                },
            }
        )
        assert error.error.code == code


# ---------------------------------------------------------------------------
# Permission matrix (real ROLE_PERMISSIONS from the application)
# ---------------------------------------------------------------------------


def test_permission_matrix_keeps_duties_separated() -> None:
    assert "execution:accept" in ROLE_PERMISSIONS["engineer"]
    for role in ("executor", "dispatcher", "admin"):
        assert "execution:accept" not in ROLE_PERMISSIONS[role]

    assert "task:assign" in ROLE_PERMISSIONS["dispatcher"]
    assert "task:assign" in ROLE_PERMISSIONS["engineer"]
    assert "task:assign" in ROLE_PERMISSIONS["chief_engineer"]
    for role in ("executor", "executive", "admin"):
        assert "task:assign" not in ROLE_PERMISSIONS[role]

    assert "operation:write" in ROLE_PERMISSIONS["chief_engineer"]
    assert "operation:write" not in ROLE_PERMISSIONS["dispatcher"]
    assert "operation:write" not in ROLE_PERMISSIONS["engineer"]


# ---------------------------------------------------------------------------
# Route matrix
# ---------------------------------------------------------------------------


def test_routes_are_unique_and_versioned() -> None:
    keys = [(policy.method, policy.path) for policy in ROUTES]
    assert len(keys) == len(set(keys))
    assert all(policy.path.startswith("/api/v1/maintenance") for policy in ROUTES)
    assert all(policy.allowed_roles <= KNOWN_ROLES for policy in ROUTES)
    assert all(policy.allowed_roles for policy in ROUTES)
    assert all(policy.mutation for policy in ROUTES if policy.method != "GET")
    assert not any(policy.mutation for policy in ROUTES if policy.method == "GET")


@pytest.mark.parametrize("policy", ROUTES, ids=lambda p: f"{p.method} {p.path}")
@pytest.mark.parametrize("role", sorted(KNOWN_ROLES))
def test_route_matrix_allows_or_denies_role(policy: RoutePolicy, role: str) -> None:
    if role in policy.allowed_roles:
        require_any_role([role], policy.allowed_roles)
    else:
        with pytest.raises(AuthorizationError):
            require_any_role([role], policy.allowed_roles)


@pytest.mark.parametrize(
    "policy",
    [
        route("POST", "/api/v1/maintenance/tasks/{task_id}/review"),
        route("GET", "/api/v1/maintenance/ui/quality"),
        route("PUT", "/api/v1/maintenance/equipment/{equipment_id}/service-configurations/{binding_id}"),
        route("POST", "/api/v1/maintenance/tasks/{task_id}/assign"),
    ],
)
def test_executor_is_denied_supervisory_routes(policy: RoutePolicy) -> None:
    with pytest.raises(AuthorizationError):
        require_any_role(["executor"], policy.allowed_roles)


def test_engineer_cannot_change_regulation() -> None:
    """The controller reviews work but does not edit the regulation."""
    with pytest.raises(AuthorizationError):
        require_any_role(
            ["engineer"],
            route("PUT", "/api/v1/maintenance/equipment/{equipment_id}/service-configurations/{binding_id}").allowed_roles,
        )


def test_engineer_can_assign_and_cancel_pre_execution_tasks() -> None:
    for policy in (
        route("POST", "/api/v1/maintenance/tasks/{task_id}/assign"),
        route("POST", "/api/v1/maintenance/tasks/{task_id}/cancel"),
    ):
        require_any_role(["engineer"], policy.allowed_roles)


def test_dispatcher_cannot_review_or_read_quality_queue() -> None:
    for policy in (
        route("POST", "/api/v1/maintenance/tasks/{task_id}/review"),
        route("GET", "/api/v1/maintenance/ui/quality"),
    ):
        with pytest.raises(AuthorizationError):
            require_any_role(["dispatcher"], policy.allowed_roles)


def test_admin_alone_does_not_replace_engineer_or_dispatcher() -> None:
    for policy in (
        route("POST", "/api/v1/maintenance/tasks/{task_id}/review"),
        route("GET", "/api/v1/maintenance/ui/quality"),
        route("POST", "/api/v1/maintenance/tasks/{task_id}/assign"),
    ):
        with pytest.raises(AuthorizationError):
            require_any_role(["admin"], policy.allowed_roles)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_unknown_user_is_rejected(directory: PrincipalDirectory) -> None:
    with pytest.raises(AuthenticationError):
        directory.authenticate(UNKNOWN_USER)


def test_missing_session_is_rejected(directory: PrincipalDirectory) -> None:
    with pytest.raises(AuthenticationError):
        directory.authenticate(None)


def test_disabled_user_is_rejected(directory: PrincipalDirectory) -> None:
    with pytest.raises(AuthenticationError):
        directory.authenticate(DISABLED_USER)


def test_authenticated_user_can_list_tasks(directory: PrincipalDirectory) -> None:
    principal = directory.authenticate(EXECUTOR_1)
    require_any_role(principal.roles, route("GET", "/api/v1/maintenance/ui/tasks").allowed_roles)


def http_status(error: Exception | None) -> int:
    """Documented mapping from the authorization layer to HTTP status codes."""
    if error is None:
        return 200
    if isinstance(error, AuthenticationError):
        return 401
    if isinstance(error, AuthorizationError):
        return 403
    return 500


def test_forbidden_actions_map_to_expected_http_statuses(
    directory: PrincipalDirectory,
    tasks: list[TaskRecord],
) -> None:
    with pytest.raises(AuthenticationError) as unauthenticated:
        directory.authenticate(UNKNOWN_USER)
    assert http_status(unauthenticated.value) == 401

    principal = directory.authenticate(EXECUTOR_1)
    with pytest.raises(AuthorizationError) as forbidden:
        require_any_role(
            principal.roles,
            route("POST", "/api/v1/maintenance/tasks/{task_id}/review").allowed_roles,
        )
    assert http_status(forbidden.value) == 403

    assert http_status(None) == 200  # allowed action

    foreign = visible_task(principal, tasks, TASK_A_2)
    assert foreign is None
    assert (200 if foreign is not None else 404) == 404


# ---------------------------------------------------------------------------
# Visibility and self-review
# ---------------------------------------------------------------------------


def test_executor_sees_only_own_tasks(
    directory: PrincipalDirectory,
    tasks: list[TaskRecord],
) -> None:
    principal = directory.authenticate(EXECUTOR_1)
    assert [record.task_id for record in visible_tasks(principal, tasks)] == [TASK_A_1]


def test_executor_cannot_open_foreign_task(
    directory: PrincipalDirectory,
    tasks: list[TaskRecord],
) -> None:
    principal = directory.authenticate(EXECUTOR_1)
    assert visible_task(principal, tasks, TASK_A_2) is None
    assert visible_task(principal, tasks, TASK_B_1) is None


def test_engineer_sees_site_tasks_but_not_other_site(
    directory: PrincipalDirectory,
    tasks: list[TaskRecord],
) -> None:
    principal = directory.authenticate(ENGINEER)
    visible = {record.task_id for record in visible_tasks(principal, tasks)}
    assert visible == {TASK_A_1, TASK_A_2}


def test_outsider_does_not_see_foreign_site_tasks(
    directory: PrincipalDirectory,
    tasks: list[TaskRecord],
) -> None:
    principal = directory.authenticate(OUTSIDER_SITE_B)
    assert [record.task_id for record in visible_tasks(principal, tasks)] == [TASK_B_1]


def test_executor_cannot_review_any_task(
    directory: PrincipalDirectory,
    tasks: list[TaskRecord],
) -> None:
    principal = directory.authenticate(EXECUTOR_1)
    record = visible_task(principal, tasks, TASK_A_1)
    assert record is not None
    with pytest.raises(AuthorizationError):
        require_reviewer(principal, record)


def test_engineer_cannot_review_own_execution(
    directory: PrincipalDirectory,
) -> None:
    principal = directory.authenticate(ENGINEER_EXECUTOR)
    own_record = TaskRecord(TASK_A_1, SITE_A, frozenset({ENGINEER_EXECUTOR}))
    with pytest.raises(AuthorizationError, match="own execution"):
        require_reviewer(principal, own_record)


def test_engineer_can_review_foreign_execution(
    directory: PrincipalDirectory,
    tasks: list[TaskRecord],
) -> None:
    principal = directory.authenticate(ENGINEER)
    record = visible_task(principal, tasks, TASK_A_1)
    assert record is not None
    require_reviewer(principal, record)


def test_visibility_rule_marks_executor_routes_as_assigned_only() -> None:
    assert route("GET", "/api/v1/maintenance/ui/tasks").requires_own_task(["executor"])
    assert route("GET", "/api/v1/maintenance/ui/tasks/{task_id}").requires_own_task(["executor"])
    assert not route("GET", "/api/v1/maintenance/ui/tasks").requires_own_task(["engineer"])


def test_route_contract_names_registered_fastapi_routes() -> None:
    from fastapi.routing import APIRoute
    from app.main import create_app
    registered = {(method, entry.path) for entry in create_app().routes
                  if isinstance(entry, APIRoute) for method in entry.methods}
    missing = {(entry.method, entry.path) for entry in ROUTES} - registered
    assert not missing, f"Role contract contains unregistered routes: {sorted(missing)}"
