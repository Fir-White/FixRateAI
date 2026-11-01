BEGIN;
ALTER TABLE schedule_entries ADD COLUMN source_occurrence_id UUID;
CREATE UNIQUE INDEX schedule_entries_source_occurrence ON schedule_entries(site_id,source_occurrence_id)
    WHERE source_occurrence_id IS NOT NULL;

CREATE TABLE planning_runs (
    planning_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(site_id),
    idempotency_key UUID NOT NULL,
    request_sha256 CHAR(64) NOT NULL,
    period_year INTEGER NOT NULL CHECK (period_year BETWEEN 2000 AND 2100),
    period_month SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    created_by UUID NOT NULL,
    response_snapshot JSONB NOT NULL CHECK (jsonb_typeof(response_snapshot)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(site_id,idempotency_key),
    FOREIGN KEY(site_id,created_by) REFERENCES site_memberships(site_id,user_id)
);
COMMIT;
