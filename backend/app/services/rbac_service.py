"""Role-based access control service."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.schemas.users import (
    ROLE_PERMISSIONS,
    ApiRole,
    DB_TO_API_ROLE,
    UserRole,
)


class AccessDeniedError(Exception):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Access denied"):
        self.message = message
        super().__init__(message)


class RBACService:
    """Service for role-based access control."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_user_api_roles(
        self,
        user_id: UUID,
        site_id: UUID | None = None,
    ) -> list[ApiRole]:
        """Get user's API roles (mapped from DB roles)."""
        memberships = await self.user_repo.get_site_memberships(user_id, site_id)
        api_roles = set()
        for m in memberships:
            if m.role in DB_TO_API_ROLE:
                api_roles.add(DB_TO_API_ROLE[m.role])
        return list(api_roles)

    async def has_permission(
        self,
        user_id: UUID,
        permission: str,
        site_id: UUID | None = None,
    ) -> bool:
        """Check if user has a specific permission."""
        api_roles = await self.get_user_api_roles(user_id, site_id)
        for role in api_roles:
            if permission in ROLE_PERMISSIONS.get(role, frozenset()):
                return True
        return False

    async def require_permission(
        self,
        user_id: UUID,
        permission: str,
        site_id: UUID | None = None,
    ) -> None:
        """Require user to have a permission or raise AccessDeniedError."""
        if not await self.has_permission(user_id, permission, site_id):
            raise AccessDeniedError(
                f"User lacks required permission: {permission}"
            )

    async def has_site_access(
        self,
        user_id: UUID,
        site_id: UUID,
    ) -> bool:
        """Check if user has any role on a site."""
        memberships = await self.user_repo.get_site_memberships(user_id, site_id)
        return len(memberships) > 0

    async def require_site_access(
        self,
        user_id: UUID,
        site_id: UUID,
    ) -> None:
        """Require user to have access to a site or raise AccessDeniedError."""
        if not await self.has_site_access(user_id, site_id):
            raise AccessDeniedError(
                "User does not have access to this site"
            )

    async def is_admin(
        self,
        user_id: UUID,
        site_id: UUID | None = None,
    ) -> bool:
        """Check if user has admin role."""
        api_roles = await self.get_user_api_roles(user_id, site_id)
        return "admin" in api_roles

    async def require_admin(
        self,
        user_id: UUID,
        site_id: UUID | None = None,
    ) -> None:
        """Require user to be admin or raise AccessDeniedError."""
        if not await self.is_admin(user_id, site_id):
            raise AccessDeniedError("Admin access required")
