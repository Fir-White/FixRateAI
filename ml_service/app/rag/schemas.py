"""Data transfer objects and schemas for the Dynamic RAG and Outbox Consumer subsystem."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DocumentMetadata(BaseModel):
    """Metadata for an indexed regulation document or spreadsheet catalog."""
    model_config = ConfigDict(frozen=True)

    document_id: str
    title: str
    source_revision: str
    source_sha256: str | None = None
    expected_sha256: str | None = None
    equipment_class: str | None = None
    site_acl: list[str] = Field(default_factory=list, description="Allowed site IDs (empty = global)")
    role_acl: list[str] = Field(default_factory=lambda: ["chief_engineer", "executor"])
    file_path: str | None = None
    is_archived: bool = False
    is_stale: bool = False
    status: Literal["active", "stale", "archived", "deleted", "pending", "failed"] = "active"


class Chunk(BaseModel):
    """Atomic text snippet extracted from regulation or catalog with strict provenance."""
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    document_title: str
    source_revision: str
    section_title: str
    section_path: str = Field(default="", description="Full hierarchical heading breadcrumb")
    chunk_index: int = 0
    content: str
    clean_text: str = Field(description="Normalized lowercase text for search matching")
    equipment_class: str | None = None
    site_acl: list[str] = Field(default_factory=list)
    role_acl: list[str] = Field(default_factory=list)
    source_ref: str
    sha256: str
    is_stale: bool = False


class RetrievalQuery(BaseModel):
    """Query parameters for knowledge base retrieval under CR-17 role and site rules."""
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="Natural language search query or question")
    site_id: str | None = Field(default=None, description="Active site context of the requesting user")
    user_role: Literal["chief_engineer", "executor", "admin", "unauthorized"] | str = Field(
        default="executor", description="CR-17 user role"
    )
    equipment_class: str | None = Field(default=None, description="Optional equipment filter")
    requested_revision: str | None = Field(default=None, description="Explicit requested revision if any")
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.05, ge=0.0)


class Citation(BaseModel):
    """Structured verifiable citation returned to model context or UI."""
    model_config = ConfigDict(frozen=True)

    document_id: str
    document_title: str
    source_revision: str
    section_title: str
    section_path: str = ""
    source_ref: str
    snippet: str
    relevance_score: float
    is_stale: bool = False
    warning: str | None = None


class RetrievalResult(BaseModel):
    """Complete retrieval response with anti-hallucination guardrails and formatted context."""
    model_config = ConfigDict(frozen=True)

    status: Literal[
        "OK",
        "DOCUMENT_NOT_FOUND",
        "ACCESS_DENIED",
        "STALE_REVISION_WARNING",
        "EMPTY_QUERY",
    ]
    query: str
    citations: list[Citation] = Field(default_factory=list)
    context_text: str = ""
    disclaimer: str = (
        "Материалы базы знаний носят справочный характер и цитируются строго из утверждённых регламентов. "
        "Любое отступление от технологической карты требует письменного согласования главным инженером."
    )
    limitations: list[str] = Field(default_factory=list)
    error_code: str | None = None
    is_hallucination_blocked: bool = False


class OutboxEvent(BaseModel):
    """Durable event from source_revision_events outbox table."""
    model_config = ConfigDict(extra="ignore")

    event_id: UUID
    site_id: UUID | str
    scope: str
    source_revision: int
    source_sha256: str | None = None
    entity_type: str
    entity_id: UUID | str | None = None
    change_type: Literal["created", "updated", "revoked", "deleted", "source_revision", "text_change"] | str = "created"
    payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "published", "failed"] = "pending"
    created_at: datetime | None = None
    published_at: datetime | None = None


class IndexSyncReport(BaseModel):
    """Summary of outbox processing run."""
    model_config = ConfigDict(frozen=True)

    sync_id: UUID = Field(default_factory=uuid4)
    processed_events: int = 0
    published_events: int = 0
    failed_events: int = 0
    gap_detected: bool = False
    total_documents: int = 0
    total_chunks: int = 0
    details: list[str] = Field(default_factory=list)
    synced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
