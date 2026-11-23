"""High-level RAG service orchestrating corpus indexing, ACL verification, and outbox consumption."""
from __future__ import annotations

import hashlib
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

_GLOBAL_RAG_SERVICE: RAGService | None = None


class RAGService:
    """Production service for dynamic RAG, operational regulation citations, and outbox synchronization."""

    def __init__(
        self,
        index: RAGIndex | None = None,
        consumer: DurableOutboxConsumer | None = None,
    ) -> None:
        self.index = index if index is not None else RAGIndex()
        self.consumer = consumer if consumer is not None else DurableOutboxConsumer(self.index)
        self.rebuilt_from_storage: bool = False

    @classmethod
    def create_with_frozen_corpus(
        cls,
        corpus_dir: str | Path | None = None,
        manifest_path: str | Path | None = None,
        verify_integrity: bool = True,
    ) -> RAGService:
        """Factory creating and initializing RAGService with all frozen regulation documents loaded and SHA-verified."""
        service = cls()
        service.load_frozen_corpus(corpus_dir=corpus_dir, manifest_path=manifest_path, verify_integrity=verify_integrity)
        return service

    @staticmethod
    def verify_manifest_integrity(manifest_path: str | Path | None = None) -> tuple[bool, list[str]]:
        """Verifies manifest canonical checksum and all physical document SHA-256 hashes against disk."""
        repo_root = Path(__file__).resolve().parents[3]
        if manifest_path is None:
            manifest_path = repo_root / "data" / "manifests" / "rag_corpus_manifest.json"
        else:
            manifest_path = Path(manifest_path)

        errors: list[str] = []
        if not manifest_path.exists():
            return False, [f"Manifest file not found: {manifest_path}"]

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Verify manifest's own canonical checksum
        declared_checksum = data.get("checksum", "")
        if not declared_checksum or not declared_checksum.startswith("sha256:"):
            errors.append("Manifest missing valid 'checksum' field (expected 'sha256:<hash>')")
        else:
            expected_hash = declared_checksum.split(":", 1)[1]
            data_copy = {k: v for k, v in data.items() if k != "checksum"}
            canonical_blob = json.dumps(data_copy, sort_keys=True, ensure_ascii=False).encode("utf-8")
            actual_hash = hashlib.sha256(canonical_blob).hexdigest()
            if actual_hash != expected_hash:
                errors.append(
                    f"Manifest canonical checksum mismatch: declared {declared_checksum}, calculated sha256:{actual_hash}"
                )

        # 2. Check each referenced document file on disk
        for item in data.get("instruction_mapping", []):
            app_src = item.get("approved_source", {})
            rel_path = app_src.get("file_path")
            expected_sha = app_src.get("sha256")
            if not rel_path:
                continue

            full_path = repo_root / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
            if not full_path.exists():
                errors.append(f"Corpus file missing: {rel_path}")
                continue

            actual_sha = hashlib.sha256(full_path.read_bytes()).hexdigest()
            if expected_sha and actual_sha != expected_sha:
                errors.append(f"SHA256 mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}")

        return len(errors) == 0, errors

    def load_frozen_corpus(
        self,
        corpus_dir: str | Path | None = None,
        manifest_path: str | Path | None = None,
        verify_integrity: bool = True,
    ) -> int:
        """Loads, verifies, and indexes the 5 frozen operational regulations cataloged in rag_corpus_manifest.json."""
        repo_root = Path(__file__).resolve().parents[3]

        if manifest_path is None:
            manifest_path = repo_root / "data" / "manifests" / "rag_corpus_manifest.json"
        else:
            manifest_path = Path(manifest_path)

        if not manifest_path.exists():
            raise FileNotFoundError(f"RAG corpus manifest not found at: {manifest_path}")

        if verify_integrity:
            is_valid, errors = self.verify_manifest_integrity(manifest_path)
            if not is_valid:
                raise ValueError(f"Corpus manifest integrity check failed: {'; '.join(errors)}")

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
            content = file_path.read_text(encoding="utf-8")
            expected_sha = app_src.get("sha256")

            override_meta = {
                "document_id": app_src.get("document_id"),
                "title": app_src.get("title"),
                "source_revision": app_src.get("source_revision"),
                "site_acl": item.get("site_acl", []),
                "role_acl": item.get("role_acl", ["chief_engineer", "executor"]),
                "equipment_class": item.get("equipment_class"),
                "expected_sha256": expected_sha,
            }

            metadata, chunks = DocumentExtractor.extract_from_markdown(
                content=content,
                file_path=file_path,
                default_equipment_class=item.get("equipment_class"),
                override_metadata=override_meta,
            )

            self.index.add_document(metadata, chunks)
            indexed_count += 1

        logger.info("Successfully loaded %d verified frozen regulations into RAGIndex", indexed_count)
        return indexed_count

    def rebuild_from_storage(
        self,
        session: Any = None,
        corpus_dir: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> int:
        """Rebuilds RAG index from verified manifest and published PostgreSQL outbox events upon restart."""
        # Reset current index and consumer state
        self.index = RAGIndex()
        self.consumer.index = self.index
        self.consumer.processed_event_ids.clear()
        self.consumer.stream_revisions.clear()
        count = self.load_frozen_corpus(corpus_dir=corpus_dir, manifest_path=manifest_path, verify_integrity=True)

        if session is not None:
            from sqlalchemy import text
            published_events = session.execute(text("""
                SELECT event_id, site_id, scope, source_revision, source_sha256,
                       entity_type, entity_id, change_type, payload, status
                FROM source_revision_events
                WHERE status = 'published'
                ORDER BY source_revision, event_id
            """)).mappings().all()

            for row in published_events:
                self.consumer.process_single_db_event(session, row["event_id"], update_status=False, is_rebuild=True)

        self.rebuilt_from_storage = True
        return count

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
                user_role=user_role,
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
        document_id: str | None = None,
    ) -> tuple[DocumentMetadata, list[Chunk]]:
        """Extracts and indexes tabular Excel catalog rows for an operational site."""
        metadata, chunks = DocumentExtractor.extract_from_catalog_rows(
            rows=rows,
            site_id=site_id,
            source_revision=source_revision,
            catalog_sha256=catalog_sha256,
            document_id=document_id,
        )
        self.index.add_document(metadata, chunks)
        return metadata, chunks


