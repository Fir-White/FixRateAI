"""User repository for database operations."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import Site, SiteMembership, User
from app.schemas.users import UserRole


class UserRepository:
    """Repository for user-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID with memberships."""
        result = await self.session.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        full_name: str,
        email: str,
        password_hash: str | None = None,
    ) -> User:
        """Create a new user."""
        user = User(
            full_name=full_name,
            email=email.lower(),
            password_hash=password_hash,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_is_active(self, user_id: UUID, is_active: bool) -> User | None:
        """Update user active status."""
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.is_active = is_active
        await self.session.flush()
        return user

    async def get_site_memberships(
        self,
        user_id: UUID,
        site_id: UUID | None = None,
    ) -> list[SiteMembership]:
        """Get user's site memberships."""
        query = select(SiteMembership).where(
            SiteMembership.user_id == user_id,
            SiteMembership.is_active.is_(True),
        )
        if site_id is not None:
            query = query.where(SiteMembership.site_id == site_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def assign_role(
        self,
        user_id: UUID,
        site_id: UUID,
        role: UserRole,
    ) -> SiteMembership:
        """Assign a role to user on a site."""
        membership = SiteMembership(
            user_id=user_id,
            site_id=site_id,
            role=role,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def get_site_members(self, site_id: UUID) -> list[User]:
        """Get all active users on a site."""
        result = await self.session.execute(
            select(User)
            .join(SiteMembership, User.user_id == SiteMembership.user_id)
            .where(
                SiteMembership.site_id == site_id,
                SiteMembership.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
        return list(result.scalars().all())
