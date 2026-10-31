"""Session SQLAlchemy model for user authentication."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Session(Base):
    """User authentication session with CSRF protection."""

    __tablename__ = "sessions"

    session_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    csrf_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default="now()",
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="sessions_expiry_check"),
        Index("idx_sessions_user_active", "user_id", "expires_at"),
    )
