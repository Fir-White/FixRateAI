-- BE05: explicit reservation intervals and immutable historical assignments.
BEGIN;

ALTER TABLE work_orders ADD COLUMN planned_end_at TIMESTAMPTZ;
ALTER TABLE work_orders ADD CONSTRAINT work_orders_planned_interval
    CHECK (planned_end_at IS NULL OR (planned_start_at IS NOT NULL AND planned_end_at > planned_start_at));

ALTER TABLE work_assignments
    ADD COLUMN start_at TIMESTAMPTZ,
    ADD COLUMN end_at TIMESTAMPTZ,
    ADD COLUMN qualification_snapshot JSONB,
    ADD COLUMN reason TEXT,
    ADD COLUMN released_at TIMESTAMPTZ;
ALTER TABLE work_assignments ADD CONSTRAINT work_assignments_interval
    CHECK ((start_at IS NULL AND end_at IS NULL) OR (start_at IS NOT NULL AND end_at IS NOT NULL AND end_at > start_at));
ALTER TABLE work_assignments ADD CONSTRAINT work_assignments_qualification_snapshot
    CHECK (qualification_snapshot IS NULL OR jsonb_typeof(qualification_snapshot) = 'array');
-- Closed records retain their ID, interval, principal and qualification facts.
ALTER TABLE work_assignments DROP CONSTRAINT work_assignments_site_id_work_order_id_user_id_key;
CREATE UNIQUE INDEX work_assignments_current_worker
    ON work_assignments(site_id,work_order_id,user_id)
    WHERE status NOT IN ('cancelled','declined');
CREATE INDEX work_assignments_worker_interval ON work_assignments(site_id,user_id,start_at,end_at)
    WHERE status IN ('assigned','active');

COMMIT;
