"""Equipment API endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import generate_request_id
from app.schemas.common import ErrorCode, ErrorResponse
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentUpdate,
)
from app.services.equipment_service import EquipmentError, EquipmentService

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get(
    "",
    response_model=EquipmentListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        403: {"model": ErrorResponse, "description": "Access denied"},
    },
)
async def list_equipment(
    site_id: UUID | None = Query(default=None, description="Filter by site ID"),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by equipment status",
    ),
    limit: int = Query(default=100, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Items to skip"),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentListResponse:
    """Get paginated list of equipment.

    Requires equipment:read permission on the site.
    """
    service = EquipmentService(session)

    try:
        return await service.list_equipment(
            site_id=site_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except EquipmentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code=e.code,
                message=e.message,
                request_id=generate_request_id(),
            ).model_dump(),
        )


@router.post(
    "",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"model": ErrorResponse, "description": "Access denied"},
        409: {"model": ErrorResponse, "description": "Conflict (duplicate asset code)"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def create_equipment(
    data: EquipmentCreate,
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    """Create new equipment.

    Requires equipment:write permission on the site.
    """
    service = EquipmentService(session)

    try:
        return await service.create_equipment(data)
    except EquipmentError as e:
        if e.code == "CONFLICT":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorResponse(
                    code=e.code,
                    message=e.message,
                    details=[{"field": e.field, "issue": e.message}] if e.field else [],
                    request_id=generate_request_id(),
                ).model_dump(),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code=e.code,
                message=e.message,
                request_id=generate_request_id(),
            ).model_dump(),
        )


@router.get(
    "/{equipment_id}",
    response_model=EquipmentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Equipment not found"},
    },
)
async def get_equipment(
    equipment_id: UUID,
    site_id: UUID | None = Query(default=None, description="Site scope"),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    """Get equipment by ID.

    Requires equipment:read permission on the site.
    """
    service = EquipmentService(session)

    try:
        return await service.get_equipment(equipment_id, site_id)
    except EquipmentError as e:
        if e.code == "NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    code=e.code,
                    message=e.message,
                    request_id=generate_request_id(),
                ).model_dump(),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code=e.code,
                message=e.message,
                request_id=generate_request_id(),
            ).model_dump(),
        )


@router.patch(
    "/{equipment_id}",
    response_model=EquipmentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Equipment not found"},
        409: {"model": ErrorResponse, "description": "Conflict or stale revision"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def update_equipment(
    equipment_id: UUID,
    data: EquipmentUpdate,
    site_id: UUID | None = Query(default=None, description="Site scope"),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    """Update equipment.

    Requires equipment:write permission on the site.
    """
    service = EquipmentService(session)

    try:
        return await service.update_equipment(equipment_id, data, site_id)
    except EquipmentError as e:
        if e.code == "NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    code=e.code,
                    message=e.message,
                    request_id=generate_request_id(),
                ).model_dump(),
            )
        if e.code == "CONFLICT":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorResponse(
                    code=e.code,
                    message=e.message,
                    details=[{"field": e.field, "issue": e.message}] if e.field else [],
                    request_id=generate_request_id(),
                ).model_dump(),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code=e.code,
                message=e.message,
                request_id=generate_request_id(),
            ).model_dump(),
        )


@router.delete(
    "/{equipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Equipment not found"},
    },
)
async def delete_equipment(
    equipment_id: UUID,
    site_id: UUID | None = Query(default=None, description="Site scope"),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete equipment by retiring it.

    Requires equipment:write permission on the site.
    """
    service = EquipmentService(session)
    deleted = await service.delete_equipment(equipment_id, site_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code=ErrorCode.NOT_FOUND,
                message="Equipment not found or access denied",
                request_id=generate_request_id(),
            ).model_dump(),
        )
