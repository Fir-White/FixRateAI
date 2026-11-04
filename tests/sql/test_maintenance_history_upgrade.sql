-- Capture before 005 and compare after 008 in the SAME disposable database.
-- psql -v qa03_capture=true captures; the default verifies and removes the snapshot.
\set ON_ERROR_STOP on
\if :{?qa03_capture}
\else
\set qa03_capture false
\endif
BEGIN;
\if :qa03_capture
CREATE SCHEMA qa03_upgrade_check;
CREATE TABLE qa03_upgrade_check.history_snapshot (
    table_name text NOT NULL, row_id text NOT NULL, row_data jsonb NOT NULL,
    PRIMARY KEY(table_name,row_id)
);
DO $$
DECLARE rel text; pk text; amount integer;
BEGIN
    FOREACH rel IN ARRAY ARRAY['forecast_runs','orchestration_decisions','work_orders',
        'work_reports','work_assignments','evidence_files','acceptance_reviews','audit_events'] LOOP
        SELECT a.attname INTO STRICT pk FROM pg_index i
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
        WHERE i.indisprimary AND i.indrelid=('public.' || rel)::regclass;
        EXECUTE format('INSERT INTO qa03_upgrade_check.history_snapshot SELECT %L, %I::text, to_jsonb(t) FROM public.%I t',rel,pk,rel);
        GET DIAGNOSTICS amount = ROW_COUNT;
        IF amount=0 THEN RAISE EXCEPTION 'Upgrade verification requires nonempty history: %',rel; END IF;
        RAISE NOTICE 'Captured % rows from %',amount,rel;
    END LOOP;
END $$;
COMMIT;
\echo 'HISTORY SNAPSHOT CAPTURED'
\else
DO $$
DECLARE old record; pk text; actual jsonb; field record; amount integer := 0;
BEGIN
    IF NOT EXISTS(SELECT 1 FROM qa03_upgrade_check.history_snapshot) THEN
        RAISE EXCEPTION 'Missing nonempty upgrade snapshot';
    END IF;
    FOR old IN SELECT * FROM qa03_upgrade_check.history_snapshot LOOP
        SELECT a.attname INTO STRICT pk FROM pg_index i
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
        WHERE i.indisprimary AND i.indrelid=('public.' || old.table_name)::regclass;
        EXECUTE format('SELECT to_jsonb(t) FROM public.%I t WHERE %I::text=$1',old.table_name,pk)
            INTO actual USING old.row_id;
        IF actual IS NULL THEN RAISE EXCEPTION 'Upgrade lost history %.%',old.table_name,old.row_id; END IF;
        FOR field IN SELECT * FROM jsonb_each(old.row_data) LOOP
            IF actual->field.key IS DISTINCT FROM field.value THEN
                RAISE EXCEPTION 'Upgrade rewrote history %.% column %',old.table_name,old.row_id,field.key;
            END IF;
        END LOOP;
        amount := amount+1;
    END LOOP;
    RAISE NOTICE 'Preserved all original fields in % historical rows',amount;
END $$;
DROP TABLE qa03_upgrade_check.history_snapshot;
DROP SCHEMA qa03_upgrade_check;
COMMIT;
\echo 'ALL UPGRADE HISTORY CHECKS PASSED'
\endif
