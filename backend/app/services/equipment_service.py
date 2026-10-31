"""Equipment service for business logic."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.equipment_repository import EquipmentRepository
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentUpdate,
)


class EquipmentError(Exception):
    """Raised when equipment operation fails."""

    def __init__(self, code: str, message: str, field: str | None = None):
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)


class EquipmentService:
    """Service for equipment operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = EquipmentRepository(session)

    async def get_equipment(
        self,
        equipment_id: UUID,
        site_id: UUID | None = None,
    ) -> EquipmentResponse:
        """Get equipment by ID with site scope validation."""
        equipment = await self.repo.get_by_id(equipment_id, site_id)
        if equipment is None:
            raise EquipmentError(
                "NOT_FOUND",
                "Equipment not found or access denied",
            )
        return EquipmentResponse.model_validate(equipment)

    async def list_equipment(
        self,
        site_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> EquipmentListResponse:
        """Get paginated list of equipment."""
        items, total = await self.repo.get_list(
            site_id=site_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return EquipmentListResponse(
            items=[EquipmentResponse.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def create_equipment(
        self,
        data: EquipmentCreate,
    ) -> EquipmentResponse:
        """Create new equipment with validation."""
        # Check asset code uniqueness within site
        is_unique = await self.repo.check_asset_code_unique(
            data.site_id,
            data.asset_code,
        )
        if not is_unique:
            raise EquipmentError(
                "CONFLICT",
                f"Asset code '{data.asset_code}' already exists on this site",
                field="asset_code",
            )

        equipment = await self.repo.create(data)
        return EquipmentResponse.model_validate(equipment)

    async def update_equipment(
        self,
        equipment_id: UUID,
        data: EquipmentUpdate,
        site_id: UUID | None = None,
    ) -> EquipmentResponse:
        """Update equipment with optional site scope."""
        # Check asset code uniqueness if being updated
        if data.asset_code if hasattr(data, "asset_code") and data.asset_code else False:
            is_unique = await self.repo.check_asset_code_unique(
                site_id or UUID(int=0),  # Need to get current site_id
                data.asset_code,
                exclude_equipment_id=equipment_id,
            )
            if not is_unique:
                raise EquipmentError(
                    "CONFLICT",
                    f"Asset code '{data.asset_code}' already exists on this site",
                    field="asset_code",
                )

        equipment = await self.repo.update(equipment_id, data, site_id)
        if equipment is None:
            raise EquipmentError(
                "NOT_FOUND",
                "Equipment not found or access denied",
            )
        return EquipmentResponse.model_validate(equipment)

    async def delete_equipment(
        self,
        equipment_id: UUID,
        site_id: UUID | None = None,
    ) -> bool:
        """Soft-delete equipment by retiring it."""
        return await self.repo.delete(equipment_id, site_id)
