"""Durable outbox consumer for source_revision_events table with transaction savepoints and SHA validation."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from .extractor import DocumentExtractor
from .index import RAGIndex
from .schemas import IndexSyncReport, OutboxEvent

logger = logging.getLogger("fixrate.rag.consumer")


class DurableOutboxConsumer:
    """Consumes and indexes source revision events with strict idempotency, gap detection, and nested savepoints."""

    def __init__(self, index: RAGIndex) -> None:
        self.index = index
        self.processed_event_ids: set[str] = set()
        # Track known revisions per stream: (site_id, scope, entity_id/entity_type) -> int
        self.stream_revisions: dict[str, int] = {}

    def _stream_key(self, event: OutboxEvent) -> str:
        ent = str(event.entity_id) if event.entity_id else event.entity_type
        return f"{event.site_id}:{event.scope}:{ent}"

    def process_single_event(self, event: OutboxEvent) -> bool:
        """Processes a single outbox event, verifying SHA integrity, updating index, and tracking streams."""
        evt_id = str(event.event_id)
        if evt_id in self.processed_event_ids:
            logger.debug("Event %s already processed; skipping (idempotent)", evt_id)
            return True

        stream_key = self._stream_key(event)
        last_rev = self.stream_revisions.get(stream_key, 0)
        gap = False
        if last_rev > 0 and event.source_revision > last_rev + 1:
            logger.warning(
                "Gap detected on stream %s: received revision %d, expected %d",
                stream_key,
                event.source_revision,
                last_rev + 1,
            )
            gap = True

        self.stream_revisions[stream_key] = max(last_rev, event.source_revision)

        payload = event.payload or {}
        change_type = event.change_type

        # Verify SHA-256 if provided
        if event.source_sha256:
            content_to_check = payload.get("markdown_text") or payload.get("content")
            if content_to_check:
                actual_sha = hashlib.sha256(content_to_check.encode("utf-8")).hexdigest()
                if actual_sha != event.source_sha256:
                    raise ValueError(
                        f"Event {evt_id} SHA256 mismatch: expected {event.source_sha256}, got {actual_sha}"
                    )

        if change_type in ("created", "updated", "source_revision", "text_change"):
            # 1. Markdown document ingestion
            if "markdown_text" in payload or "content" in payload:
                text_content = payload.get("markdown_text") or payload.get("content", "")
                override_meta = {
                    "document_id": payload.get("document_id") or (str(event.entity_id) if event.entity_id else f"doc-{event.scope}"),
                    "title": payload.get("title") or f"Документ {event.scope}",
                    "source_revision": f"rev-{event.source_revision}",
                    "site_acl": [str(event.site_id)] if event.site_id else [],
                    "role_acl": payload.get("role_acl", ["chief_engineer", "executor"]),
                    "equipment_class": payload.get("equipment_class"),
                    "expected_sha256": event.source_sha256,
                }
                meta, chunks = DocumentExtractor.extract_from_markdown(
                    text_content,
                    file_path=payload.get("file_path"),
                    override_metadata=override_meta,
                )
                self.index.add_document(meta, chunks)

            # 2. File path markdown ingestion
            elif "file_path" in payload:
                fpath = Path(payload["file_path"])
                if fpath.exists():
                    text_content = fpath.read_text(encoding="utf-8")
                    if event.source_sha256:
                        actual_sha = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
                        if actual_sha != event.source_sha256:
                            raise ValueError(
                                f"File {fpath} SHA256 mismatch: expected {event.source_sha256}, got {actual_sha}"
                            )
                    override_meta = {
                        "document_id": payload.get("document_id") or f"doc-{event.scope}",
                        "title": payload.get("title"),
                        "source_revision": f"rev-{event.source_revision}",
                        "site_acl": [str(event.site_id)] if event.site_id else [],
                        "role_acl": payload.get("role_acl", ["chief_engineer", "executor"]),
                        "equipment_class": payload.get("equipment_class"),
                        "expected_sha256": event.source_sha256,
                    }
                    meta, chunks = DocumentExtractor.extract_from_markdown(
                        text_content,
                        file_path=str(fpath),
                        override_metadata=override_meta,
                    )
                    self.index.add_document(meta, chunks)
                else:
                    raise FileNotFoundError(f"Referenced regulation file not found: {fpath}")

            # 3. Tabular Excel catalog ingestion
            elif "rows" in payload:
                rows = payload["rows"]
                meta, chunks = DocumentExtractor.extract_from_catalog_rows(
                    rows,
                    site_id=str(event.site_id),
                    source_revision=event.source_revision,
                    catalog_sha256=event.source_sha256,
                )
                self.index.add_document(meta, chunks)
            else:
                logger.info("Outbox event %s has empty or custom payload", evt_id)

        elif change_type in ("revoked", "deleted"):
            doc_id = payload.get("document_id") or (str(event.entity_id) if event.entity_id else f"doc-{event.scope}")
            reason = payload.get("reason", f"Event {evt_id} marked {change_type}")
            self.index.revoke_document(doc_id, reason=reason)

        self.processed_event_ids.add(evt_id)
        return not gap

    def process_events(self, events: list[OutboxEvent | dict[str, Any]]) -> IndexSyncReport:
        """Processes a sequence of events in-memory or from decoupled event queues."""
        processed_count = 0
        published_count = 0
        failed_count = 0
        gap_detected = False
        details: list[str] = []

        for item in events:
            if isinstance(item, dict):
                try:
                    event = OutboxEvent.model_validate(item)
                except Exception as exc:
                    failed_count += 1
                    details.append(f"Failed to parse event dict: {exc}")
                    continue
            else:
                event = item

            processed_count += 1
            try:
                no_gap = self.process_single_event(event)
                if not no_gap:
                    gap_detected = True
                    details.append(f"Stream gap detected for event {event.event_id}")
                published_count += 1
            except Exception as exc:
                failed_count += 1
                details.append(f"Error processing event {event.event_id}: {exc}")
                logger.exception("Failed to process outbox event %s", event.event_id)

        return IndexSyncReport(
            processed_events=processed_count,
            published_events=published_count,
            failed_events=failed_count,
            gap_detected=gap_detected,
            total_documents=len(self.index.documents),
            total_chunks=len(self.index.chunks),
            details=details,
            synced_at=datetime.now(timezone.utc),
        )

    def process_db_events(
        self, session: Any, site_id: str | UUID | None = None, limit: int = 100
    ) -> IndexSyncReport:
        """Pulls pending events from PostgreSQL source_revision_events table using nested savepoints."""
        from sqlalchemy import text

        query_str = """
            SELECT event_id, site_id, scope, source_revision, source_sha256,
                   entity_type, entity_id, change_type, payload, status, created_at, published_at
            FROM source_revision_events
            WHERE status = 'pending'
        """
        params: dict[str, Any] = {"limit": limit}
        if site_id:
            query_str += " AND site_id = :site"
            params["site"] = str(site_id)

        query_str += " ORDER BY created_at, event_id FOR UPDATE SKIP LOCKED LIMIT :limit"

        rows = session.execute(text(query_str), params).mappings().all()

        processed = 0
        published = 0
        failed = 0
        gap_detected = False
        details: list[str] = []

        for row in rows:
            processed += 1
            row_dict = dict(row)
            try:
                # Nested transaction / savepoint prevents aborting outer transaction on error
                with session.begin_nested():
                    p = row_dict.get("payload")
                    if isinstance(p, str):
                        row_dict["payload"] = json.loads(p)
                    elif p is None:
                        row_dict["payload"] = {}

                    evt = OutboxEvent.model_validate(row_dict)
                    no_gap = self.process_single_event(evt)
                    if not no_gap:
                        gap_detected = True

                    session.execute(
                        text("""
                            UPDATE source_revision_events
                            SET status = 'published', published_at = now()
                            WHERE event_id = :event_id AND status = 'pending'
                        """),
                        {"event_id": evt.event_id},
                    )
                published += 1
            except Exception as exc:
                failed += 1
                details.append(f"DB event {row_dict.get('event_id')} failed: {exc}")
                # Savepoint was rolled back, outer transaction remains valid
                session.execute(
                    text("""
                        UPDATE source_revision_events
                        SET status = 'failed'
                        WHERE event_id = :event_id AND status = 'pending'
                    """),
                    {"event_id": row_dict.get("event_id")},
                )

        if processed > 0:
            session.commit()

        return IndexSyncReport(
            processed_events=processed,
            published_events=published,
            failed_events=failed,
            gap_detected=gap_detected,
            total_documents=len(self.index.documents),
            total_chunks=len(self.index.chunks),
            details=details,
            synced_at=datetime.now(timezone.utc),
        )
