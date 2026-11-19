BEGIN;

CREATE TABLE source_imports (
    source_import_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(site_id) ON DELETE RESTRICT,
    source_sha256 CHAR(64) NOT NULL,
    source_name TEXT NOT NULL,
    source_revision INTEGER NOT NULL CHECK (source_revision > 0),
    status TEXT NOT NULL CHECK (status IN ('imported','failed')),
    row_count INTEGER NOT NULL CHECK (row_count > 0),
    source_rows JSONB NOT NULL CHECK (jsonb_typeof(source_rows) = 'object'),
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, source_sha256),
    FOREIGN KEY (site_id, created_by) REFERENCES site_memberships(site_id, user_id)
);

CREATE INDEX source_imports_site_revision ON source_imports(site_id, source_revision);

COMMIT;
