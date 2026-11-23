"""Dynamic RAG, Regulation Chunker, and Durable Outbox Consumer for FixRate AI."""
from __future__ import annotations

from .consumer import DurableOutboxConsumer
from .extractor import DocumentExtractor, compute_content_sha256, normalize_search_text
from .guardrails import AntiHallucinationGuardrail, PromptInjectionDefense
from .index import RAGIndex, stem_russian_word
from .schemas import (
    Chunk,
    Citation,
    DocumentMetadata,
    IndexSyncReport,
    OutboxEvent,
    RetrievalQuery,
    RetrievalResult,
)
from .service import RAGService, get_rag_service

__all__ = [
    "AntiHallucinationGuardrail",
    "Chunk",
    "Citation",
    "DocumentExtractor",
    "DocumentMetadata",
    "DurableOutboxConsumer",
    "IndexSyncReport",
    "OutboxEvent",
    "PromptInjectionDefense",
    "RAGIndex",
    "RAGService",
    "RetrievalQuery",
    "RetrievalResult",
    "compute_content_sha256",
    "get_rag_service",
    "normalize_search_text",
    "stem_russian_word",
]
