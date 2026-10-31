"""Security utilities: password hashing, JWT tokens, CSRF protection."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

# NOTE: For production, install and use passlib with bcrypt:
# pip install passlib[bcrypt]
# from passlib.context import CryptContext
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Temporary implementation using hashlib (SHA-256 + salt)
# WARNING: Not recommended for production - use bcrypt instead
def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt.
    
    WARNING: This is a temporary implementation. For production,
    install passlib[bcrypt] and use bcrypt hashing.
    """
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${password_hash}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.
    
    WARNING: This is a temporary implementation. For production,
    install passlib[bcrypt] and use bcrypt verification.
    """
    try:
        salt, password_hash = hashed_password.split("$", 1)
        computed_hash = hashlib.sha256((salt + plain_password).encode()).hexdigest()
        return secrets.compare_digest(computed_hash, password_hash)
    except (ValueError, AttributeError):
        return False


# Try to import jose for JWT, fall back to manual implementation
try:
    from jose import JWTError, jwt
    
    def create_access_token(
        user_id: UUID,
        session_id: UUID,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create a JWT access token for a user session."""
        from app.core.config import get_settings
        settings = get_settings()

        if expires_delta is None:
            expires_delta = timedelta(minutes=settings.jwt_expire_minutes)

        expire = datetime.now(UTC) + expires_delta

        to_encode = {
            "sub": str(user_id),
            "sid": str(session_id),
            "exp": expire,
            "iat": datetime.now(UTC),
        }

        return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


    def decode_access_token(token: str) -> dict[str, Any] | None:
        """Decode and validate a JWT access token."""
        from app.core.config import get_settings
        settings = get_settings()

        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except JWTError:
            return None

except ImportError:
    # Fallback: simple token without JWT (for development only)
    def create_access_token(
        user_id: UUID,
        session_id: UUID,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create a simple token (non-JWT fallback)."""
        # In production, install python-jose for proper JWT
        return secrets.token_urlsafe(32)


    def decode_access_token(token: str) -> dict[str, Any] | None:
        """Decode token (fallback - returns None)."""
        # Cannot decode simple tokens
        return None


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def generate_session_id() -> UUID:
    """Generate a new session identifier."""
    return UUID(secrets.token_hex(16), version=4)


def generate_request_id() -> str:
    """Generate a request ID for correlation."""
    return secrets.token_hex(16)
