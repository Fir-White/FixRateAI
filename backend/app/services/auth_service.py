"""Authentication service for login/logout operations."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    generate_session_id,
    hash_password,
    verify_password,
)
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.users import SessionResponse, UserProfile


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class AuthService:
    """Service for authentication operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.session_repo = SessionRepository(session)
        self.settings = get_settings()

    async def login(self, email: str, password: str) -> SessionResponse:
        """Authenticate user and create session."""
        # Find user
        user = await self.user_repo.get_by_email(email)
        if user is None:
            raise AuthenticationError(
                "INVALID_CREDENTIALS",
                "Invalid email or password",
            )

        # Check if user is active
        if not user.is_active:
            raise AuthenticationError(
                "USER_INACTIVE",
                "User account is deactivated",
            )

        # Verify password
        if user.password_hash is None:
            raise AuthenticationError(
                "INVALID_CREDENTIALS",
                "Invalid email or password",
            )

        if not verify_password(password, user.password_hash):
            raise AuthenticationError(
                "INVALID_CREDENTIALS",
                "Invalid email or password",
            )

        # Create session
        session_id = generate_session_id()
        csrf_token = generate_csrf_token()
        expires_at = datetime.now(UTC) + timedelta(
            minutes=self.settings.jwt_expire_minutes
        )

        await self.session_repo.create(
            user_id=user.user_id,
            csrf_token=csrf_token,
            expires_at=expires_at,
            session_id=session_id,
        )

        # Get user profile with roles
        memberships = await self.user_repo.get_site_memberships(user.user_id)
        roles = [
            {"site_id": str(m.site_id), "role": m.role}
            for m in memberships
        ]

        return SessionResponse(
            user=UserProfile(
                user_id=user.user_id,
                full_name=user.full_name,
                email=user.email,
                roles=roles,
            ),
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

    async def logout(self, session_id: UUID) -> bool:
        """Revoke a session."""
        return await self.session_repo.revoke(session_id)

    async def validate_session(
        self,
        session_id: UUID,
        csrf_token: str | None = None,
    ) -> UserProfile | None:
        """Validate session and return user profile."""
        session = await self.session_repo.get_by_id(session_id)
        if session is None:
            return None

        # Optionally validate CSRF
        if csrf_token is not None:
            if not await self.session_repo.validate_csrf(session_id, csrf_token):
                return None

        # Get user
        user = await self.user_repo.get_by_id(session.user_id)
        if user is None or not user.is_active:
            return None

        # Get roles
        memberships = await self.user_repo.get_site_memberships(user.user_id)
        roles = [
            {"site_id": str(m.site_id), "role": m.role}
            for m in memberships
        ]

        return UserProfile(
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            roles=roles,
        )

    async def create_user_with_password(
        self,
        full_name: str,
        email: str,
        password: str,
    ) -> UUID:
        """Create a new user with hashed password."""
        password_hash = hash_password(password)
        user = await self.user_repo.create(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
        )
        return user.user_id
