BEGIN;

CREATE TABLE work_consumptions (
    consumption_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    work_report_id UUID NOT NULL,
    equipment_id UUID,
    material_name TEXT NOT NULL
        CHECK (length(btrim(material_name)) BETWEEN 1 AND 256),
    quantity NUMERIC(18,3) NOT NULL CHECK (quantity > 0),
    unit TEXT NOT NULL CHECK (length(btrim(unit)) BETWEEN 1 AND 64),
    recorded_by UUID NOT NULL,
    task_revision INTEGER NOT NULL CHECK (task_revision > 0),
    idempotency_key UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','void')),
    supersedes_consumption_id UUID,
    superseded_by_consumption_id UUID,
    correction_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, work_order_id, work_report_id, idempotency_key),
    UNIQUE (site_id, consumption_id),
    FOREIGN KEY (site_id,work_order_id) REFERENCES work_orders(site_id,work_order_id) ON DELETE RESTRICT,
    FOREIGN KEY (site_id,work_order_id,work_report_id)
        REFERENCES work_reports(site_id,work_order_id,work_report_id) ON DELETE RESTRICT,
    FOREIGN KEY (site_id,equipment_id) REFERENCES equipment(site_id,equipment_id) ON DELETE RESTRICT,
    FOREIGN KEY (site_id,recorded_by) REFERENCES site_memberships(site_id,user_id) ON DELETE RESTRICT,
    CHECK (status='active' OR superseded_by_consumption_id IS NOT NULL),
    CHECK (status='void' OR superseded_by_consumption_id IS NULL),
    CHECK (supersedes_consumption_id IS NULL OR (status='active' AND correction_reason IS NOT NULL))
);

CREATE INDEX work_consumptions_attempt
    ON work_consumptions(site_id,work_order_id,work_report_id,created_at DESC);

ALTER TABLE equipment_components
    ADD COLUMN IF NOT EXISTS replaced_by_component_id UUID,
    ADD COLUMN IF NOT EXISTS replacement_source_component_id UUID,
    ADD COLUMN IF NOT EXISTS replacement_work_order_id UUID,
    ADD COLUMN IF NOT EXISTS replacement_work_report_id UUID,
    ADD COLUMN IF NOT EXISTS replacement_reason TEXT;

COMMIT;
