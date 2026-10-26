"""Заявки на ремонт, фотографии и уточнения по заявке."""
import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RepairRequest(Base):
    """Заявка на ремонт: исходные данные для будущего черновика сметы."""

    __tablename__ = "repair_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created','processing','needs_clarification',"
            "'ready_for_review','closed','cancelled','failed')",
            name="repair_requests_status_check",
        ),
        Index(
            "idx_requests_building_date",
            "building_id",
            text("created_at DESC"),
        ),
        Index(
            "idx_requests_author_date",
            "created_by",
            text("created_at DESC"),
        ),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "buildings.building_id",
            name="fk_requests_building",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            name="fk_requests_author",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location_description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'created'"),
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class RequestPhoto(Base):
    """Метаданные загруженного фото; сам файл лежит за адаптером хранилища."""

    __tablename__ = "request_photos"
    __table_args__ = (
        UniqueConstraint(
            "storage_key",
            name="request_photos_storage_key_key",
        ),
        UniqueConstraint(
            "processed_storage_key",
            name="request_photos_processed_storage_key_key",
        ),
        UniqueConstraint("photo_id", "request_id", name="uq_photo_request"),
        CheckConstraint("file_size > 0", name="request_photos_file_size_check"),
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9A-Fa-f]{64}$'",
            name="request_photos_checksum_sha256_check",
        ),
        Index("idx_photos_request", "request_id"),
    )

    photo_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "repair_requests.request_id",
            name="fk_photos_request",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    processed_storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class RequestClarification(Base):
    """Вопрос пользователю, если для расчёта не хватает данных.

    Это штатный способ не выдумывать объём, норматив или цену.
    """

    __tablename__ = "request_clarifications"
    __table_args__ = (
        UniqueConstraint(
            "clarification_id",
            "request_id",
            name="uq_clarification_request",
        ),
        ForeignKeyConstraint(
            ["run_id", "request_id"],
            ["ai_runs.run_id", "ai_runs.request_id"],
            name="fk_clarifications_run_same_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_clarification_id", "request_id"],
            [
                "request_clarifications.clarification_id",
                "request_clarifications.request_id",
            ],
            name="fk_clarifications_previous_same_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('open','answered','cancelled','superseded')",
            name="request_clarifications_status_check",
        ),
        CheckConstraint(
            "status <> 'answered' OR (answer IS NOT NULL AND answered_at IS NOT NULL)",
            name="chk_clarification_answered",
        ),
        CheckConstraint(
            "supersedes_clarification_id IS DISTINCT FROM clarification_id",
            name="chk_clarification_not_self",
        ),
        Index("idx_clarifications_request", "request_id"),
    )

    clarification_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "repair_requests.request_id",
            name="fk_clarifications_request",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'open'"),
    )
    answered_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            name="fk_clarifications_user",
            ondelete="RESTRICT",
        ),
    )
    supersedes_clarification_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    answered_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
