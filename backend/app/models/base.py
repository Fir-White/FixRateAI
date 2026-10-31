"""SQLAlchemy model base class."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    type_annotation_map = {
        UUID: PG_UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }

    @property
    def dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return {
            c.name: getattr(self, c.name) for c in self.__table__.columns
        }
