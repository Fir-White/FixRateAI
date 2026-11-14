BEGIN;
-- Decisions overlay immutable source catalogs. Every edit appends a revision;
-- neither source cells nor previously confirmed decisions are rewritten.
CREATE TABLE catalog_operation_decisions (
    decision_id UUID PRIMARY KEY,
    site_id UUID NOT NULL,
    import_id UUID NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number BETWEEN 1 AND 1048576),
    revision INTEGER NOT NULL CHECK (revision > 0),
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed BOOLEAN NOT NULL DEFAULT false,
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 2000),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload)='object'),
    binding_snapshot JSONB NOT NULL CHECK (jsonb_typeof(binding_snapshot)='array'),
    parent_revision INTEGER,
    FOREIGN KEY (site_id,import_id) REFERENCES regulation_catalog_imports(site_id,import_id),
    UNIQUE (site_id,import_id,row_number,revision)
);
CREATE INDEX catalog_decisions_latest ON catalog_operation_decisions(site_id,import_id,row_number,revision DESC);
COMMIT;
