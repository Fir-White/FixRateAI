from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.dto import equipment_create_values, equipment_response
from app.schemas.maintenance_api import EquipmentCreate


def test_equipment_mapping_preserves_values_and_requires_explicit_metadata():
    site, system, kind, equipment = (uuid4() for _ in range(4))
    request = EquipmentCreate(site_id=site, equipment_type_id=kind, inventory_code="EQ-1",
                              name="Насос", commissioned_on=date(2026, 1, 1))
    values = equipment_create_values(request, system_id=system)
    assert values["system_id"] == system
    row = SimpleNamespace(equipment_id=equipment, **values)
    response = equipment_response(row, source_ref="verified record", data_origin="customer", revision=2)
    assert response.equipment_id == equipment
    assert response.site_id == request.site_id
    assert response.inventory_code == request.inventory_code
    assert response.commissioned_on == request.commissioned_on
    assert response.revision == 2
    with pytest.raises(TypeError):
        equipment_response(row)


def test_equipment_response_does_not_invent_status():
    row = SimpleNamespace(status="under_repair")
    with pytest.raises(ValueError, match="no agreed"):
        equipment_response(row, source_ref="source", data_origin="customer", revision=1)


@pytest.mark.parametrize("state", ["active", "retired"])
def test_equipment_status_round_trip(state):
    request = EquipmentCreate(site_id=uuid4(), equipment_type_id=uuid4(), inventory_code="x", name="x", state=state)
    row = SimpleNamespace(equipment_id=uuid4(), **equipment_create_values(request, system_id=uuid4()))
    assert equipment_response(row, source_ref="source", data_origin="customer", revision=1).state == state


def test_out_of_service_is_not_mapped_to_under_repair():
    request = EquipmentCreate(site_id=uuid4(), equipment_type_id=uuid4(), inventory_code="x", name="x", state="out_of_service")
    with pytest.raises(ValueError, match="no agreed"):
        equipment_create_values(request, system_id=uuid4())
