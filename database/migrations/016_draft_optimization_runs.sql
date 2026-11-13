BEGIN;
CREATE TABLE draft_optimization_runs (
    run_id UUID PRIMARY KEY,
    site_id UUID NOT NULL,
    draft_id UUID NOT NULL,
    base_revision INTEGER NOT NULL CHECK (base_revision>0),
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','running','cancel_requested','cancelled','succeeded','failed')),
    options JSONB NOT NULL CHECK (jsonb_typeof(options)='object'),
    input_snapshot JSONB NOT NULL CHECK (jsonb_typeof(input_snapshot)='object'),
    input_sha256 CHAR(64) NOT NULL,
    request_sha256 CHAR(64) NOT NULL,
    idempotency_key UUID NOT NULL,
    lease_token UUID,
    result JSONB,
    baseline_segments JSONB,
    optimized_segments JSONB,
    error_code TEXT,
    applied_revision INTEGER,
    applied_kind TEXT CHECK (applied_kind IN ('baseline','optimized')),
    UNIQUE(site_id,idempotency_key),
    FOREIGN KEY(site_id,draft_id,base_revision) REFERENCES planning_draft_versions(site_id,draft_id,revision),
    FOREIGN KEY(site_id,draft_id,applied_revision) REFERENCES planning_draft_versions(site_id,draft_id,revision),
    CHECK (result IS NULL OR jsonb_typeof(result)='object'),
    CHECK (baseline_segments IS NULL OR jsonb_typeof(baseline_segments)='array'),
    CHECK (optimized_segments IS NULL OR jsonb_typeof(optimized_segments)='array')
);
CREATE INDEX draft_optimization_runs_queue ON draft_optimization_runs(created_at,run_id) WHERE state IN ('queued','running','cancel_requested');
CREATE INDEX draft_optimization_runs_history ON draft_optimization_runs(site_id,draft_id,created_at DESC);
COMMIT;
