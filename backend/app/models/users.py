"""User and site membership SQLAlchemy models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Role enum values matching database constraints
UserRole = Literal["executive", "chief_engineer", "engineer", "technician"]


class Site(Base):
    """Physical site/facility being maintained."""

    __tablename__ = "sites"

    site_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(nullable=False)
    address: Mapped[str | None] = mapped_column()
    timezone: Mapped[str] = mapped_column(
        default="Asia/Yekaterinburg",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default="now()",
        nullable=False,
    )

    # Relationships
    memberships: Mapped[list["SiteMembership"]] = relationship(
        back_populates="site",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="sites_name_check"),
        CheckConstraint("length(trim(timezone)) > 0", name="sites_timezone_check"),
        Index("idx_sites_active_name", "is_active", "name"),
    )


class User(Base):
    """User account with optional password authentication."""

    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    full_name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False)
    password_hash: Mapped[str | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default="now()",
        nullable=False,
    )

    # Relationships
    memberships: Mapped[list["SiteMembership"]] = relationship(
        back_populates="user",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("length(trim(full_name)) > 0", name="users_full_name_check"),
        CheckConstraint("position('@' in email) > 1", name="users_email_check"),
        UniqueConstraint("email", name="users_email_unique"),
        Index("idx_users_email", "email"),
    )


class SiteMembership(Base):
    """User role and access on a specific site (RBAC basis)."""

    __tablename__ = "site_memberships"

    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.site_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[UserRole] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        server_default="now()",
        nullable=False,
    )

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")

    __table_args__ = (
        CheckConstraint(
            "role IN ('executive','chief_engineer','engineer','technician')",
            name="site_memberships_role_check",
        ),
        Index("idx_site_memberships_user", "user_id", "is_active"),
    )
