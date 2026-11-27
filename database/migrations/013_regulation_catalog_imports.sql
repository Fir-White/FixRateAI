-- Immutable source drafts: never create equipment, maintenance rules or assignments.
BEGIN;
CREATE TABLE regulation_catalog_imports (
    import_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(site_id),
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    filename TEXT NOT NULL CHECK (length(filename) BETWEEN 1 AND 256),
    source_sha256 CHAR(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    parser_version TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind='hvac_january_catalog'),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status='draft'),
    source_file BYTEA NOT NULL CHECK (octet_length(source_file) BETWEEN 1 AND 5242880),
    summary JSONB NOT NULL CHECK (jsonb_typeof(summary)='object'),
    catalog_data JSONB NOT NULL CHECK (jsonb_typeof(catalog_data)='object'),
    UNIQUE (site_id,source_sha256,parser_version),
    UNIQUE (site_id,import_id)
);
CREATE INDEX regulation_catalog_imports_site_created ON regulation_catalog_imports(site_id,created_at DESC,import_id);
COMMIT;
