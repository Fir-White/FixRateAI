"""Tests for authentication service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.users import User
from app.services.auth_service import AuthenticationError, AuthService


class TestPasswordHashing:
    """Test password hashing utilities."""

    def test_hash_password_creates_valid_hash(self) -> None:
        """Password hash should be created successfully."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 20

    def test_verify_password_with_correct_password(self) -> None:
        """Password verification should succeed with correct password."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_with_incorrect_password(self) -> None:
        """Password verification should fail with incorrect password."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password("wrongpassword", hashed) is False


class TestAuthService:
    """Test authentication service."""

    async def test_login_with_valid_credentials(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Login should succeed with valid credentials."""
        service = AuthService(db_session)

        result = await service.login("test@example.com", "testpassword")

        assert result.user.user_id == test_user.user_id
        assert result.user.email == test_user.email
        assert result.csrf_token is not None
        assert result.expires_at is not None

    async def test_login_with_invalid_email(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Login should fail with non-existent email."""
        service = AuthService(db_session)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.login("nonexistent@example.com", "password")

        assert exc_info.value.code == "INVALID_CREDENTIALS"

    async def test_login_with_invalid_password(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Login should fail with wrong password."""
        service = AuthService(db_session)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.login("test@example.com", "wrongpassword")

        assert exc_info.value.code == "INVALID_CREDENTIALS"

    async def test_login_with_inactive_user(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Login should fail for inactive user."""
        # Create inactive user
        user = User(
            full_name="Inactive User",
            email="inactive@example.com",
            password_hash=hash_password("password123"),
            is_active=False,
        )
        db_session.add(user)
        await db_session.flush()

        service = AuthService(db_session)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.login("inactive@example.com", "password123")

        assert exc_info.value.code == "USER_INACTIVE"

    async def test_create_user_with_password(
        self,
        db_session: AsyncSession,
    ) -> None:
        """User creation should hash password correctly."""
        service = AuthService(db_session)

        user_id = await service.create_user_with_password(
            full_name="New User",
            email="new@example.com",
            password="newpassword123",
        )

        # Verify user was created
        user = await db_session.get(User, user_id)
        assert user is not None
        assert user.email == "new@example.com"
        assert user.password_hash is not None
        assert verify_password("newpassword123", user.password_hash)
