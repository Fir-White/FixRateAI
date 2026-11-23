"""High-level RAG service orchestrating corpus indexing, ACL verification, and outbox consumption."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from .consumer import DurableOutboxConsumer
from .extractor import DocumentExtractor
from .index import RAGIndex
from .schemas import Chunk, DocumentMetadata, IndexSyncReport, OutboxEvent, RetrievalQuery, RetrievalResult

logger = logging.getLogger("fixrate.rag.service")


class RAGService:
    """Production service for dynamic RAG, operational regulation citations, and outbox synchronization."""

    def __init__(
        self,
        index: RAGIndex | None = None,
        consumer: DurableOutboxConsumer | None = None,
    ) -> None:
        self.index = index if index is not None else RAGIndex()
        self.consumer = consumer if consumer is not None else DurableOutboxConsumer(self.index)

    @classmethod
    def create_with_frozen_corpus(
        cls,
        corpus_dir: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> RAGService:
        """Factory creating and initializing RAGService with all frozen regulation documents loaded."""
        service = cls()
        service.load_frozen_corpus(corpus_dir=corpus_dir, manifest_path=manifest_path)
        return service

    def load_frozen_corpus(
        self,
        corpus_dir: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> int:
        """Loads and indexes the 5 frozen operational regulations cataloged in rag_corpus_manifest.json."""
        repo_root = Path(__file__).resolve().parents[3]

        if manifest_path is None:
            manifest_path = repo_root / "data" / "manifests" / "rag_corpus_manifest.json"
        else:
            manifest_path = Path(manifest_path)

        if not manifest_path.exists():
            raise FileNotFoundError(f"RAG corpus manifest not found at: {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        instruction_mapping = manifest_data.get("instruction_mapping", [])
        indexed_count = 0

        for item in instruction_mapping:
            app_src = item.get("approved_source", {})
            rel_path = app_src.get("file_path")
            if not rel_path:
                continue

            file_path = repo_root / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
            if not file_path.exists():
                logger.warning("Corpus file does not exist: %s", file_path)
                continue

            content = file_path.read_text(encoding="utf-8")
            override_meta = {
                "document_id": app_src.get("document_id"),
                "title": app_src.get("title"),
                "source_revision": app_src.get("source_revision"),
                "site_acl": item.get("site_acl", []),
                "role_acl": item.get("role_acl", ["chief_engineer", "executor"]),
                "equipment_class": item.get("equipment_class"),
            }

            metadata, chunks = DocumentExtractor.extract_from_markdown(
                content=content,
                file_path=file_path,
                default_equipment_class=item.get("equipment_class"),
                override_metadata=override_meta,
            )

            self.index.add_document(metadata, chunks)
            indexed_count += 1

        logger.info("Successfully loaded %d frozen regulation documents into RAGIndex", indexed_count)
        return indexed_count

    def query(
        self,
        query: RetrievalQuery | dict[str, Any] | str,
        site_id: str | None = None,
        user_role: str = "executor",
        equipment_class: str | None = None,
        requested_revision: str | None = None,
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> RetrievalResult:
        """Queries the RAG index with CR-17 role checks, site ACL verification, and anti-hallucination."""
        if isinstance(query, str):
            q_obj = RetrievalQuery(
                query=query,
                site_id=site_id,
                user_role=user_role,  # type: ignore[arg-type]
                equipment_class=equipment_class,
                requested_revision=requested_revision,
                top_k=top_k,
                min_score=min_score,
            )
        elif isinstance(query, dict):
            q_obj = RetrievalQuery.model_validate(query)
        else:
            q_obj = query

        return self.index.retrieve(q_obj)

    def sync_outbox(
        self,
        events: list[OutboxEvent | dict[str, Any]] | None = None,
        session: Any = None,
        site_id: str | UUID | None = None,
        limit: int = 100,
    ) -> IndexSyncReport:
        """Syncs pending outbox revision events either from an in-memory queue or direct PostgreSQL session."""
        if events is not None:
            return self.consumer.process_events(events)
        if session is not None:
            return self.consumer.process_db_events(session=session, site_id=site_id, limit=limit)
        return IndexSyncReport()

    def index_catalog_rows(
        self,
        rows: list[dict[str, Any]],
        site_id: str,
        source_revision: int | str,
        catalog_sha256: str | None = None,
    ) -> tuple[DocumentMetadata, list[Chunk]]:
        """Extracts and indexes tabular Excel catalog rows for an operational site."""
        metadata, chunks = DocumentExtractor.extract_from_catalog_rows(
            rows=rows,
            site_id=site_id,
            source_revision=source_revision,
            catalog_sha256=catalog_sha256,
        )
        self.index.add_document(metadata, chunks)
        return metadata, chunks
