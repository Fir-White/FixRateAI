import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.maintenance_api import (
    CalendarResponse,
    OperationCreate,
    RecurrenceRuleCreate,
    ROLE_PERMISSIONS,
)


EXAMPLES = Path(__file__).parents[1] / "examples" / "maintenance_api_examples.json"


def load_examples() -> dict:
    return json.loads(EXAMPLES.read_text(encoding="utf-8"))


def test_operation_preserves_decimal_norm_and_unconfirmed_duration() -> None:
    request = load_examples()["examples"][0]["request"]

    operation = OperationCreate.model_validate_json(json.dumps(request, ensure_ascii=False))

    assert operation.raw_norm_value == Decimal("1.000")
    assert operation.norm_unit == "unconfirmed"
    assert operation.planning_duration_minutes is None


def test_calendar_is_event_list_and_total_matches() -> None:
    response = load_examples()["examples"][1]["response"]

    calendar = CalendarResponse.model_validate_json(json.dumps(response, ensure_ascii=False))

    assert calendar.year == 2026
    assert calendar.month == 10
    assert calendar.total == len(calendar.items) == 1
    assert not any(key.startswith("day_") for key in response)


def test_confirmed_annual_rule_requires_matching_number_of_dates() -> None:
    payload = {
        "source_ref": "customer:sheet!D9",
        "data_origin": "customer",
        "regulation_version_id": UUID("00000000-0000-0000-0000-000000000001"),
        "source_text": "5/год",
        "kind": "explicit_dates",
        "confirmed": True,
        "explicit_dates": [date(2026, 1, 1)],
        "yearly_count": 5,
        "allowed_lead_days": 0,
    }

    with pytest.raises(ValidationError, match="yearly_count"):
        RecurrenceRuleCreate.model_validate(payload)


def test_create_models_reject_unknown_fields() -> None:
    payload = load_examples()["examples"][0]["request"] | {"unexpected": True}

    with pytest.raises(ValidationError, match="unexpected"):
        OperationCreate.model_validate(payload)


def test_role_permissions_are_explicit_and_non_empty() -> None:
    assert set(ROLE_PERMISSIONS) == {"admin", "dispatcher", "executor", "engineer"}
    assert all(permissions for permissions in ROLE_PERMISSIONS.values())
