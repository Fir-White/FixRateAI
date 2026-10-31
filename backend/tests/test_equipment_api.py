"""Tests for equipment API endpoints."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.equipment import Equipment
from app.models.users import Site, User
from app.schemas.equipment import EquipmentCreate


class TestEquipmentAPI:
    """Test equipment CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_equipment_empty(
        self,
        db_session: AsyncSession,
    ) -> None:
        """List endpoint should return empty list initially."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/equipment")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_create_equipment_success(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_system,
        test_equipment_type,
    ) -> None:
        """Create endpoint should create equipment successfully."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/equipment",
                json={
                    "site_id": str(test_site.site_id),
                    "system_id": str(test_system.system_id),
                    "equipment_type_id": str(test_equipment_type.equipment_type_id),
                    "asset_code": "TEST-001",
                    "name": "Test Equipment",
                    "status": "active",
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["asset_code"] == "TEST-001"
        assert data["name"] == "Test Equipment"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_equipment_duplicate_asset_code(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_system,
    ) -> None:
        """Create endpoint should reject duplicate asset codes."""
        # Create first equipment
        equipment1 = Equipment(
            site_id=test_site.site_id,
            system_id=test_system.system_id,
            asset_code="DUPLICATE-001",
            name="First Equipment",
        )
        db_session.add(equipment1)
        await db_session.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/equipment",
                json={
                    "site_id": str(test_site.site_id),
                    "system_id": str(test_system.system_id),
                    "asset_code": "DUPLICATE-001",
                    "name": "Second Equipment",
                    "status": "active",
                },
            )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert "already exists" in data["message"]

    @pytest.mark.asyncio
    async def test_get_equipment_by_id(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_system,
    ) -> None:
        """Get endpoint should return equipment by ID."""
        # Create equipment
        equipment = Equipment(
            site_id=test_site.site_id,
            system_id=test_system.system_id,
            asset_code="GET-001",
            name="Get Test Equipment",
            status="active",
        )
        db_session.add(equipment)
        await db_session.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/equipment/{equipment.equipment_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["equipment_id"] == str(equipment.equipment_id)
        assert data["asset_code"] == "GET-001"

    @pytest.mark.asyncio
    async def test_get_equipment_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Get endpoint should return 404 for non-existent equipment."""
        from uuid import uuid4

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/equipment/{uuid4()}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_equipment_success(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_system,
    ) -> None:
        """Update endpoint should modify equipment."""
        # Create equipment
        equipment = Equipment(
            site_id=test_site.site_id,
            system_id=test_system.system_id,
            asset_code="UPDATE-001",
            name="Original Name",
            status="active",
        )
        db_session.add(equipment)
        await db_session.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/equipment/{equipment.equipment_id}",
                json={
                    "name": "Updated Name",
                    "status": "under_repair",
                },
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["status"] == "under_repair"

    @pytest.mark.asyncio
    async def test_delete_equipment_success(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_system,
    ) -> None:
        """Delete endpoint should retire equipment."""
        # Create equipment
        equipment = Equipment(
            site_id=test_site.site_id,
            system_id=test_system.system_id,
            asset_code="DELETE-001",
            name="Delete Test Equipment",
            status="active",
        )
        db_session.add(equipment)
        await db_session.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(f"/api/v1/equipment/{equipment.equipment_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify equipment is retired
        from app.models.equipment import Equipment
        result = await db_session.get(Equipment, equipment.equipment_id)
        assert result.status == "retired"


class TestEquipmentValidation:
    """Test equipment validation rules."""

    @pytest.mark.asyncio
    async def test_create_equipment_invalid_status(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_system,
    ) -> None:
        """Create endpoint should reject invalid status."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/equipment",
                json={
                    "site_id": str(test_site.site_id),
                    "system_id": str(test_system.system_id),
                    "asset_code": "INVALID-001",
                    "name": "Invalid Status Equipment",
                    "status": "invalid_status",
                },
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_create_equipment_missing_required_fields(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Create endpoint should reject missing required fields."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/equipment",
                json={
                    "name": "Missing Fields Equipment",
                },
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
