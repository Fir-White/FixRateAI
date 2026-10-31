"""Only mappings that have a lossless interpretation in the current DDL."""
from uuid import UUID
from typing import Literal
from app.schemas.maintenance_api import EquipmentCreate, EquipmentResponse


def equipment_create_values(request: EquipmentCreate, *, system_id: UUID) -> dict:
    # REST has no system_id, whereas SQL requires it. Never guess the system.
    # out_of_service does not mean under_repair and is not in the SQL CHECK.
    if request.state == "out_of_service":
        raise ValueError("out_of_service has no agreed SQL status mapping")
    return {
        "site_id": request.site_id, "system_id": system_id,
        "equipment_type_id": request.equipment_type_id,
        "asset_code": request.inventory_code, "name": request.name,
        "commissioned_on": request.commissioned_on, "status": request.state,
    }


def equipment_response(equipment, *, source_ref: str,
                       data_origin: Literal["customer", "synthetic_demo"],
                       revision: int) -> EquipmentResponse:
    """Supplement with authoritative persisted metadata, never inferred defaults.

    The current equipment table does not store these three values; callers must
    not construct them from guesses, request data, or constants.
    """
    if equipment.status not in ("active", "retired"):
        raise ValueError("SQL equipment status has no agreed DTO mapping")
    return EquipmentResponse(
        equipment_id=equipment.equipment_id, site_id=equipment.site_id,
        equipment_type_id=equipment.equipment_type_id, inventory_code=equipment.asset_code,
        name=equipment.name, commissioned_on=equipment.commissioned_on,
        state=equipment.status, source_ref=source_ref, data_origin=data_origin, revision=revision,
    )
