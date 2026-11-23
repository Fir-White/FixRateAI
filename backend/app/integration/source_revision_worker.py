"""Durable source-catalog outbox processor."""
from __future__ import annotations

from sqlalchemy import text

from .source_import import index_source_rows


def publish_event(session, event):
    status = 'published'
    try:
        with session.begin_nested():
            if event['entity_type'] == 'source_import' and event.get('change_type') not in ('revoked', 'deleted'):
                if not index_source_rows(session, site_id=event['site_id'], source_revision=event['source_revision'],
                                         source_sha256=event['source_sha256']):
                    raise ValueError('Missing source rows for revision')
            try:
                from ml_service.app.rag import get_rag_service
                get_rag_service().consumer.process_single_db_event(session, event['event_id'], update_status=False)
            except Exception:
                raise
    except Exception:
        status = 'failed'
    return session.execute(text("""
        UPDATE source_revision_events
        SET status=:status,published_at=CASE WHEN :status='published' THEN CURRENT_TIMESTAMP END
        WHERE site_id=:site AND event_id=:event AND status='pending'
        RETURNING event_id,status,published_at
    """), {'status': status, 'site': event['site_id'], 'event': event['event_id']}).mappings().one()


def process_pending_revisions(app) -> int:
    with app.state.factory() as session:
        events = session.execute(text("""
            SELECT event_id,site_id,source_sha256,source_revision,entity_type,change_type
            FROM source_revision_events
            WHERE status='pending' AND entity_type='source_import'
            ORDER BY created_at,event_id
            FOR UPDATE SKIP LOCKED
            LIMIT 100
        """)).mappings().all()
        processed = sum(publish_event(session, event)['status'] == 'published' for event in events)
        session.commit()
    return processed
