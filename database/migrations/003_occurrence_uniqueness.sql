BEGIN;
-- A rule can apply to several assets on the same day. Keep one aggregate
-- occurrence when no binding is supplied and one occurrence per binding.
DO $$
DECLARE name_of_constraint text;
BEGIN
 SELECT c.conname INTO STRICT name_of_constraint
 FROM pg_constraint c
 WHERE c.conrelid = 'schedule_entries'::regclass AND c.contype = 'u'
   AND (SELECT array_agg(a.attname::text ORDER BY k.ord)
        FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum)
       = ARRAY['site_id','schedule_plan_id','maintenance_rule_id','planned_date','sequence_no'];
 EXECUTE format('ALTER TABLE schedule_entries DROP CONSTRAINT %I', name_of_constraint);
END $$;
CREATE UNIQUE INDEX schedule_entries_unbound_occurrence
 ON schedule_entries(site_id, schedule_plan_id, maintenance_rule_id, planned_date, sequence_no)
 WHERE binding_id IS NULL;
COMMIT;
