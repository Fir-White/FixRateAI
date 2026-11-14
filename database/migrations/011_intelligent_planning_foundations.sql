-- Equal local start/end times now mean a shift ending on the next date.
-- Existing unequal times retain their meaning; no history is rewritten.
DO $$
DECLARE constraint_name text;
BEGIN
    FOR constraint_name IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'employee_shift_rules'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%starts_local <> ends_local%'
    LOOP
        EXECUTE format('ALTER TABLE employee_shift_rules DROP CONSTRAINT %I', constraint_name);
    END LOOP;
END $$;

-- PostgreSQL accepts 24:00; Python's local-time contract accepts 00:00..23:59.
ALTER TABLE employee_shift_rules ADD CONSTRAINT employee_shift_rules_local_clock
    CHECK (starts_local < TIME '24:00' AND ends_local < TIME '24:00');

INSERT INTO maintenance_types (code, name)
VALUES ('TO3', 'ТО3') ON CONFLICT (code) DO NOTHING;
