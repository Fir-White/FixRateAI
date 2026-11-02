"""Domain rules and projections for the maintenance_jobs API."""
from __future__ import annotations

from typing import Final

INTERNAL_TO_PUBLIC: Final = {
    "draft": "planned",
    "assigned": "assigned",
    "in_progress": "in_progress",
    "in_review": "submitted",
    "completed": "accepted",
    "rework": "rework",
}
PUBLIC_TO_INTERNAL: Final = {value: key for key, value in INTERNAL_TO_PUBLIC.items()}

TRANSITIONS: Final = {
    "planned": frozenset({"assigned"}),
    "assigned": frozenset({"in_progress"}),
    "in_progress": frozenset({"submitted"}),
    "submitted": frozenset({"accepted", "rework"}),
    "rework": frozenset({"in_progress"}),
    "accepted": frozenset(),
}


class InvalidJobTransition(ValueError):
    """Raised when a job cannot move to the requested status."""


def public_status(internal_status: str) -> str:
    return INTERNAL_TO_PUBLIC.get(internal_status, internal_status)


def internal_status(status: str) -> str:
    try:
        return PUBLIC_TO_INTERNAL[status]
    except KeyError as exc:
        raise InvalidJobTransition(f"Unknown maintenance job status: {status}") from exc


def ensure_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, frozenset()):
        raise InvalidJobTransition(f"Transition {current}->{target} is not allowed")
