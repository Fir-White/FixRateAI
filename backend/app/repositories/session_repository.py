"""Session repository for authentication operations."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


class SessionRepository:
    """Repository for session-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: UUID,
        csrf_token: str,
        expires_at: datetime,
        session_id: UUID | None = None,
    ) -> Session:
        """Create a new session."""
        session_model = Session(
            session_id=session_id,
            user_id=user_id,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        self.session.add(session_model)
        await self.session.flush()
        return session_model

    async def get_by_id(self, session_id: UUID) -> Session | None:
        """Get session by ID if not expired or revoked."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(Session).where(
                Session.session_id == session_id,
                Session.expires_at > now,
                Session.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def validate_csrf(self, session_id: UUID, csrf_token: str) -> bool:
        """Validate CSRF token for a session."""
        session = await self.get_by_id(session_id)
        if session is None:
            return False
        return session.csrf_token == csrf_token

    async def revoke(self, session_id: UUID) -> bool:
        """Revoke a session by setting revoked_at."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(Session)
            .where(
                Session.session_id == session_id,
                Session.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.session.flush()
        return result.rowcount > 0

    async def revoke_all_user_sessions(self, user_id: UUID) -> int:
        """Revoke all active sessions for a user."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(Session)
            .where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.session.flush()
        return result.rowcount

    async def cleanup_expired(self) -> int:
        """Delete expired sessions older than 24 hours."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(hours=24)
        result = await self.session.execute(
            delete(Session).where(Session.expires_at < cutoff)
        )
        await self.session.flush()
        return result.rowcount
