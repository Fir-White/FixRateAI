-- Additive TL03 subset. Existing invalid rows are retained and must be reviewed
-- before the FK is validated. New/updated rows are checked immediately.
BEGIN;

-- Keep the full NUMERIC(12,2) range while allowing three fractional digits.
ALTER TABLE work_orders
    ALTER COLUMN norm_hours_snapshot TYPE NUMERIC(13,3);

ALTER TABLE schedule_entries
    ADD CONSTRAINT uq_schedule_entries_order_rule
    UNIQUE (site_id, system_id, schedule_entry_id, maintenance_rule_id);

ALTER TABLE work_orders
    ADD CONSTRAINT fk_work_orders_entry_rule
    FOREIGN KEY (site_id, system_id, schedule_entry_id, maintenance_rule_id)
    REFERENCES schedule_entries (site_id, system_id, schedule_entry_id, maintenance_rule_id)
    ON DELETE RESTRICT NOT VALID;

COMMIT;
