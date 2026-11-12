import pytest

from app.maintenance_jobs import InvalidJobTransition, ensure_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("planned", "assigned"),
        ("assigned", "in_progress"),
        ("in_progress", "submitted"),
        ("submitted", "accepted"),
        ("submitted", "rework"),
        ("rework", "in_progress"),
    ],
)
def test_maintenance_job_transition_is_allowed(current, target):
    ensure_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("planned", "in_progress"),
        ("assigned", "submitted"),
        ("submitted", "planned"),
        ("accepted", "accepted"),
        ("accepted", "in_progress"),
        ("rework", "accepted"),
    ],
)
def test_maintenance_job_transition_rejects_invalid_edges(current, target):
    with pytest.raises(InvalidJobTransition):
        ensure_transition(current, target)
