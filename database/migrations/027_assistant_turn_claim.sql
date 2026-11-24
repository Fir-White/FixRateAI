BEGIN;
-- Nullable for turns created by an older application during a rolling upgrade.
ALTER TABLE assistant_turns ADD COLUMN worker_claimed_at timestamptz;
COMMIT;
