-- TL02 catalog 0.9; applied once to an empty database.

BEGIN;

CREATE TABLE sites (
    site_id UUID DEFAULT gen_random_uuid() NOT NULL,
    name TEXT NOT NULL,
    address TEXT,
    timezone TEXT DEFAULT 'Asia/Yekaterinburg' NOT NULL,
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (site_id),
    CHECK (length(trim(name)) > 0),
    CHECK (length(trim(timezone)) > 0)
);

CREATE TABLE users (
    user_id UUID DEFAULT gen_random_uuid() NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT,
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (user_id),
    CHECK (length(trim(full_name)) > 0),
    CHECK (position('@' in email) > 1)
);

CREATE TABLE site_memberships (
    site_id UUID NOT NULL,
    user_id UUID NOT NULL,
    role TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (site_id, user_id),
    CHECK (role IN ('executive','chief_engineer','engineer','technician'))
);

CREATE TABLE engineering_systems (
    system_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    notes TEXT,
    is_active BOOLEAN DEFAULT true NOT NULL,
    PRIMARY KEY (system_id),
    UNIQUE (site_id,system_id),
    UNIQUE (site_id,code),
    CHECK (length(trim(name)) > 0)
);

CREATE TABLE equipment_types (
    equipment_type_id UUID DEFAULT gen_random_uuid() NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    default_attributes JSONB DEFAULT '{}' NOT NULL,
    PRIMARY KEY (equipment_type_id),
    UNIQUE (code),
    CHECK (jsonb_typeof(default_attributes) = 'object')
);

CREATE TABLE equipment (
    equipment_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    parent_equipment_id UUID,
    equipment_type_id UUID,
    asset_code TEXT NOT NULL,
    name TEXT NOT NULL,
    serial_number TEXT,
    commissioned_on DATE,
    location TEXT,
    properties JSONB DEFAULT '{}' NOT NULL,
    status TEXT DEFAULT 'active' NOT NULL,
    PRIMARY KEY (equipment_id),
    UNIQUE (site_id,equipment_id),
    UNIQUE (site_id,system_id,equipment_id),
    UNIQUE (site_id,asset_code),
    CHECK (status IN ('active','under_repair','retired')),
    CHECK (jsonb_typeof(properties) = 'object'),
    CHECK (parent_equipment_id IS DISTINCT FROM equipment_id)
);

CREATE TABLE skills (
    skill_id UUID DEFAULT gen_random_uuid() NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    validity_required BOOLEAN DEFAULT false NOT NULL,
    PRIMARY KEY (skill_id),
    UNIQUE (code)
);

CREATE TABLE user_skills (
    site_id UUID NOT NULL,
    user_id UUID NOT NULL,
    skill_id UUID NOT NULL,
    verified_at TIMESTAMPTZ,
    valid_until DATE,
    PRIMARY KEY (site_id, user_id, skill_id),
    CHECK (valid_until IS NULL OR verified_at IS NOT NULL)
);

CREATE TABLE availability_slots (
    availability_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    user_id UUID NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'available' NOT NULL,
    reason TEXT,
    PRIMARY KEY (availability_id),
    CHECK (ends_at > starts_at),
    CHECK (status IN ('available','unavailable'))
);

CREATE TABLE crews (
    crew_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true NOT NULL,
    PRIMARY KEY (crew_id),
    UNIQUE (site_id,crew_id),
    UNIQUE (site_id,name)
);

CREATE TABLE crew_members (
    crew_member_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    crew_id UUID NOT NULL,
    user_id UUID NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    PRIMARY KEY (crew_member_id),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE maintenance_types (
    maintenance_type_id UUID DEFAULT gen_random_uuid() NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    PRIMARY KEY (maintenance_type_id),
    UNIQUE (code)
);

CREATE TABLE operation_templates (
    operation_template_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    maintenance_type_id UUID NOT NULL,
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (operation_template_id),
    UNIQUE (site_id,operation_template_id),
    UNIQUE (site_id,system_id,operation_template_id),
    UNIQUE (site_id,system_id,code),
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(title)) > 0)
);

CREATE TABLE regulation_documents (
    regulation_document_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    title TEXT NOT NULL,
    source_kind TEXT DEFAULT 'customer' NOT NULL,
    source_uri TEXT,
    external_reference TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (regulation_document_id),
    UNIQUE (site_id,regulation_document_id),
    CHECK (source_kind IN ('customer','manufacturer','internal','demo'))
);

