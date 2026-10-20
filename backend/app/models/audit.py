"""Журнал аудита действий пользователей, системы и AI."""
import datetime
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    """Неизменяемое событие аудита; изменения сущностей хранятся в JSONB."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user','system','ai')",
            name="audit_events_actor_type_check",
        ),
        CheckConstraint(
            "jsonb_typeof(changes) = 'object'",
            name="audit_events_changes_check",
        ),
        CheckConstraint(
            "(actor_type = 'user' AND user_id IS NOT NULL) OR "
            "(actor_type <> 'user' AND user_id IS NULL)",
            name="chk_audit_actor",
        ),
        Index("idx_audit_request_time", "request_id", text("created_at DESC")),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            name="fk_audit_user",
            ondelete="RESTRICT",
        ),
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "repair_requests.request_id",
            name="fk_audit_request",
            ondelete="RESTRICT",
        ),
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
