"""Дефекты, их фото и измерения."""
import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Defect(Base):
    """Дефект, предложенный AI или созданный/подтверждённый человеком."""

    __tablename__ = "defects"
    __table_args__ = (
        UniqueConstraint("defect_id", "request_id", name="uq_defect_request"),
        ForeignKeyConstraint(
            ["source_ai_result_id", "request_id"],
            ["ai_results.ai_result_id", "ai_results.request_id"],
            name="fk_defects_ai_result_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "confirmation_status IN ('suggested','confirmed','rejected')",
            name="defects_confirmation_status_check",
        ),
        CheckConstraint(
            "confirmation_status <> 'confirmed' OR "
            "(confirmed_by IS NOT NULL AND defect_type_id IS NOT NULL)",
            name="chk_defect_confirmation",
        ),
        Index("idx_defects_request", "request_id"),
    )

    defect_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "repair_requests.request_id",
            name="fk_defects_request",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    defect_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "defect_types.defect_type_id",
            name="fk_defects_type",
            ondelete="RESTRICT",
        ),
    )
    source_ai_result_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )
    description: Mapped[str | None] = mapped_column(Text)
    location_description: Mapped[str | None] = mapped_column(Text)
    confirmation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'suggested'"),
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            name="fk_defects_confirmer",
            ondelete="RESTRICT",
        ),
    )
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DefectPhoto(Base):
    """Связь дефекта с фото заявки; у дефекта не более одного главного фото."""

    __tablename__ = "defect_photos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["defect_id", "request_id"],
            ["defects.defect_id", "defects.request_id"],
            name="fk_defect_photos_defect_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["photo_id", "request_id"],
            ["request_photos.photo_id", "request_photos.request_id"],
            name="fk_defect_photos_photo_request",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_defect_single_primary_photo",
            "defect_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index("idx_defect_photos_photo", "photo_id"),
    )

    defect_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    photo_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DefectMeasurement(Base):
    """Измерение параметра дефекта с источником и версионированием."""

    __tablename__ = "defect_measurements"
    __table_args__ = (
        UniqueConstraint(
            "measurement_id",
            "defect_id",
            name="uq_measurement_defect",
        ),
        ForeignKeyConstraint(
            ["defect_id", "request_id"],
            ["defects.defect_id", "defects.request_id"],
            name="fk_measure_defect_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_ai_result_id", "request_id"],
            ["ai_results.ai_result_id", "ai_results.request_id"],
            name="fk_measure_ai_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_measurement_id", "defect_id"],
            [
                "defect_measurements.measurement_id",
                "defect_measurements.defect_id",
            ],
            name="fk_measure_previous_same_defect",
            ondelete="RESTRICT",
        ),
        CheckConstraint("value >= 0", name="defect_measurements_value_check"),
        CheckConstraint(
            "source_type IN ('manual','text','photo','document','derived')",
            name="defect_measurements_source_type_check",
        ),
        CheckConstraint(
            "verification_status IN ('unverified','confirmed','rejected')",
            name="defect_measurements_verification_status_check",
        ),
        CheckConstraint(
            "supersedes_measurement_id IS DISTINCT FROM measurement_id",
            name="chk_measurement_no_self_reference",
        ),
        Index(
            "uq_measure_current_per_parameter",
            "defect_id",
            "parameter_code",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("idx_measurements_request", "request_id"),
    )

    measurement_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    defect_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    parameter_code: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ai_result_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            name="fk_measure_user",
            ondelete="RESTRICT",
        ),
    )
    is_approximate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    verification_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'unverified'"),
    )
    supersedes_measurement_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