def get_rag_service(session: Any = None) -> RAGService:
    """Returns singleton instance of RAGService initialized with frozen corpus and automatic database rebuild."""
    global _GLOBAL_RAG_SERVICE
    if _GLOBAL_RAG_SERVICE is None:
        _GLOBAL_RAG_SERVICE = RAGService.create_with_frozen_corpus()
        if session is not None:
            try:
                _GLOBAL_RAG_SERVICE.rebuild_from_storage(session=session)
            except Exception as exc:
                logger.warning("Failed to auto-rebuild RAG from provided session: %s", exc)
        else:
            try:
                from backend.app.db.session import make_session_factory, make_engine
                engine = make_engine()
                factory = make_session_factory(engine)
                with factory() as s:
                    _GLOBAL_RAG_SERVICE.rebuild_from_storage(session=s)
            except Exception:
                pass
    elif session is not None and not _GLOBAL_RAG_SERVICE.rebuilt_from_storage:
        try:
            _GLOBAL_RAG_SERVICE.rebuild_from_storage(session=session)
        except Exception as exc:
            logger.warning("Failed to auto-rebuild RAG from session: %s", exc)
    return _GLOBAL_RAG_SERVICE


def reset_rag_service() -> None:
    """Resets global singleton instance of RAGService."""
    global _GLOBAL_RAG_SERVICE
    _GLOBAL_RAG_SERVICE = None
