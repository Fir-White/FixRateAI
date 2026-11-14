BEGIN;
-- Existing schedule_plans/entries refer to active monthly rules/tasks. These
-- independent immutable scenarios can precede active rules and span a year.
CREATE TABLE planning_draft_versions (
    version_id UUID PRIMARY KEY,
    draft_id UUID NOT NULL,
    site_id UUID NOT NULL REFERENCES sites(site_id),
    import_id UUID NOT NULL,
    revision INTEGER NOT NULL CHECK (revision>0),
    parent_revision INTEGER,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 256),
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 2000),
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    input_sha256 CHAR(64) NOT NULL,
    source_snapshot JSONB NOT NULL CHECK (jsonb_typeof(source_snapshot)='object'),
    resource_snapshot JSONB NOT NULL CHECK (jsonb_typeof(resource_snapshot)='object'),
    occurrences JSONB NOT NULL CHECK (jsonb_typeof(occurrences)='array'),
    segments JSONB NOT NULL CHECK (jsonb_typeof(segments)='array'),
    validation_snapshot JSONB NOT NULL CHECK (jsonb_typeof(validation_snapshot)='object'),
    summary JSONB NOT NULL CHECK (jsonb_typeof(summary)='object'),
    month_summary JSONB NOT NULL CHECK (jsonb_typeof(month_summary)='array'),
    idempotency_key UUID,
    request_sha256 CHAR(64),
    CHECK (starts_on BETWEEN DATE '2000-01-01' AND DATE '2200-12-31' AND ends_on>=starts_on AND ends_on-starts_on<=365),
    CHECK ((revision=1 AND parent_revision IS NULL) OR (revision>1 AND parent_revision IS NOT NULL AND parent_revision=revision-1)),
    UNIQUE (site_id,draft_id,revision),
    UNIQUE (site_id,idempotency_key),
    FOREIGN KEY (site_id,import_id) REFERENCES regulation_catalog_imports(site_id,import_id),
    FOREIGN KEY (site_id,draft_id,parent_revision) REFERENCES planning_draft_versions(site_id,draft_id,revision)
);
CREATE INDEX planning_draft_versions_catalog ON planning_draft_versions(site_id,import_id,created_at DESC);
COMMIT;
