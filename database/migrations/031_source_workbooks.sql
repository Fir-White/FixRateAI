BEGIN;

CREATE TABLE source_workbooks (
    book_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(site_id),
    filename TEXT NOT NULL CHECK (length(filename) BETWEEN 1 AND 256),
    original_sha256 CHAR(64) NOT NULL CHECK (original_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, book_id),
    UNIQUE (site_id, original_sha256)
);
CREATE INDEX source_workbooks_site_created ON source_workbooks (site_id, created_at DESC, book_id);

CREATE TABLE source_workbook_versions (
    site_id UUID NOT NULL,
    book_id UUID NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    content BYTEA NOT NULL,
    size_bytes INTEGER GENERATED ALWAYS AS (octet_length(content)) STORED
        CHECK (size_bytes BETWEEN 1 AND 5242880),
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, book_id, version),
    FOREIGN KEY (site_id, book_id) REFERENCES source_workbooks(site_id, book_id) ON DELETE CASCADE
);

COMMIT;
