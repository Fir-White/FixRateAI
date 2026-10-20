"""Запуски AI-пайплайна и их результаты по модулям CV/NLP/RAG."""
import datetime
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiRun(Base):
    """Один запуск пайплайна обработки заявки."""

    __tablename__ = "ai_runs"
    __table_args__ = (
        UniqueConstraint("run_id", "request_id", name="uq_run_request"),
        CheckConstraint(
            "status IN ('pending','running','completed','failed','needs_clarification')",
            name="ai_runs_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_snapshot) = 'object'",
            name="ai_runs_input_snapshot_check",
        ),
        Index("idx_runs_request_started", "request_id", text("started_at DESC")),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "repair_requests.request_id",
            name="fk_runs_request",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'pending'"),
    )
    pipeline_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class AiResult(Base):
    """Результат отдельного модуля пайплайна (CV, NLP или RAG)."""

    __tablename__ = "ai_results"
    __table_args__ = (
        UniqueConstraint("ai_result_id", "request_id", name="uq_result_request"),
        ForeignKeyConstraint(
            ["run_id", "request_id"],
            ["ai_runs.run_id", "ai_runs.request_id"],
            name="fk_results_run_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "module_type IN ('cv','nlp','rag')",
            name="ai_results_module_type_check",
        ),
        CheckConstraint(
            "status IN ('running','completed','failed','uncertain')",
            name="ai_results_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_reference) = 'object'",
            name="ai_results_input_reference_check",
        ),
        CheckConstraint(
            "jsonb_typeof(result_data) = 'object'",
            name="ai_results_result_data_check",
        ),
        CheckConstraint(
            "processing_time_ms >= 0",
            name="ai_results_processing_time_ms_check",
        ),
        Index("idx_results_run", "run_id"),
    )

    ai_result_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    module_type: Mapped[str] = mapped_column(String(20), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(150))
    model_version: Mapped[str | None] = mapped_column(String(100))
    input_reference: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    result_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'completed'"),
    )
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
