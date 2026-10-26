"""Справочные таблицы: пользователи, здания, типы дефектов и источники норм."""
import datetime
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """Пользователь системы: оператор, сметчик или администратор."""

    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
        CheckConstraint(
            "role IN ('operator','estimator','admin')",
            name="users_role_check",
        ),
        CheckConstraint(
            "length(btrim(email)) > 0",
            name="chk_user_email_nonempty",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'operator'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class Building(Base):
    """Здание (объект ремонта) и его паспортные характеристики."""

    __tablename__ = "buildings"
    __table_args__ = (
        CheckConstraint(
            "construction_year BETWEEN 1800 AND 2200",
            name="buildings_construction_year_check",
        ),
        CheckConstraint("floors_count > 0", name="buildings_floors_count_check"),
        CheckConstraint("total_area > 0", name="buildings_total_area_check"),
        CheckConstraint(
            "jsonb_typeof(additional_properties) = 'object'",
            name="buildings_additional_properties_check",
        ),
    )

    building_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    address: Mapped[str] = mapped_column(Text, nullable=False)
    building_type: Mapped[str | None] = mapped_column(String(100))
    construction_year: Mapped[int | None] = mapped_column(SmallInteger)
    floors_count: Mapped[int | None] = mapped_column(SmallInteger)
    total_area: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    wall_material: Mapped[str | None] = mapped_column(String(100))
    additional_properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DefectType(Base):
    """Справочник типов дефектов (код + человекочитаемое название)."""

    __tablename__ = "defect_types"
    __table_args__ = (
        UniqueConstraint("code", name="defect_types_code_key"),
    )

    defect_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )


class NormSource(Base):
    """Источник нормативной или коммерческой расценки.

    `DEMO` — вымышленный источник для пилота; он не является подтверждённым
    ФЕР/ТЕР и не должен выдаваться за норматив.
    """

    __tablename__ = "norm_sources"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_series_id",
            name="uq_norm_source_series_identity",
        ),
        ForeignKeyConstraint(
            ["supersedes_source_id", "source_series_id"],
            ["norm_sources.source_id", "norm_sources.source_series_id"],
            name="fk_norm_source_previous_same_series",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_type IN ('FER','FERR','TER','TERR','COMMERCIAL','DEMO')",
            name="norm_sources_source_type_check",
        ),
        CheckConstraint(
            "NOT is_verified OR source_url IS NOT NULL OR document_reference IS NOT NULL",
            name="chk_verified_has_reference",
        ),
        CheckConstraint(
            "length(btrim(title)) > 0",
            name="chk_norm_source_title_nonempty",
        ),
        CheckConstraint(
            "edition IS NULL OR length(btrim(edition)) > 0",
            name="chk_norm_source_edition_nonempty",
        ),
        CheckConstraint(
            "provider_name IS NULL OR length(btrim(provider_name)) > 0",
            name="chk_norm_source_provider_nonempty",
        ),
        CheckConstraint(
            "valid_to IS NULL OR effective_date IS NULL OR valid_to >= effective_date",
            name="chk_norm_source_valid_period",
        ),
        CheckConstraint(
            "default_currency IS NULL OR default_currency ~ '^[A-Z]{3}$'",
            name="chk_norm_source_currency",
        ),
        CheckConstraint(
            "source_type <> 'DEMO' OR NOT is_verified",
            name="chk_demo_source_unverified",
        ),
        CheckConstraint(
            "NOT is_verified OR ("
            "COALESCE(NULLIF(btrim(edition), ''), effective_date::text) IS NOT NULL "
            "AND COALESCE(NULLIF(btrim(source_url), ''), "
            "NULLIF(btrim(document_reference), '')) IS NOT NULL "
            "AND (source_type IN ('FER','FERR','TER','TERR') OR ("
            "source_type = 'COMMERCIAL' AND provider_name IS NOT NULL "
            "AND default_currency IS NOT NULL)))",
            name="chk_verified_source_details",
        ),
        Index(
            "uq_norm_sources_current_series",
            "source_series_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index(
            "idx_norm_sources_catalog_lookup",
            "source_type",
            "region",
            "is_current",
            text("effective_date DESC"),
        ),
        Index(
            "idx_norm_sources_series_effective",
            "source_series_id",
            text("effective_date DESC NULLS LAST"),
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_series_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    supersedes_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    provider_name: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[datetime.date | None] = mapped_column(Date)
    effective_date: Mapped[datetime.date | None] = mapped_column(Date)
    valid_to: Mapped[datetime.date | None] = mapped_column(Date)
    default_currency: Mapped[str | None] = mapped_column(CHAR(3))
    source_url: Mapped[str | None] = mapped_column(Text)
    document_reference: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
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