CREATE TABLE regulation_editions (
    regulation_edition_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    regulation_document_id UUID NOT NULL,
    edition_code TEXT NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_sha256 CHAR(64),
    is_approved BOOLEAN DEFAULT false NOT NULL,
    approved_by UUID,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (regulation_edition_id),
    UNIQUE (site_id,regulation_edition_id),
    UNIQUE (site_id,regulation_document_id,edition_code),
    CHECK (effective_to IS NULL OR effective_to >= effective_from),
    CHECK (source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE maintenance_rules (
    maintenance_rule_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    operation_template_id UUID NOT NULL,
    regulation_edition_id UUID NOT NULL,
    supersedes_rule_id UUID,
    rule_version INTEGER DEFAULT 1 NOT NULL,
    period_unit TEXT NOT NULL,
    period_count INTEGER DEFAULT 1 NOT NULL,
    occurrences_per_period INTEGER DEFAULT 1 NOT NULL,
    scheduling_mode TEXT NOT NULL,
    source_text TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    schedule_parameters JSONB DEFAULT '{}' NOT NULL,
    required_people SMALLINT NOT NULL,
    norm_hours NUMERIC(12,2) NOT NULL,
    norm_hours_basis TEXT DEFAULT 'unknown' NOT NULL,
    active_from DATE NOT NULL,
    active_until DATE,
    publication_status TEXT DEFAULT 'draft' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (maintenance_rule_id),
    UNIQUE (site_id,maintenance_rule_id),
    UNIQUE (site_id,system_id,maintenance_rule_id),
    UNIQUE (site_id,operation_template_id,rule_version),
    CHECK (rule_version > 0),
    CHECK (period_count > 0),
    CHECK (occurrences_per_period > 0),
    CHECK (required_people BETWEEN 1 AND 100),
    CHECK (norm_hours >= 0),
    CHECK (period_unit IN ('day','month','quarter','year')),
    CHECK (scheduling_mode IN ('fixed_interval','calendar_window','explicit_months')),
    CHECK (norm_hours_basis IN ('total_person_hours','per_person','unknown')),
    CHECK (publication_status IN ('draft','published','archived')),
    CHECK (active_until IS NULL OR active_until >= active_from),
    CHECK (jsonb_typeof(schedule_parameters) = 'object')
);

CREATE TABLE rule_equipment (
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    maintenance_rule_id UUID NOT NULL,
    equipment_id UUID NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    PRIMARY KEY (site_id, maintenance_rule_id, equipment_id, valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE rule_required_skills (
    site_id UUID NOT NULL,
    maintenance_rule_id UUID NOT NULL,
    skill_id UUID NOT NULL,
    minimum_holders SMALLINT DEFAULT 1 NOT NULL,
    PRIMARY KEY (site_id, maintenance_rule_id, skill_id),
    CHECK (minimum_holders > 0)
);

CREATE TABLE schedule_plans (
    schedule_plan_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    period_year INTEGER NOT NULL,
    period_month SMALLINT NOT NULL,
    revision INTEGER DEFAULT 1 NOT NULL,
    status TEXT DEFAULT 'draft' NOT NULL,
    created_by UUID NOT NULL,
    approved_by UUID,
    approved_at TIMESTAMPTZ,
    source_snapshot JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (schedule_plan_id),
    UNIQUE (site_id,schedule_plan_id),
    UNIQUE (site_id,period_year,period_month,revision),
    CHECK (period_year BETWEEN 2000 AND 2200),
    CHECK (period_month BETWEEN 1 AND 12),
    CHECK (revision > 0),
    CHECK (status IN ('draft','approved','superseded')),
    CHECK (jsonb_typeof(source_snapshot) = 'object')
);

CREATE TABLE schedule_entries (
    schedule_entry_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    schedule_plan_id UUID NOT NULL,
    maintenance_rule_id UUID NOT NULL,
    orchestration_decision_id UUID,
    sequence_no SMALLINT DEFAULT 1 NOT NULL,
    planned_date DATE NOT NULL,
    planned_at TIMESTAMPTZ,
    regulatory_deadline_on DATE NOT NULL,
    regulatory_deadline_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'planned' NOT NULL,
    rule_snapshot JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (schedule_entry_id),
    UNIQUE (site_id,schedule_entry_id),
    UNIQUE (site_id,system_id,schedule_entry_id),
    UNIQUE (site_id,schedule_plan_id,maintenance_rule_id,planned_date,sequence_no),
    CHECK (sequence_no > 0),
    CHECK (planned_date <= regulatory_deadline_on),
    CHECK (planned_at IS NULL OR planned_at <= regulatory_deadline_at),
    CHECK (status IN ('planned','cancelled','superseded')),
    CHECK (jsonb_typeof(rule_snapshot) = 'object')
);

CREATE TABLE incident_reports (
    incident_report_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    equipment_id UUID,
    reported_by UUID NOT NULL,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'new' NOT NULL,
    ai_result_snapshot JSONB,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (incident_report_id),
    UNIQUE (site_id,incident_report_id),
    UNIQUE (site_id,system_id,incident_report_id),
    CHECK (length(trim(description)) > 0),
    CHECK (status IN ('new','triaged','closed'))
);

CREATE TABLE work_orders (
    work_order_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    maintenance_rule_id UUID,
    schedule_entry_id UUID,
    incident_report_id UUID,
    origin TEXT DEFAULT 'scheduled' NOT NULL,
    status TEXT DEFAULT 'draft' NOT NULL,
    priority TEXT DEFAULT 'normal' NOT NULL,
    operation_snapshot JSONB DEFAULT '{}' NOT NULL,
    required_people_snapshot SMALLINT NOT NULL,
    norm_hours_snapshot NUMERIC(12,2) NOT NULL,
    norm_hours_basis_snapshot TEXT DEFAULT 'unknown' NOT NULL,
    planned_start_at TIMESTAMPTZ,
    regulatory_deadline_at TIMESTAMPTZ,
    orchestration_decision_id UUID,
    created_by UUID,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (work_order_id),
    UNIQUE (site_id,work_order_id),
    UNIQUE (site_id,system_id,work_order_id),
    UNIQUE (site_id,schedule_entry_id),
    CHECK (origin IN ('scheduled','incident','manual')),
    CHECK (status IN ('draft','clarification','assigned','in_progress','in_review','rework','completed','cancelled')),
    CHECK (priority IN ('normal','high','critical')),
    CHECK (required_people_snapshot > 0),
    CHECK (norm_hours_snapshot >= 0),
    CHECK (orchestration_decision_id IS NULL OR maintenance_rule_id IS NOT NULL),
    CHECK (norm_hours_basis_snapshot IN ('total_person_hours','per_person','unknown')),
    CHECK (jsonb_typeof(operation_snapshot) = 'object'),
    CHECK ((planned_start_at IS NULL OR regulatory_deadline_at IS NULL OR planned_start_at <= regulatory_deadline_at)),
    CHECK ((origin <> 'scheduled' OR (schedule_entry_id IS NOT NULL AND maintenance_rule_id IS NOT NULL))),
    CHECK ((origin <> 'incident' OR incident_report_id IS NOT NULL))
);

CREATE TABLE work_order_equipment (
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    equipment_id UUID NOT NULL,
    asset_snapshot JSONB DEFAULT '{}' NOT NULL,
    PRIMARY KEY (site_id, work_order_id, equipment_id),
    CHECK (jsonb_typeof(asset_snapshot) = 'object')
);

CREATE TABLE work_assignments (
    work_assignment_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    user_id UUID NOT NULL,
    crew_id UUID,
    assigned_by UUID NOT NULL,
    assigned_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    status TEXT DEFAULT 'assigned' NOT NULL,
    actual_person_hours NUMERIC(12,2),
    PRIMARY KEY (work_assignment_id),
    UNIQUE (site_id,work_order_id,user_id),
    CHECK (status IN ('assigned','declined','active','finished','cancelled')),
    CHECK (actual_person_hours IS NULL OR actual_person_hours >= 0)
);

CREATE TABLE checklist_templates (
    checklist_template_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    operation_template_id UUID NOT NULL,
    item_code TEXT NOT NULL,
    template_version INTEGER DEFAULT 1 NOT NULL,
    prompt TEXT NOT NULL,
    input_kind TEXT NOT NULL,
    unit_code TEXT,
    is_required BOOLEAN DEFAULT true NOT NULL,
    position SMALLINT DEFAULT 1 NOT NULL,
    PRIMARY KEY (checklist_template_id),
    UNIQUE (site_id,checklist_template_id),
    UNIQUE (site_id,operation_template_id,item_code,template_version),
    CHECK (template_version > 0),
    CHECK (position > 0),
    CHECK (input_kind IN ('checkbox','number','text','photo'))
);

CREATE TABLE work_reports (
    work_report_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    revision_no INTEGER DEFAULT 1 NOT NULL,
    submitted_by UUID NOT NULL,
    comment TEXT,
    status TEXT DEFAULT 'draft' NOT NULL,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (work_report_id),
    UNIQUE (site_id,work_order_id,work_report_id),
    UNIQUE (site_id,work_order_id,revision_no),
    CHECK (revision_no > 0),
    CHECK (status IN ('draft','submitted','reviewed'))
);

CREATE TABLE checklist_results (
    checklist_result_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    work_report_id UUID NOT NULL,
    checklist_template_id UUID,
    question_snapshot TEXT NOT NULL,
    response_value JSONB DEFAULT '{}' NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (checklist_result_id),
    UNIQUE (work_report_id,checklist_template_id),
    CHECK (jsonb_typeof(response_value) = 'object')
);

CREATE TABLE work_readings (
    work_reading_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    work_report_id UUID NOT NULL,
    equipment_id UUID,
    parameter_code TEXT NOT NULL,
    numeric_value NUMERIC(18,6) NOT NULL,
    unit_code TEXT NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL,
    is_estimated BOOLEAN DEFAULT false NOT NULL,
    PRIMARY KEY (work_reading_id),
    CHECK (length(trim(unit_code)) > 0)
);

CREATE TABLE evidence_files (
    evidence_file_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    work_report_id UUID,
    uploaded_by UUID NOT NULL,
    stage TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    captured_at TIMESTAMPTZ,
    uploaded_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (evidence_file_id),
    UNIQUE (site_id,work_order_id,evidence_file_id),
    UNIQUE (storage_key),
    CHECK (stage IN ('before','after','issue','other')),
    CHECK (mime_type IN ('image/jpeg','image/png','image/webp','image/heic','application/pdf')),
    CHECK (file_size > 0),
    CHECK (sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE acceptance_reviews (
    acceptance_review_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    work_report_id UUID NOT NULL,
    reviewer_user_id UUID NOT NULL,
    decision TEXT NOT NULL,
    comment TEXT,
    reviewed_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (acceptance_review_id),
    UNIQUE (site_id,work_report_id),
    CHECK (decision IN ('accepted','rework','rejected'))
);

CREATE TABLE predictor_versions (
    predictor_version_id UUID DEFAULT gen_random_uuid() NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    artifact_ref TEXT,
    config_snapshot JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (predictor_version_id),
    UNIQUE (kind,name,version),
    CHECK (kind IN ('rule','ai','vision','orchestrator')),
    CHECK (jsonb_typeof(config_snapshot) = 'object')
);

CREATE TABLE forecast_runs (
    forecast_run_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    maintenance_rule_id UUID NOT NULL,
    equipment_id UUID,
    predictor_version_id UUID NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL,
    input_snapshot JSONB DEFAULT '{}' NOT NULL,
    proposal_at TIMESTAMPTZ,
    regulatory_deadline_at TIMESTAMPTZ NOT NULL,
    confidence NUMERIC(5,4),
    risk_score NUMERIC(5,4),
    rationale TEXT,
    output_snapshot JSONB DEFAULT '{}' NOT NULL,
    produced_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (forecast_run_id),
    UNIQUE (site_id,system_id,maintenance_rule_id,forecast_run_id),
    CHECK (method IN ('rule','ai')),
    CHECK (status IN ('ok','unavailable','insufficient_data','failed')),
    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CHECK (risk_score IS NULL OR risk_score BETWEEN 0 AND 1),
    CHECK ((status = 'ok' AND proposal_at IS NOT NULL) OR (status <> 'ok' AND proposal_at IS NULL)),
    CHECK (jsonb_typeof(input_snapshot) = 'object'),
    CHECK (jsonb_typeof(output_snapshot) = 'object')
);

CREATE TABLE orchestration_decisions (
    orchestration_decision_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    system_id UUID NOT NULL,
    maintenance_rule_id UUID NOT NULL,
    rule_forecast_id UUID,
    ai_forecast_id UUID,
    orchestrator_version_id UUID NOT NULL,
    selected_method TEXT NOT NULL,
    selected_at TIMESTAMPTZ,
    regulatory_deadline_at TIMESTAMPTZ NOT NULL,
    requires_human_approval BOOLEAN DEFAULT true NOT NULL,
    reason TEXT NOT NULL,
    comparison_snapshot JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (orchestration_decision_id),
    UNIQUE (site_id,system_id,maintenance_rule_id,orchestration_decision_id),
    CHECK (selected_method IN ('rule','ai','conservative_fallback','manual_review')),
    CHECK ((selected_method = 'manual_review' AND selected_at IS NULL) OR (selected_method <> 'manual_review' AND selected_at IS NOT NULL)),
    CHECK (selected_at IS NULL OR selected_at <= regulatory_deadline_at),
    CHECK (jsonb_typeof(comparison_snapshot) = 'object'),
    CHECK (length(trim(reason)) > 0)
);

CREATE TABLE ai_quality_checks (
    ai_quality_check_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    work_report_id UUID,
    before_file_id UUID,
    after_file_id UUID,
    predictor_version_id UUID NOT NULL,
    status TEXT NOT NULL,
    visible_change TEXT,
    assessment TEXT NOT NULL,
    confidence NUMERIC(5,4),
    findings JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (ai_quality_check_id),
    CHECK (status IN ('ok','inconclusive','failed')),
    CHECK (assessment IN ('consistent','concern','inconclusive')),
    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CHECK (jsonb_typeof(findings) = 'object')
);

CREATE TABLE audit_events (
    audit_event_id UUID DEFAULT gen_random_uuid() NOT NULL,
    site_id UUID NOT NULL,
    actor_type TEXT NOT NULL,
    actor_user_id UUID,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    action TEXT NOT NULL,
    before_snapshot JSONB,
    after_snapshot JSONB,
    occurred_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (audit_event_id),
    CHECK (actor_type IN ('user','system','ai')),
    CHECK ((actor_type = 'user' AND actor_user_id IS NOT NULL) OR (actor_type <> 'user'))
);

ALTER TABLE site_memberships ADD CONSTRAINT fk_1 FOREIGN KEY (site_id) REFERENCES sites (site_id) ON DELETE RESTRICT;

ALTER TABLE site_memberships ADD CONSTRAINT fk_2 FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE RESTRICT;

ALTER TABLE engineering_systems ADD CONSTRAINT fk_3 FOREIGN KEY (site_id) REFERENCES sites (site_id) ON DELETE RESTRICT;

ALTER TABLE equipment ADD CONSTRAINT fk_4 FOREIGN KEY (site_id, system_id) REFERENCES engineering_systems (site_id, system_id) ON DELETE RESTRICT;

ALTER TABLE equipment ADD CONSTRAINT fk_5 FOREIGN KEY (site_id, parent_equipment_id) REFERENCES equipment (site_id, equipment_id) ON DELETE RESTRICT;

ALTER TABLE equipment ADD CONSTRAINT fk_6 FOREIGN KEY (equipment_type_id) REFERENCES equipment_types (equipment_type_id) ON DELETE RESTRICT;

ALTER TABLE user_skills ADD CONSTRAINT fk_7 FOREIGN KEY (site_id, user_id) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE user_skills ADD CONSTRAINT fk_8 FOREIGN KEY (skill_id) REFERENCES skills (skill_id) ON DELETE RESTRICT;

ALTER TABLE availability_slots ADD CONSTRAINT fk_9 FOREIGN KEY (site_id, user_id) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE crews ADD CONSTRAINT fk_10 FOREIGN KEY (site_id) REFERENCES sites (site_id) ON DELETE RESTRICT;

ALTER TABLE crew_members ADD CONSTRAINT fk_11 FOREIGN KEY (site_id, crew_id) REFERENCES crews (site_id, crew_id) ON DELETE RESTRICT;

ALTER TABLE crew_members ADD CONSTRAINT fk_12 FOREIGN KEY (site_id, user_id) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE operation_templates ADD CONSTRAINT fk_13 FOREIGN KEY (site_id, system_id) REFERENCES engineering_systems (site_id, system_id) ON DELETE RESTRICT;

ALTER TABLE operation_templates ADD CONSTRAINT fk_14 FOREIGN KEY (maintenance_type_id) REFERENCES maintenance_types (maintenance_type_id) ON DELETE RESTRICT;

ALTER TABLE regulation_documents ADD CONSTRAINT fk_15 FOREIGN KEY (site_id) REFERENCES sites (site_id) ON DELETE RESTRICT;

ALTER TABLE regulation_editions ADD CONSTRAINT fk_16 FOREIGN KEY (site_id, regulation_document_id) REFERENCES regulation_documents (site_id, regulation_document_id) ON DELETE RESTRICT;

ALTER TABLE regulation_editions ADD CONSTRAINT fk_17 FOREIGN KEY (site_id, approved_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE maintenance_rules ADD CONSTRAINT fk_18 FOREIGN KEY (site_id, system_id, operation_template_id) REFERENCES operation_templates (site_id, system_id, operation_template_id) ON DELETE RESTRICT;

ALTER TABLE maintenance_rules ADD CONSTRAINT fk_19 FOREIGN KEY (site_id, regulation_edition_id) REFERENCES regulation_editions (site_id, regulation_edition_id) ON DELETE RESTRICT;

ALTER TABLE maintenance_rules ADD CONSTRAINT fk_20 FOREIGN KEY (site_id, supersedes_rule_id) REFERENCES maintenance_rules (site_id, maintenance_rule_id) ON DELETE RESTRICT;

ALTER TABLE rule_equipment ADD CONSTRAINT fk_21 FOREIGN KEY (site_id, system_id, maintenance_rule_id) REFERENCES maintenance_rules (site_id, system_id, maintenance_rule_id) ON DELETE RESTRICT;

ALTER TABLE rule_equipment ADD CONSTRAINT fk_22 FOREIGN KEY (site_id, system_id, equipment_id) REFERENCES equipment (site_id, system_id, equipment_id) ON DELETE RESTRICT;

ALTER TABLE rule_required_skills ADD CONSTRAINT fk_23 FOREIGN KEY (site_id, maintenance_rule_id) REFERENCES maintenance_rules (site_id, maintenance_rule_id) ON DELETE RESTRICT;

ALTER TABLE rule_required_skills ADD CONSTRAINT fk_24 FOREIGN KEY (skill_id) REFERENCES skills (skill_id) ON DELETE RESTRICT;

ALTER TABLE schedule_plans ADD CONSTRAINT fk_25 FOREIGN KEY (site_id) REFERENCES sites (site_id) ON DELETE RESTRICT;

ALTER TABLE schedule_plans ADD CONSTRAINT fk_26 FOREIGN KEY (site_id, created_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE schedule_plans ADD CONSTRAINT fk_27 FOREIGN KEY (site_id, approved_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE schedule_entries ADD CONSTRAINT fk_28 FOREIGN KEY (site_id, schedule_plan_id) REFERENCES schedule_plans (site_id, schedule_plan_id) ON DELETE RESTRICT;

ALTER TABLE schedule_entries ADD CONSTRAINT fk_29 FOREIGN KEY (site_id, system_id, maintenance_rule_id) REFERENCES maintenance_rules (site_id, system_id, maintenance_rule_id) ON DELETE RESTRICT;

ALTER TABLE schedule_entries ADD CONSTRAINT fk_30 FOREIGN KEY (site_id, system_id, maintenance_rule_id, orchestration_decision_id) REFERENCES orchestration_decisions (site_id, system_id, maintenance_rule_id, orchestration_decision_id) ON DELETE RESTRICT;

ALTER TABLE incident_reports ADD CONSTRAINT fk_31 FOREIGN KEY (site_id, system_id) REFERENCES engineering_systems (site_id, system_id) ON DELETE RESTRICT;

ALTER TABLE incident_reports ADD CONSTRAINT fk_32 FOREIGN KEY (site_id, system_id, equipment_id) REFERENCES equipment (site_id, system_id, equipment_id) ON DELETE RESTRICT;

ALTER TABLE incident_reports ADD CONSTRAINT fk_33 FOREIGN KEY (site_id, reported_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE work_orders ADD CONSTRAINT fk_34 FOREIGN KEY (site_id, system_id) REFERENCES engineering_systems (site_id, system_id) ON DELETE RESTRICT;

ALTER TABLE work_orders ADD CONSTRAINT fk_35 FOREIGN KEY (site_id, system_id, maintenance_rule_id) REFERENCES maintenance_rules (site_id, system_id, maintenance_rule_id) ON DELETE RESTRICT;

ALTER TABLE work_orders ADD CONSTRAINT fk_36 FOREIGN KEY (site_id, system_id, schedule_entry_id) REFERENCES schedule_entries (site_id, system_id, schedule_entry_id) ON DELETE RESTRICT;

ALTER TABLE work_orders ADD CONSTRAINT fk_37 FOREIGN KEY (site_id, system_id, incident_report_id) REFERENCES incident_reports (site_id, system_id, incident_report_id) ON DELETE RESTRICT;

ALTER TABLE work_orders ADD CONSTRAINT fk_38 FOREIGN KEY (site_id, created_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE work_orders ADD CONSTRAINT fk_39 FOREIGN KEY (site_id, system_id, maintenance_rule_id, orchestration_decision_id) REFERENCES orchestration_decisions (site_id, system_id, maintenance_rule_id, orchestration_decision_id) ON DELETE RESTRICT;

ALTER TABLE work_order_equipment ADD CONSTRAINT fk_40 FOREIGN KEY (site_id, system_id, work_order_id) REFERENCES work_orders (site_id, system_id, work_order_id) ON DELETE RESTRICT;

ALTER TABLE work_order_equipment ADD CONSTRAINT fk_41 FOREIGN KEY (site_id, system_id, equipment_id) REFERENCES equipment (site_id, system_id, equipment_id) ON DELETE RESTRICT;

ALTER TABLE work_assignments ADD CONSTRAINT fk_42 FOREIGN KEY (site_id, work_order_id) REFERENCES work_orders (site_id, work_order_id) ON DELETE RESTRICT;

ALTER TABLE work_assignments ADD CONSTRAINT fk_43 FOREIGN KEY (site_id, user_id) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE work_assignments ADD CONSTRAINT fk_44 FOREIGN KEY (site_id, assigned_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE work_assignments ADD CONSTRAINT fk_45 FOREIGN KEY (site_id, crew_id) REFERENCES crews (site_id, crew_id) ON DELETE RESTRICT;

ALTER TABLE checklist_templates ADD CONSTRAINT fk_46 FOREIGN KEY (site_id, operation_template_id) REFERENCES operation_templates (site_id, operation_template_id) ON DELETE RESTRICT;

ALTER TABLE work_reports ADD CONSTRAINT fk_47 FOREIGN KEY (site_id, work_order_id) REFERENCES work_orders (site_id, work_order_id) ON DELETE RESTRICT;

ALTER TABLE work_reports ADD CONSTRAINT fk_48 FOREIGN KEY (site_id, submitted_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE checklist_results ADD CONSTRAINT fk_49 FOREIGN KEY (site_id, work_order_id, work_report_id) REFERENCES work_reports (site_id, work_order_id, work_report_id) ON DELETE RESTRICT;

ALTER TABLE checklist_results ADD CONSTRAINT fk_50 FOREIGN KEY (site_id, checklist_template_id) REFERENCES checklist_templates (site_id, checklist_template_id) ON DELETE RESTRICT;

ALTER TABLE work_readings ADD CONSTRAINT fk_51 FOREIGN KEY (site_id, system_id, work_order_id) REFERENCES work_orders (site_id, system_id, work_order_id) ON DELETE RESTRICT;

ALTER TABLE work_readings ADD CONSTRAINT fk_52 FOREIGN KEY (site_id, work_order_id, work_report_id) REFERENCES work_reports (site_id, work_order_id, work_report_id) ON DELETE RESTRICT;

ALTER TABLE work_readings ADD CONSTRAINT fk_53 FOREIGN KEY (site_id, system_id, equipment_id) REFERENCES equipment (site_id, system_id, equipment_id) ON DELETE RESTRICT;

ALTER TABLE evidence_files ADD CONSTRAINT fk_54 FOREIGN KEY (site_id, work_order_id) REFERENCES work_orders (site_id, work_order_id) ON DELETE RESTRICT;

ALTER TABLE evidence_files ADD CONSTRAINT fk_55 FOREIGN KEY (site_id, work_order_id, work_report_id) REFERENCES work_reports (site_id, work_order_id, work_report_id) ON DELETE RESTRICT;

ALTER TABLE evidence_files ADD CONSTRAINT fk_56 FOREIGN KEY (site_id, uploaded_by) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE acceptance_reviews ADD CONSTRAINT fk_57 FOREIGN KEY (site_id, work_order_id, work_report_id) REFERENCES work_reports (site_id, work_order_id, work_report_id) ON DELETE RESTRICT;

ALTER TABLE acceptance_reviews ADD CONSTRAINT fk_58 FOREIGN KEY (site_id, reviewer_user_id) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

ALTER TABLE forecast_runs ADD CONSTRAINT fk_59 FOREIGN KEY (site_id, system_id, maintenance_rule_id) REFERENCES maintenance_rules (site_id, system_id, maintenance_rule_id) ON DELETE RESTRICT;

ALTER TABLE forecast_runs ADD CONSTRAINT fk_60 FOREIGN KEY (site_id, system_id, equipment_id) REFERENCES equipment (site_id, system_id, equipment_id) ON DELETE RESTRICT;

ALTER TABLE forecast_runs ADD CONSTRAINT fk_61 FOREIGN KEY (predictor_version_id) REFERENCES predictor_versions (predictor_version_id) ON DELETE RESTRICT;

ALTER TABLE orchestration_decisions ADD CONSTRAINT fk_62 FOREIGN KEY (site_id, system_id, maintenance_rule_id) REFERENCES maintenance_rules (site_id, system_id, maintenance_rule_id) ON DELETE RESTRICT;

ALTER TABLE orchestration_decisions ADD CONSTRAINT fk_63 FOREIGN KEY (site_id, system_id, maintenance_rule_id, rule_forecast_id) REFERENCES forecast_runs (site_id, system_id, maintenance_rule_id, forecast_run_id) ON DELETE RESTRICT;

ALTER TABLE orchestration_decisions ADD CONSTRAINT fk_64 FOREIGN KEY (site_id, system_id, maintenance_rule_id, ai_forecast_id) REFERENCES forecast_runs (site_id, system_id, maintenance_rule_id, forecast_run_id) ON DELETE RESTRICT;

ALTER TABLE orchestration_decisions ADD CONSTRAINT fk_65 FOREIGN KEY (orchestrator_version_id) REFERENCES predictor_versions (predictor_version_id) ON DELETE RESTRICT;

ALTER TABLE ai_quality_checks ADD CONSTRAINT fk_66 FOREIGN KEY (site_id, work_order_id) REFERENCES work_orders (site_id, work_order_id) ON DELETE RESTRICT;

ALTER TABLE ai_quality_checks ADD CONSTRAINT fk_67 FOREIGN KEY (site_id, work_order_id, work_report_id) REFERENCES work_reports (site_id, work_order_id, work_report_id) ON DELETE RESTRICT;

ALTER TABLE ai_quality_checks ADD CONSTRAINT fk_68 FOREIGN KEY (site_id, work_order_id, before_file_id) REFERENCES evidence_files (site_id, work_order_id, evidence_file_id) ON DELETE RESTRICT;

ALTER TABLE ai_quality_checks ADD CONSTRAINT fk_69 FOREIGN KEY (site_id, work_order_id, after_file_id) REFERENCES evidence_files (site_id, work_order_id, evidence_file_id) ON DELETE RESTRICT;

ALTER TABLE ai_quality_checks ADD CONSTRAINT fk_70 FOREIGN KEY (predictor_version_id) REFERENCES predictor_versions (predictor_version_id) ON DELETE RESTRICT;

ALTER TABLE audit_events ADD CONSTRAINT fk_71 FOREIGN KEY (site_id) REFERENCES sites (site_id) ON DELETE RESTRICT;

ALTER TABLE audit_events ADD CONSTRAINT fk_72 FOREIGN KEY (site_id, actor_user_id) REFERENCES site_memberships (site_id, user_id) ON DELETE RESTRICT;

CREATE INDEX idx_sites_1 ON sites (is_active, name);

CREATE UNIQUE INDEX idx_users_1 ON users (lower(email));

CREATE INDEX idx_site_memberships_1 ON site_memberships (user_id, is_active);

CREATE INDEX idx_engineering_systems_1 ON engineering_systems (site_id,name);

CREATE INDEX idx_equipment_1 ON equipment (site_id,system_id,status);

CREATE INDEX idx_equipment_2 ON equipment (site_id,parent_equipment_id);

CREATE INDEX idx_availability_slots_1 ON availability_slots (site_id,user_id,starts_at,ends_at);

CREATE INDEX idx_crew_members_1 ON crew_members (site_id,crew_id,valid_to);

CREATE UNIQUE INDEX idx_crew_members_2 ON crew_members (site_id,crew_id,user_id) WHERE valid_to IS NULL;

CREATE INDEX idx_operation_templates_1 ON operation_templates (site_id,system_id,maintenance_type_id);

CREATE INDEX idx_regulation_editions_1 ON regulation_editions (site_id,effective_from,effective_to);

CREATE INDEX idx_maintenance_rules_1 ON maintenance_rules (site_id,system_id,publication_status,active_from);

CREATE INDEX idx_rule_equipment_1 ON rule_equipment (site_id,equipment_id);

CREATE UNIQUE INDEX idx_rule_equipment_2 ON rule_equipment (site_id,maintenance_rule_id,equipment_id) WHERE valid_to IS NULL;

CREATE UNIQUE INDEX idx_schedule_plans_1 ON schedule_plans (site_id,period_year,period_month) WHERE status = 'approved';

CREATE INDEX idx_schedule_entries_1 ON schedule_entries (site_id,planned_date,status);

CREATE INDEX idx_schedule_entries_2 ON schedule_entries (site_id,maintenance_rule_id,planned_date);

CREATE INDEX idx_work_orders_1 ON work_orders (site_id,status,regulatory_deadline_at);

CREATE INDEX idx_work_orders_2 ON work_orders (site_id,system_id,created_at);

CREATE INDEX idx_work_assignments_1 ON work_assignments (site_id,user_id,status,assigned_at);

CREATE INDEX idx_work_readings_1 ON work_readings (site_id,equipment_id,measured_at);

CREATE INDEX idx_work_readings_2 ON work_readings (site_id,work_order_id);

CREATE INDEX idx_evidence_files_1 ON evidence_files (site_id,work_order_id,stage);

CREATE INDEX idx_acceptance_reviews_1 ON acceptance_reviews (site_id,work_order_id,reviewed_at);

CREATE INDEX idx_forecast_runs_1 ON forecast_runs (site_id,maintenance_rule_id,produced_at DESC);

CREATE INDEX idx_forecast_runs_2 ON forecast_runs (site_id,equipment_id,produced_at DESC);

CREATE INDEX idx_orchestration_decisions_1 ON orchestration_decisions (site_id,maintenance_rule_id,created_at DESC);

CREATE INDEX idx_ai_quality_checks_1 ON ai_quality_checks (site_id,work_order_id,created_at DESC);

CREATE INDEX idx_audit_events_1 ON audit_events (site_id,entity_type,entity_id,occurred_at);

CREATE INDEX idx_audit_events_2 ON audit_events (site_id,occurred_at DESC);

COMMIT;
