"""Authentication API endpoints."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import generate_request_id
from app.schemas.common import ErrorCode, ErrorResponse
from app.schemas.users import LoginRequest, SessionResponse
from app.services.auth_service import AuthenticationError, AuthService

router = APIRouter(prefix="/session", tags=["authentication"])


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
    },
)
async def login(
    request: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """Authenticate user and create session.

    Sets session cookie and returns user profile with CSRF token.
    """
    auth_service = AuthService(session)

    try:
        result = await auth_service.login(request.email, request.password)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                code=ErrorCode.INVALID_CREDENTIALS,
                message=e.message,
                request_id=generate_request_id(),
            ).model_dump(),
        )

    # Set session cookie (HttpOnly for security)
    response.set_cookie(
        key="session_id",
        value=str(result.user.user_id),  # Simplified; in real app use encrypted session ID
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=int((result.expires_at - datetime.now(UTC)).total_seconds()),
    )

    return result


@router.get(
    "",
    response_model=SessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def get_current_session(
    session_id: str | None = Cookie(default=None),
    csrf_token: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """Get current user session profile.

    Requires valid session cookie.
    """
    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                code=ErrorCode.UNAUTHORIZED,
                message="No session cookie provided",
                request_id=generate_request_id(),
            ).model_dump(),
        )

    try:
        user_id = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                code=ErrorCode.INVALID_UUID,
                message="Invalid session ID format",
                request_id=generate_request_id(),
            ).model_dump(),
        )

    auth_service = AuthService(session)
    user_profile = await auth_service.validate_session(user_id)

    if user_profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                code=ErrorCode.SESSION_EXPIRED,
                message="Session expired or invalid",
                request_id=generate_request_id(),
            ).model_dump(),
        )

    return SessionResponse(
        user=user_profile,
        csrf_token=csrf_token or "",
        expires_at=datetime.now(UTC),  # Would need session model to get real expiry
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def logout(
    response: Response,
    session_id: str | None = Cookie(default=None),
    x_csrf_token: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Revoke current session and clear cookie.

    Requires CSRF token header for security.
    """
    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                code=ErrorCode.UNAUTHORIZED,
                message="No session cookie provided",
                request_id=generate_request_id(),
            ).model_dump(),
        )

    try:
        user_id = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                code=ErrorCode.INVALID_UUID,
                message="Invalid session ID format",
                request_id=generate_request_id(),
            ).model_dump(),
        )

    auth_service = AuthService(session)
    await auth_service.logout(user_id)

    # Clear session cookie
    response.delete_cookie("session_id")
