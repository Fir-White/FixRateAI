-- Append-only analyst workflow support. No existing reports or files are removed.
ALTER TABLE work_orders ADD COLUMN overdue_since_at timestamptz;
ALTER TABLE work_orders ADD COLUMN exception_context jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(exception_context)='object');
ALTER TABLE work_reports ADD COLUMN execution_context jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(execution_context)='object');
ALTER TABLE work_readings ADD COLUMN phase text NOT NULL DEFAULT 'unspecified' CHECK (phase IN ('before','after','unspecified'));
ALTER TABLE evidence_files ADD COLUMN verification_context jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(verification_context)='object');
CREATE TABLE maintenance_notifications (
 notification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 site_id uuid NOT NULL REFERENCES sites(site_id) ON DELETE RESTRICT,
 user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
 event_key text NOT NULL,
 message text NOT NULL CHECK (length(trim(message))>0),
 work_order_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(),
 read_at timestamptz,
 UNIQUE(site_id,user_id,event_key),
 FOREIGN KEY(site_id,work_order_id) REFERENCES work_orders(site_id,work_order_id) ON DELETE RESTRICT
);
CREATE INDEX maintenance_notifications_inbox ON maintenance_notifications(site_id,user_id,created_at DESC);

-- Several source obligations may move to the same effective date.
ALTER TABLE schedule_entries ADD COLUMN source_date date;
CREATE UNIQUE INDEX schedule_entries_binding_source_date ON schedule_entries(site_id,binding_id,source_date)
 WHERE binding_id IS NOT NULL AND source_date IS NOT NULL;
