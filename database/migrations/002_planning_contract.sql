BEGIN;

-- Stable identity for a rule-to-equipment binding, retained across changes.
ALTER TABLE rule_equipment
    ADD COLUMN binding_id UUID NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    ADD COLUMN baseline_runtime_hours NUMERIC(18,6) CHECK (baseline_runtime_hours >= 0),
    ADD UNIQUE (binding_id),
    ADD UNIQUE (site_id, system_id, maintenance_rule_id, binding_id);

ALTER TABLE schedule_entries
    ADD COLUMN binding_id UUID,
    ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    ADD COLUMN earliest_date DATE,
    ADD COLUMN runtime_due_at_hours NUMERIC(18,6) CHECK (runtime_due_at_hours >= 0),
    ADD CHECK (earliest_date IS NULL OR earliest_date <= planned_date),
    ADD FOREIGN KEY (site_id, system_id, maintenance_rule_id, binding_id)
        REFERENCES rule_equipment (site_id, system_id, maintenance_rule_id, binding_id);
CREATE UNIQUE INDEX schedule_entries_binding_occurrence
    ON schedule_entries (site_id, schedule_plan_id, binding_id, planned_date, sequence_no)
    WHERE binding_id IS NOT NULL;

-- Preserve the precision and optionality of raw_norm_value; no implicit conversion.
ALTER TABLE maintenance_rules ALTER COLUMN norm_hours TYPE NUMERIC(12,3),
    ALTER COLUMN norm_hours DROP NOT NULL;
ALTER TABLE maintenance_rules ADD COLUMN data_origin TEXT NOT NULL DEFAULT 'customer'
    CHECK (data_origin IN ('customer', 'synthetic_demo'));

-- Record old and new values transactionally for the editable planning entities.
CREATE FUNCTION record_planning_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_data jsonb; new_data jsonb; record_data jsonb;
BEGIN
    IF TG_OP <> 'INSERT' THEN old_data := to_jsonb(OLD); END IF;
    IF TG_OP <> 'DELETE' THEN new_data := to_jsonb(NEW); END IF;
    record_data := COALESCE(new_data, old_data);
    INSERT INTO audit_events(site_id, actor_type, entity_type, entity_id, action, before_snapshot, after_snapshot)
    VALUES ((record_data->>'site_id')::uuid, 'system', TG_TABLE_NAME,
            (record_data->>TG_ARGV[0])::uuid, lower(TG_OP), old_data, new_data);
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER audit_operation_templates AFTER INSERT OR UPDATE OR DELETE ON operation_templates
    FOR EACH ROW EXECUTE FUNCTION record_planning_change('operation_template_id');
CREATE TRIGGER audit_maintenance_rules AFTER INSERT OR UPDATE OR DELETE ON maintenance_rules
    FOR EACH ROW EXECUTE FUNCTION record_planning_change('maintenance_rule_id');
CREATE TRIGGER audit_rule_equipment AFTER INSERT OR UPDATE OR DELETE ON rule_equipment
    FOR EACH ROW EXECUTE FUNCTION record_planning_change('binding_id');
CREATE TRIGGER audit_schedule_plans AFTER INSERT OR UPDATE OR DELETE ON schedule_plans
    FOR EACH ROW EXECUTE FUNCTION record_planning_change('schedule_plan_id');
CREATE TRIGGER audit_schedule_entries AFTER INSERT OR UPDATE OR DELETE ON schedule_entries
    FOR EACH ROW EXECUTE FUNCTION record_planning_change('schedule_entry_id');
COMMIT;
