"""Tests for role-based access control."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import Site, SiteMembership, User
from app.services.rbac_service import AccessDeniedError, RBACService


class TestRBACService:
    """Test RBAC permission checks."""

    async def test_get_user_api_roles(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should map DB roles to API roles correctly."""
        # Assign executive role (maps to admin)
        membership = SiteMembership(
            site_id=test_site.site_id,
            user_id=test_user.user_id,
            role="executive",
        )
        db_session.add(membership)
        await db_session.flush()

        service = RBACService(db_session)
        roles = await service.get_user_api_roles(test_user.user_id)

        assert "admin" in roles

    async def test_has_permission_with_matching_role(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should return True when user has required permission."""
        # Assign executive role (has equipment:write permission)
        membership = SiteMembership(
            site_id=test_site.site_id,
            user_id=test_user.user_id,
            role="executive",
        )
        db_session.add(membership)
        await db_session.flush()

        service = RBACService(db_session)
        has_perm = await service.has_permission(
            test_user.user_id,
            "equipment:write",
            test_site.site_id,
        )

        assert has_perm is True

    async def test_has_permission_without_matching_role(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should return False when user lacks required permission."""
        # Assign technician role (doesn't have equipment:write permission)
        membership = SiteMembership(
            site_id=test_site.site_id,
            user_id=test_user.user_id,
            role="technician",
        )
        db_session.add(membership)
        await db_session.flush()

        service = RBACService(db_session)
        has_perm = await service.has_permission(
            test_user.user_id,
            "equipment:write",
            test_site.site_id,
        )

        assert has_perm is False

    async def test_require_permission_raises_on_denial(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should raise AccessDeniedError when permission is missing."""
        # Assign technician role
        membership = SiteMembership(
            site_id=test_site.site_id,
            user_id=test_user.user_id,
            role="technician",
        )
        db_session.add(membership)
        await db_session.flush()

        service = RBACService(db_session)

        with pytest.raises(AccessDeniedError):
            await service.require_permission(
                test_user.user_id,
                "equipment:write",
                test_site.site_id,
            )

    async def test_has_site_access(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should return True when user has site access."""
        # Assign role on site
        membership = SiteMembership(
            site_id=test_site.site_id,
            user_id=test_user.user_id,
            role="engineer",
        )
        db_session.add(membership)
        await db_session.flush()

        service = RBACService(db_session)
        has_access = await service.has_site_access(test_user.user_id, test_site.site_id)

        assert has_access is True

    async def test_has_no_site_access_without_membership(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should return False when user has no site membership."""
        service = RBACService(db_session)
        has_access = await service.has_site_access(test_user.user_id, test_site.site_id)

        assert has_access is False

    async def test_is_admin_with_executive_role(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should return True for executive role (maps to admin)."""
        membership = SiteMembership(
            site_id=test_site.site_id,
            user_id=test_user.user_id,
            role="executive",
        )
        db_session.add(membership)
        await db_session.flush()

        service = RBACService(db_session)
        is_admin = await service.is_admin(test_user.user_id)

        assert is_admin is True

    async def test_is_admin_with_non_admin_role(
        self,
        db_session: AsyncSession,
        test_site: Site,
        test_user: User,
    ) -> None:
        """Should return False for non-admin roles."""
        membership = SiteMembership(
            site_id=test_site.site_id,
            user_id=test_user.user_id,
            role="technician",
        )
        db_session.add(membership)
        await db_session.flush()

        service = RBACService(db_session)
        is_admin = await service.is_admin(test_user.user_id)

        assert is_admin is False


class TestRolePermissions:
    """Test role permission matrix."""

    def test_all_roles_have_permissions(self) -> None:
        """All roles should have at least one permission."""
        from app.schemas.users import ROLE_PERMISSIONS

        for role, perms in ROLE_PERMISSIONS.items():
            assert len(perms) > 0, f"Role {role} has no permissions"

    def test_admin_has_broad_permissions(self) -> None:
        """Admin role should have broad permissions."""
        from app.schemas.users import ROLE_PERMISSIONS

        admin_perms = ROLE_PERMISSIONS.get("admin", frozenset())
        assert "users:write" in admin_perms
        assert "equipment:write" in admin_perms
        assert "schedule:write" in admin_perms

    def test_executor_has_limited_permissions(self) -> None:
        """Executor role should have limited permissions."""
        from app.schemas.users import ROLE_PERMISSIONS

        executor_perms = ROLE_PERMISSIONS.get("executor", frozenset())
        assert "task:read_assigned" in executor_perms
        assert "execution:write" in executor_perms
        # Executor shouldn't have admin permissions
        assert "users:write" not in executor_perms
        assert "equipment:write" not in executor_perms
