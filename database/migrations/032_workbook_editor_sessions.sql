BEGIN;

CREATE TABLE source_workbook_editor_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL,
    book_id UUID NOT NULL,
    base_version INTEGER NOT NULL,
    user_id UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL DEFAULT 'editing' CHECK (state IN ('editing','pending','ready','unchanged','failed','saved')),
    snapshot_request_id UUID,
    snapshot_requested_at TIMESTAMPTZ,
    snapshot_sha256 CHAR(64) CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    snapshot BYTEA CHECK (octet_length(snapshot) BETWEEN 1 AND 5242880),
    commit_key UUID,
    committed_version INTEGER,
    CHECK ((snapshot IS NULL) = (snapshot_sha256 IS NULL)),
    CHECK ((commit_key IS NULL) = (committed_version IS NULL)),
    FOREIGN KEY (site_id, book_id, base_version)
        REFERENCES source_workbook_versions(site_id, book_id, version) ON DELETE CASCADE,
    FOREIGN KEY (site_id, book_id, committed_version)
        REFERENCES source_workbook_versions(site_id, book_id, version)
);
CREATE INDEX source_workbook_editor_sessions_book
    ON source_workbook_editor_sessions (site_id, book_id, expires_at DESC);

COMMIT;
