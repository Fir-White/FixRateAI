"""Расценки и поисковые фрагменты нормативных документов."""
import datetime
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class Rate(Base):
    """Расценка на работу с явным источником и областью стоимости.

    `DEMO`-расценки не являются подтверждёнными ФЕР/ТЕР.
    """

    __tablename__ = "rates"
    __table_args__ = (
        UniqueConstraint("rate_id", "source_id", name="uq_rate_source"),
        UniqueConstraint("source_id", "rate_code", name="uq_rate_code_source"),
        CheckConstraint(
            "rate_unit_multiplier > 0",
            name="rates_rate_unit_multiplier_check",
        ),
        CheckConstraint("base_price >= 0", name="rates_base_price_check"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="rates_currency_check"),
        CheckConstraint(
            "price_basis IN ('commercial','normative_base','demo')",
            name="rates_price_basis_check",
        ),
        CheckConstraint(
            "cost_scope IN ('work_only','all_inclusive','resource_based')",
            name="rates_cost_scope_check",
        ),
        Index(
            "idx_rates_work_name",
            text("to_tsvector('russian', work_name)"),
            postgresql_using="gin",
        ),
    )

    rate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "norm_sources.source_id",
            name="fk_rates_source",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    rate_code: Mapped[str | None] = mapped_column(String(100))
    work_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit_code: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_unit_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        server_default=text("1"),
    )
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    price_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    cost_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )


class NormativeChunk(Base):
    """Фрагмент нормативного документа; вектор без фиксированной размерности.

    Размерность и HNSW/IVFFlat-индекс появятся отдельной миграцией после
    выбора embedding-модели.
    """

    __tablename__ = "normative_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "chunk_index",
            name="uq_chunk_source_index",
        ),
        ForeignKeyConstraint(
            ["rate_id", "source_id"],
            ["rates.rate_id", "rates.source_id"],
            name="fk_chunks_rate_same_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint("chunk_index >= 0", name="normative_chunks_chunk_index_check"),
        CheckConstraint(
            "length(btrim(content)) > 0",
            name="normative_chunks_content_check",
        ),
        CheckConstraint(
            "(embedding IS NULL) = (embedding_model IS NULL)",
            name="chk_chunk_embedding_model",
        ),
        CheckConstraint(
            "jsonb_typeof(source_locator) = 'object'",
            name="normative_chunks_source_locator_check",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="normative_chunks_metadata_check",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9A-Fa-f]{64}$'",
            name="normative_chunks_content_hash_check",
        ),
        Index(
            "idx_chunks_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        Index("idx_chunks_rate", "rate_id"),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "norm_sources.source_id",
            name="fk_chunks_source",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    rate_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    embedding_model: Mapped[str | None] = mapped_column(String(150))
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', content)", persisted=True),
    )
    source_locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    # В Python нельзя назвать атрибут `metadata`: это имя занято DeclarativeBase.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
