BEGIN;

CREATE TABLE IF NOT EXISTS source_revision_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(site_id) ON DELETE RESTRICT,
    scope TEXT NOT NULL CHECK (length(scope) BETWEEN 1 AND 128),
    source_revision INTEGER NOT NULL CHECK (source_revision > 0),
    source_sha256 CHAR(64),
    entity_type TEXT NOT NULL,
    entity_id UUID,
    change_type TEXT NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','published','failed')),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, scope, source_revision, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS source_revision_events_pending
    ON source_revision_events(site_id, status, created_at);

COMMIT;
