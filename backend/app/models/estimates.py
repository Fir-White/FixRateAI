"""Версии смет, их позиции и материалы."""
import datetime
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Estimate(Base):
    """Версия черновика сметы; утверждённая версия хранится как история."""

    __tablename__ = "estimates"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "version",
            name="uq_estimates_request_version",
        ),
        UniqueConstraint("estimate_id", "request_id", name="uq_estimate_request"),
        ForeignKeyConstraint(
            ["based_on_run_id", "request_id"],
            ["ai_runs.run_id", "ai_runs.request_id"],
            name="fk_estimates_run_same_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="estimates_version_check"),
        CheckConstraint(
            "status IN ('draft','needs_review','approved','rejected','superseded')",
            name="estimates_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_snapshot) = 'object'",
            name="estimates_input_snapshot_check",
        ),
        CheckConstraint("total_cost >= 0", name="estimates_total_cost_check"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="estimates_currency_check"),
        CheckConstraint(
            "status <> 'approved' OR "
            "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="chk_approved_has_reviewer",
        ),
        Index(
            "idx_estimates_request_recent",
            "request_id",
            text("version DESC"),
        ),
    )

    estimate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "repair_requests.request_id",
            name="fk_estimates_request",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'draft'"),
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(
        CHAR(3),
        nullable=False,
        server_default=text("'RUB'"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            name="fk_estimates_reviewer",
            ondelete="RESTRICT",
        ),
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    review_comment: Mapped[str | None] = mapped_column(Text)


class EstimateItem(Base):
    """Позиция ВОР: работа, объём, цена и след происхождения расчёта."""

    __tablename__ = "estimate_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["estimate_id", "request_id"],
            ["estimates.estimate_id", "estimates.request_id"],
            name="fk_items_estimate_same_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["defect_id", "request_id"],
            ["defects.defect_id", "defects.request_id"],
            name="fk_items_defect_same_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity >= 0", name="estimate_items_quantity_check"),
        CheckConstraint("unit_price >= 0", name="estimate_items_unit_price_check"),
        CheckConstraint("coefficient > 0", name="estimate_items_coefficient_check"),
        CheckConstraint("base_cost >= 0", name="estimate_items_base_cost_check"),
        CheckConstraint(
            "additional_materials_cost >= 0",
            name="estimate_items_additional_materials_cost_check",
        ),
        CheckConstraint("total_cost >= 0", name="estimate_items_total_cost_check"),
        CheckConstraint(
            "jsonb_typeof(calculation_details) = 'object'",
            name="estimate_items_calculation_details_check",
        ),
        CheckConstraint(
            "validation_status IN ('valid','blocked','needs_review')",
            name="estimate_items_validation_status_check",
        ),
        CheckConstraint(
            "source_snapshot IS NULL OR jsonb_typeof(source_snapshot) = 'object'",
            name="estimate_items_source_snapshot_check",
        ),
        CheckConstraint(
            "validation_status <> 'valid' OR ("
            "quantity IS NOT NULL AND quantity > 0 "
            "AND unit_code IS NOT NULL AND length(btrim(unit_code)) > 0 "
            "AND unit_price IS NOT NULL AND base_cost IS NOT NULL "
            "AND total_cost IS NOT NULL AND source_snapshot IS NOT NULL "
            "AND source_snapshot <> '{}'::jsonb "
            "AND (rate_id IS NOT NULL OR source_snapshot ->> 'origin' = 'manual')"
            ")",
            name="chk_item_valid_priced",
        ),
        CheckConstraint(
            "validation_status <> 'valid' OR "
            "total_cost = base_cost + COALESCE(additional_materials_cost, 0)",
            name="chk_item_valid_math",
        ),
        CheckConstraint(
            "validation_status <> 'valid' OR ("
            "source_snapshot IS NOT NULL "
            "AND jsonb_typeof(source_snapshot) = 'object' "
            "AND source_snapshot ? 'origin' "
            "AND ((rate_id IS NOT NULL "
            "AND COALESCE(source_snapshot ->> 'origin', '') IN ('normative','commercial','demo') "
            "AND COALESCE(source_snapshot ->> 'rate_id', '') = rate_id::text "
            "AND COALESCE(length(btrim(source_snapshot ->> 'source_id')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'source_series_id')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'source_type')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'source_title')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'source_version')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'rate_code')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'work_name')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'unit_code')), 0) > 0 "
            "AND COALESCE((source_snapshot ->> 'rate_unit_multiplier')::NUMERIC, -1) > 0 "
            "AND COALESCE((source_snapshot ->> 'base_price')::NUMERIC, -1) >= 0 "
            "AND COALESCE(source_snapshot ->> 'currency', '') ~ '^[A-Z]{3}$' "
            "AND COALESCE(length(btrim(source_snapshot ->> 'price_basis')), 0) > 0) "
            "OR (rate_id IS NULL "
            "AND COALESCE(source_snapshot ->> 'origin', '') = 'manual' "
            "AND COALESCE(length(btrim(source_snapshot ->> 'source_description')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'entered_by')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'basis')), 0) > 0 "
            "AND COALESCE(length(btrim(source_snapshot ->> 'unit_code')), 0) > 0 "
            "AND COALESCE((source_snapshot ->> 'unit_price')::NUMERIC, -1) >= 0 "
            "AND COALESCE(source_snapshot ->> 'currency', '') ~ '^[A-Z]{3}$')))",
            name="chk_item_source_snapshot_complete",
        ),
        Index("idx_items_estimate", "estimate_id"),
        Index("idx_items_defect", "defect_id"),
        Index("idx_items_rate", "rate_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    defect_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    rate_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "rates.rate_id",
            name="fk_items_rate",
            ondelete="RESTRICT",
        ),
    )
    work_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    unit_code: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    coefficient: Mapped[Decimal] = mapped_column(
        Numeric(14, 6),
        nullable=False,
        server_default=text("1"),
    )
    base_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    additional_materials_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2)
    )
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    calculation_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    validation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'needs_review'"),
    )
    source_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class EstimateMaterial(Base):
    """Материал позиции сметы и способ учёта его стоимости."""

    __tablename__ = "estimate_materials"
    __table_args__ = (
        CheckConstraint(
            "quantity >= 0",
            name="estimate_materials_quantity_check",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="estimate_materials_unit_price_check",
        ),
        CheckConstraint(
            "total_cost >= 0",
            name="estimate_materials_total_cost_check",
        ),
        CheckConstraint(
            "price_snapshot IS NULL OR jsonb_typeof(price_snapshot) = 'object'",
            name="estimate_materials_price_snapshot_check",
        ),
        CheckConstraint(
            "cost_treatment IN ('included_in_rate','additional','informational')",
            name="estimate_materials_cost_treatment_check",
        ),
        CheckConstraint(
            "cost_treatment <> 'additional' OR ("
            "unit_price IS NOT NULL AND total_cost IS NOT NULL "
            "AND (source_id IS NOT NULL OR "
            "(price_snapshot IS NOT NULL AND price_snapshot <> '{}'::jsonb))"
            ")",
            name="chk_material_additional_has_price",
        ),
        Index("idx_materials_item", "item_id"),
    )

    material_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "estimate_items.item_id",
            name="fk_materials_item",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    material_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "norm_sources.source_id",
            name="fk_materials_source",
            ondelete="RESTRICT",
        ),
    )
    price_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost_treatment: Mapped[str] = mapped_column(String(30), nullable=False)
