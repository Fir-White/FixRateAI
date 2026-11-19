"""Durable source-catalog outbox processor."""
from __future__ import annotations

from sqlalchemy import text


def process_pending_revisions(app) -> int:
    processed = 0
    with app.state.factory() as session:
        events = session.execute(text("""
            SELECT event_id,site_id,source_sha256,source_revision
            FROM source_revision_events
            WHERE status='pending'
            ORDER BY created_at,event_id
            FOR UPDATE SKIP LOCKED
            LIMIT 100
        """)).mappings().all()
        for event in events:
            try:
                source = session.execute(text("""
                    SELECT source_rows
                    FROM source_imports
                    WHERE site_id=:site AND source_sha256=:sha
                """), {
                    "site": event["site_id"],
                    "sha": event["source_sha256"],
                }).mappings().first()
                if source is not None:
                    for row in source["source_rows"]["rows"]:
                        search_text = " ".join(str(value) for value in (
                            row.get("code", ""),
                            row.get("title", ""),
                            row.get("maintenanceType", ""),
                            row.get("frequency", ""),
                            row.get("normHours", ""),
                        ))
                        session.execute(text("""
                            INSERT INTO source_catalog_index
                                (site_id,source_revision,source_sha256,source_ref,
                                 search_text,search_vector)
                            VALUES (:site,:revision,:sha,:ref,:text,
                                    to_tsvector('russian',:text))
                            ON CONFLICT (site_id,source_sha256,source_ref)
                            DO UPDATE SET
                                source_revision=EXCLUDED.source_revision,
                                search_text=EXCLUDED.search_text,
                                search_vector=EXCLUDED.search_vector
                        """), {
                            "site": event["site_id"],
                            "revision": event["source_revision"],
                            "sha": event["source_sha256"],
                            "ref": row["sourceRef"],
                            "text": search_text,
                        })
                session.execute(text("""
                    UPDATE source_revision_events
                    SET status='published',published_at=now()
                    WHERE event_id=:event
                """), {"event": event["event_id"]})
                session.commit()
                processed += 1
            except Exception:
                session.rollback()
                session.execute(text("""
                    UPDATE source_revision_events
                    SET status='failed'
                    WHERE event_id=:event
                """), {"event": event["event_id"]})
                session.commit()
    return processed
