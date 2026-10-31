"""Users API endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import generate_request_id
from app.schemas.common import ErrorCode, ErrorResponse
from app.schemas.users import (
    ApiRole,
    ROLE_PERMISSIONS,
    RolePermissions,
    UserResponse,
    UserSiteRole,
)
from app.repositories.user_repository import UserRepository
from app.services.rbac_service import AccessDeniedError, RBACService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
    responses={
        403: {"model": ErrorResponse, "description": "Access denied"},
    },
)
async def list_users(
    session: AsyncSession = Depends(get_db_session),
    session_id: str | None = None,  # Would come from auth middleware
) -> list[UserResponse]:
    """List all active users.

    Requires admin permissions.
    """
    # TODO: Get authenticated user from middleware
    # For now, return empty list
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=ErrorResponse(
            code="NOT_IMPLEMENTED",
            message="User listing not yet implemented",
            request_id=generate_request_id(),
        ).model_dump(),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def get_current_user(
    session: AsyncSession = Depends(get_db_session),
    session_id: str | None = None,  # Would come from auth middleware
) -> UserResponse:
    """Get current authenticated user profile.

    Requires authentication.
    """
    # TODO: Get authenticated user from middleware
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=ErrorResponse(
            code="NOT_IMPLEMENTED",
            message="Current user endpoint not yet implemented",
            request_id=generate_request_id(),
        ).model_dump(),
    )


@router.get(
    "/roles",
    response_model=list[RolePermissions],
    status_code=status.HTTP_200_OK,
)
async def get_role_permissions() -> list[RolePermissions]:
    """Get all available API roles and their permissions.

    Public endpoint for documentation purposes.
    """
    return [
        RolePermissions(role=role, permissions=list(perms))
        for role, perms in ROLE_PERMISSIONS.items()
    ]


@router.get(
    "/{user_id}/roles",
    response_model=list[UserSiteRole],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "User not found"},
    },
)
async def get_user_roles(
    user_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    # session_id: str | None = None,  # Would come from auth middleware
) -> list[UserSiteRole]:
    """Get user's roles across all sites.

    Requires admin permissions or self-access.
    """
    user_repo = UserRepository(session)

    # Check if user exists
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code=ErrorCode.NOT_FOUND,
                message="User not found",
                request_id=generate_request_id(),
            ).model_dump(),
        )

    # Get memberships
    memberships = await user_repo.get_site_memberships(user_id)
    return [
        UserSiteRole(
            site_id=m.site_id,
            user_id=m.user_id,
            role=m.role,
            is_active=m.is_active,
            joined_at=m.joined_at,
        )
        for m in memberships
    ]
