BEGIN;

-- Preserve legacy role values and accept canonical API roles for new accounts.
ALTER TABLE site_memberships DROP CONSTRAINT site_memberships_role_check;
ALTER TABLE site_memberships ADD CONSTRAINT site_memberships_role_check
    CHECK (role IN ('executive','chief_engineer','engineer','technician','admin','dispatcher','executor'));
CREATE UNIQUE INDEX users_email_casefold ON users (lower(email));
CREATE TABLE fixrate_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    csrf_hash CHAR(64) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX fixrate_sessions_expiry ON fixrate_sessions(expires_at);
ALTER TABLE equipment ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0);
ALTER TABLE work_orders ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0);
-- Freeze the checklist definition with each attempt, independently of future rules.
ALTER TABLE work_reports ADD COLUMN checklist_snapshot JSONB NOT NULL DEFAULT '[]'
    CHECK (jsonb_typeof(checklist_snapshot) = 'array');
ALTER TABLE evidence_files ADD COLUMN checklist_item_id UUID,
    ADD COLUMN view_key TEXT,
    ADD COLUMN equipment_id UUID,
    ADD FOREIGN KEY (site_id,equipment_id) REFERENCES equipment(site_id,equipment_id);
ALTER TABLE acceptance_reviews ADD COLUMN decision_context JSONB NOT NULL DEFAULT '{}'
    CHECK (jsonb_typeof(decision_context) = 'object');

COMMIT;
