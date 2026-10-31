"""Equipment repository for database operations."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipment import Equipment
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate


class EquipmentRepository:
    """Repository for equipment-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self,
        equipment_id: UUID,
        site_id: UUID | None = None,
    ) -> Equipment | None:
        """Get equipment by ID with optional site scope."""
        query = select(Equipment).where(Equipment.equipment_id == equipment_id)
        if site_id is not None:
            query = query.where(Equipment.site_id == site_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_list(
        self,
        site_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Equipment], int]:
        """Get paginated list of equipment with optional filters."""
        # Base query
        base_query = select(Equipment)

        # Apply filters
        if site_id is not None:
            base_query = base_query.where(Equipment.site_id == site_id)
        if status is not None:
            base_query = base_query.where(Equipment.status == status)

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        query = base_query.order_by(Equipment.asset_code).limit(limit).offset(offset)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def create(self, data: EquipmentCreate) -> Equipment:
        """Create new equipment."""
        equipment = Equipment(
            site_id=data.site_id,
            system_id=data.system_id,
            equipment_type_id=data.equipment_type_id,
            parent_equipment_id=data.parent_equipment_id,
            asset_code=data.asset_code,
            name=data.name,
            serial_number=data.serial_number,
            commissioned_on=data.commissioned_on,
            location=data.location,
            properties=data.properties,
            status=data.status,
        )
        self.session.add(equipment)
        await self.session.flush()
        return equipment

    async def update(
        self,
        equipment_id: UUID,
        data: EquipmentUpdate,
        site_id: UUID | None = None,
    ) -> Equipment | None:
        """Update equipment with optional site scope."""
        equipment = await self.get_by_id(equipment_id, site_id)
        if equipment is None:
            return None

        # Update fields that are provided
        update_data = data.model_dump(exclude_unset=True, exclude={"expected_revision"})
        for field, value in update_data.items():
            setattr(equipment, field, value)

        await self.session.flush()
        return equipment

    async def delete(self, equipment_id: UUID, site_id: UUID | None = None) -> bool:
        """Soft-delete equipment by setting status to retired."""
        equipment = await self.get_by_id(equipment_id, site_id)
        if equipment is None:
            return False

        equipment.status = "retired"
        await self.session.flush()
        return True

    async def check_asset_code_unique(
        self,
        site_id: UUID,
        asset_code: str,
        exclude_equipment_id: UUID | None = None,
    ) -> bool:
        """Check if asset code is unique within a site."""
        query = select(Equipment).where(
            Equipment.site_id == site_id,
            Equipment.asset_code == asset_code,
        )
        if exclude_equipment_id is not None:
            query = query.where(Equipment.equipment_id != exclude_equipment_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none() is None
