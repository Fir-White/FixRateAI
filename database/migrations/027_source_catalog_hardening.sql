BEGIN;

ALTER TABLE source_imports
    ADD COLUMN IF NOT EXISTS system_id UUID,
    ADD COLUMN IF NOT EXISTS effective_from DATE,
    ADD COLUMN IF NOT EXISTS source_workbook BYTEA,
    ADD COLUMN IF NOT EXISTS catalog_revision INTEGER;

CREATE TABLE IF NOT EXISTS catalog_revisions (
    site_id UUID NOT NULL REFERENCES sites(site_id) ON DELETE RESTRICT,
    catalog_revision INTEGER NOT NULL CHECK (catalog_revision > 0),
    source_sha256 CHAR(64),
    change_type TEXT NOT NULL,
    PRIMARY KEY (site_id, catalog_revision)
);

CREATE TABLE IF NOT EXISTS source_catalog_index (
    site_id UUID NOT NULL REFERENCES sites(site_id) ON DELETE RESTRICT,
    source_revision INTEGER NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    source_ref TEXT NOT NULL,
    search_text TEXT NOT NULL,
    search_vector TSVECTOR NOT NULL,
    PRIMARY KEY (site_id, source_sha256, source_ref)
);

CREATE INDEX IF NOT EXISTS source_catalog_index_vector
    ON source_catalog_index USING GIN (search_vector);

COMMIT;
