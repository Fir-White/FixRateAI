-- FixRate AI · initial PostgreSQL schema v3.1 · PostgreSQL 16 + pgvector.
-- Каждая версия нормативного источника и сметы хранится отдельно.
-- Демо-цены НЕ считаются подтверждёнными тарифами.
-- Применять ТОЛЬКО к пустой базе; для изменений использовать новые миграции.
-- SQL-транзакция обеспечивает откат при ошибке.
-- Расширение vector должно быть заранее установлено на сервере PostgreSQL.

BEGIN;

-- В PostgreSQL 16 gen_random_uuid() доступен без расширения pgcrypto.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash TEXT,
    role VARCHAR(30) NOT NULL DEFAULT 'operator' CHECK (role IN ('operator','estimator','admin')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email));
ALTER TABLE users ADD CONSTRAINT chk_user_email_nonempty CHECK (length(btrim(email)) > 0);

CREATE TABLE buildings (
    building_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    address TEXT NOT NULL,
    building_type VARCHAR(100),
    construction_year SMALLINT CHECK (construction_year BETWEEN 1800 AND 2200),
    floors_count SMALLINT CHECK (floors_count > 0),
    total_area NUMERIC(12,2) CHECK (total_area > 0),
    wall_material VARCHAR(100),
    additional_properties JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(additional_properties) = 'object'),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE defect_types (
    defect_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE norm_sources (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(30) NOT NULL CHECK (source_type IN ('FER','TER','COMMERCIAL','DEMO')),
    title TEXT NOT NULL,
    edition VARCHAR(100),
    region VARCHAR(100),
    publication_date DATE,
    effective_date DATE,
    source_url TEXT,
    document_reference TEXT,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_verified_has_reference CHECK (NOT is_verified OR source_url IS NOT NULL OR document_reference IS NOT NULL)
);

CREATE TABLE repair_requests (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id UUID NOT NULL,
    created_by UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    location_description TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'created' CHECK (status IN ('created','processing','needs_clarification','ready_for_review','closed','cancelled','failed')),
    cancellation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_requests_building FOREIGN KEY (building_id) REFERENCES buildings(building_id) ON DELETE RESTRICT,
    CONSTRAINT fk_requests_author FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE RESTRICT
);
CREATE INDEX idx_requests_building_date ON repair_requests (building_id, created_at DESC);
CREATE INDEX idx_requests_author_date ON repair_requests (created_by, created_at DESC);

CREATE TABLE request_photos (
    photo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL CHECK (file_size > 0),
    checksum_sha256 CHAR(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9A-Fa-f]{64}$'),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_photo_request UNIQUE (photo_id, request_id),
    CONSTRAINT fk_photos_request FOREIGN KEY (request_id) REFERENCES repair_requests(request_id) ON DELETE RESTRICT
);
CREATE INDEX idx_photos_request ON request_photos(request_id);

CREATE TABLE ai_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed','needs_clarification')),
    pipeline_version VARCHAR(50) NOT NULL,
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(input_snapshot) = 'object'),
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_run_request UNIQUE (run_id, request_id),
    CONSTRAINT fk_runs_request FOREIGN KEY (request_id) REFERENCES repair_requests(request_id) ON DELETE RESTRICT
);
CREATE INDEX idx_runs_request_started ON ai_runs (request_id, started_at DESC);

CREATE TABLE ai_results (
    ai_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    request_id UUID NOT NULL,
    module_type VARCHAR(20) NOT NULL CHECK (module_type IN ('cv','nlp','rag')),
    model_name VARCHAR(150),
    model_version VARCHAR(100),
    input_reference JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(input_reference) = 'object'),
    result_data JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(result_data) = 'object'),
    status VARCHAR(30) NOT NULL DEFAULT 'completed' CHECK (status IN ('running','completed','failed','uncertain')),
    processing_time_ms INTEGER CHECK (processing_time_ms >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_result_request UNIQUE (ai_result_id, request_id),
    CONSTRAINT fk_results_run_request FOREIGN KEY (run_id, request_id) REFERENCES ai_runs(run_id, request_id) ON DELETE RESTRICT
);
CREATE INDEX idx_results_run ON ai_results(run_id);

CREATE TABLE defects (
    defect_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    defect_type_id UUID,
    source_ai_result_id UUID,
    description TEXT,
    location_description TEXT,
    confirmation_status VARCHAR(30) NOT NULL DEFAULT 'suggested' CHECK (confirmation_status IN ('suggested','confirmed','rejected')),
    confirmed_by UUID,
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_defect_request UNIQUE (defect_id, request_id),
    CONSTRAINT chk_defect_confirmation CHECK (confirmation_status <> 'confirmed' OR (confirmed_by IS NOT NULL AND defect_type_id IS NOT NULL)),
    CONSTRAINT fk_defects_request FOREIGN KEY (request_id) REFERENCES repair_requests(request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_defects_type FOREIGN KEY (defect_type_id) REFERENCES defect_types(defect_type_id) ON DELETE RESTRICT,
    CONSTRAINT fk_defects_ai_result_request FOREIGN KEY (source_ai_result_id, request_id) REFERENCES ai_results(ai_result_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_defects_confirmer FOREIGN KEY (confirmed_by) REFERENCES users(user_id) ON DELETE RESTRICT
);
CREATE INDEX idx_defects_request ON defects(request_id);

CREATE TABLE defect_photos (
    defect_id UUID NOT NULL,
    photo_id UUID NOT NULL,
    request_id UUID NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (defect_id, photo_id),
    CONSTRAINT fk_defect_photos_defect_request FOREIGN KEY (defect_id, request_id) REFERENCES defects(defect_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_defect_photos_photo_request FOREIGN KEY (photo_id, request_id) REFERENCES request_photos(photo_id, request_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX uq_defect_single_primary_photo ON defect_photos(defect_id) WHERE is_primary;
CREATE INDEX idx_defect_photos_photo ON defect_photos(photo_id);

CREATE TABLE defect_measurements (
    measurement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    defect_id UUID NOT NULL,
    request_id UUID NOT NULL,
    parameter_code VARCHAR(60) NOT NULL,
    value NUMERIC(16,6) NOT NULL CHECK (value >= 0),
    unit_code VARCHAR(20) NOT NULL,
    source_type VARCHAR(30) NOT NULL CHECK (source_type IN ('manual','text','photo','document','derived')),
    source_ai_result_id UUID,
    recorded_by UUID,
    is_approximate BOOLEAN NOT NULL DEFAULT FALSE,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('unverified','confirmed','rejected')),
    supersedes_measurement_id UUID,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_measurement_defect UNIQUE (measurement_id, defect_id),
    CONSTRAINT chk_measurement_no_self_reference CHECK (supersedes_measurement_id IS DISTINCT FROM measurement_id),
    CONSTRAINT fk_measure_defect_request FOREIGN KEY (defect_id, request_id) REFERENCES defects(defect_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_measure_ai_request FOREIGN KEY (source_ai_result_id, request_id) REFERENCES ai_results(ai_result_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_measure_user FOREIGN KEY (recorded_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_measure_previous_same_defect FOREIGN KEY (supersedes_measurement_id, defect_id) REFERENCES defect_measurements(measurement_id, defect_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX uq_measure_current_per_parameter ON defect_measurements(defect_id, parameter_code) WHERE is_current;
CREATE INDEX idx_measurements_request ON defect_measurements(request_id);

CREATE TABLE rates (
    rate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL,
    rate_code VARCHAR(100),
    work_name TEXT NOT NULL,
    description TEXT,
    unit_code VARCHAR(20) NOT NULL,
    rate_unit_multiplier NUMERIC(14,4) NOT NULL DEFAULT 1 CHECK (rate_unit_multiplier > 0),
    base_price NUMERIC(18,4) CHECK (base_price >= 0),
    currency CHAR(3) CHECK (currency ~ '^[A-Z]{3}$'),
    price_basis VARCHAR(30) NOT NULL CHECK (price_basis IN ('commercial','normative_base','demo')),
    cost_scope VARCHAR(30) NOT NULL CHECK (cost_scope IN ('work_only','all_inclusive','resource_based')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_rate_source UNIQUE (rate_id, source_id),
    CONSTRAINT uq_rate_code_source UNIQUE (source_id, rate_code),
    CONSTRAINT fk_rates_source FOREIGN KEY (source_id) REFERENCES norm_sources(source_id) ON DELETE RESTRICT
);
CREATE INDEX idx_rates_work_name ON rates USING GIN (to_tsvector('russian', work_name));

-- Единая таблица поисковых фрагментов; вектор без фиксированной размерности до выбора embedding-модели.
CREATE TABLE normative_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL,
    rate_id UUID,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    embedding VECTOR,
    embedding_model VARCHAR(150),
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('russian', content)) STORED,
    source_locator JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_locator) = 'object'),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    content_hash CHAR(64) NOT NULL CHECK (content_hash ~ '^[0-9A-Fa-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chunk_source_index UNIQUE (source_id, chunk_index),
    CONSTRAINT chk_chunk_embedding_model CHECK ((embedding IS NULL) = (embedding_model IS NULL)),
    CONSTRAINT fk_chunks_source FOREIGN KEY (source_id) REFERENCES norm_sources(source_id) ON DELETE RESTRICT,
    CONSTRAINT fk_chunks_rate_same_source FOREIGN KEY (rate_id, source_id) REFERENCES rates(rate_id, source_id) ON DELETE RESTRICT
);
CREATE INDEX idx_chunks_search_vector ON normative_chunks USING GIN(search_vector);
CREATE INDEX idx_chunks_rate ON normative_chunks(rate_id);
-- Пример индекса HNSW, только ПОСЛЕ выбора единой размерности эмбеддингов (пример: 768):
-- CREATE INDEX idx_chunks_hnsw_768 ON normative_chunks USING hnsw
--     ((embedding::vector(768)) vector_cosine_ops)
--     WHERE embedding IS NOT NULL AND vector_dims(embedding) = 768;
-- Встроенный PostgreSQL tsvector НЕ реализует BM25. BM25 относится к поисковому ML-модулю
-- либо реализуется через отдельно выбранное расширение, без изменения ключевой ER-модели.

CREATE TABLE estimates (
    estimate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    based_on_run_id UUID,
    status VARCHAR(30) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','needs_review','approved','rejected','superseded')),
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(input_snapshot) = 'object'),
    total_cost NUMERIC(18,2) CHECK (total_cost >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    review_comment TEXT,
    CONSTRAINT uq_estimates_request_version UNIQUE (request_id, version),
    CONSTRAINT uq_estimate_request UNIQUE (estimate_id, request_id),
    CONSTRAINT chk_approved_has_reviewer CHECK (status <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    CONSTRAINT fk_estimates_request FOREIGN KEY (request_id) REFERENCES repair_requests(request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_estimates_run_same_request FOREIGN KEY (based_on_run_id, request_id) REFERENCES ai_runs(run_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_estimates_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(user_id) ON DELETE RESTRICT
);
CREATE INDEX idx_estimates_request_recent ON estimates (request_id, version DESC);

CREATE TABLE estimate_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id UUID NOT NULL,
    request_id UUID NOT NULL,
    defect_id UUID,
    rate_id UUID,
    work_name TEXT NOT NULL,
    quantity NUMERIC(16,6) CHECK (quantity >= 0),
    unit_code VARCHAR(20),
    unit_price NUMERIC(18,4) CHECK (unit_price >= 0),
    coefficient NUMERIC(14,6) NOT NULL DEFAULT 1 CHECK (coefficient > 0),
    base_cost NUMERIC(18,2) CHECK (base_cost >= 0),
    additional_materials_cost NUMERIC(18,2) CHECK (additional_materials_cost >= 0),
    total_cost NUMERIC(18,2) CHECK (total_cost >= 0),
    calculation_details JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(calculation_details) = 'object'),
    validation_status VARCHAR(30) NOT NULL DEFAULT 'needs_review' CHECK (validation_status IN ('valid','blocked','needs_review')),
    source_snapshot JSONB CHECK (source_snapshot IS NULL OR jsonb_typeof(source_snapshot) = 'object'),
    -- Для ручной позиции rate_id может быть NULL, но источник ручной цены обязан быть зафиксирован.
    CONSTRAINT chk_item_valid_priced CHECK (
        validation_status <> 'valid' OR (
            quantity IS NOT NULL AND quantity > 0
            AND unit_code IS NOT NULL AND length(btrim(unit_code)) > 0
            AND unit_price IS NOT NULL AND base_cost IS NOT NULL AND total_cost IS NOT NULL
            AND source_snapshot IS NOT NULL AND source_snapshot <> '{}'::jsonb
            AND (rate_id IS NOT NULL OR source_snapshot ->> 'origin' = 'manual')
        )
    ),
    CONSTRAINT chk_item_valid_math CHECK (
        validation_status <> 'valid' OR
        total_cost = base_cost + COALESCE(additional_materials_cost, 0)
    ),
    CONSTRAINT fk_items_estimate_same_request FOREIGN KEY (estimate_id, request_id) REFERENCES estimates(estimate_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_items_defect_same_request FOREIGN KEY (defect_id, request_id) REFERENCES defects(defect_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_items_rate FOREIGN KEY (rate_id) REFERENCES rates(rate_id) ON DELETE RESTRICT
);
CREATE INDEX idx_items_estimate ON estimate_items(estimate_id);
CREATE INDEX idx_items_defect ON estimate_items(defect_id);
CREATE INDEX idx_items_rate ON estimate_items(rate_id);

CREATE TABLE estimate_materials (
    material_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id UUID NOT NULL,
    material_name TEXT NOT NULL,
    quantity NUMERIC(16,6) NOT NULL CHECK (quantity >= 0),
    unit_code VARCHAR(20) NOT NULL,
    unit_price NUMERIC(18,4) CHECK (unit_price >= 0),
    total_cost NUMERIC(18,2) CHECK (total_cost >= 0),
    source_id UUID,
    price_snapshot JSONB CHECK (price_snapshot IS NULL OR jsonb_typeof(price_snapshot) = 'object'),
    cost_treatment VARCHAR(30) NOT NULL CHECK (cost_treatment IN ('included_in_rate','additional','informational')),
    CONSTRAINT chk_material_additional_has_price CHECK (cost_treatment <> 'additional' OR (unit_price IS NOT NULL AND total_cost IS NOT NULL AND (source_id IS NOT NULL OR (price_snapshot IS NOT NULL AND price_snapshot <> '{}'::jsonb)))),
    CONSTRAINT fk_materials_item FOREIGN KEY (item_id) REFERENCES estimate_items(item_id) ON DELETE RESTRICT,
    CONSTRAINT fk_materials_source FOREIGN KEY (source_id) REFERENCES norm_sources(source_id) ON DELETE RESTRICT
);
CREATE INDEX idx_materials_item ON estimate_materials(item_id);

CREATE TABLE request_clarifications (
    clarification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    run_id UUID,
    field_name VARCHAR(100) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered','cancelled','superseded')),
    answered_by UUID,
    supersedes_clarification_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at TIMESTAMPTZ,
    CONSTRAINT uq_clarification_request UNIQUE (clarification_id, request_id),
    CONSTRAINT chk_clarification_answered CHECK (status <> 'answered' OR (answer IS NOT NULL AND answered_at IS NOT NULL)),
    CONSTRAINT chk_clarification_not_self CHECK (supersedes_clarification_id IS DISTINCT FROM clarification_id),
    CONSTRAINT fk_clarifications_request FOREIGN KEY (request_id) REFERENCES repair_requests(request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_clarifications_run_same_request FOREIGN KEY (run_id, request_id) REFERENCES ai_runs(run_id, request_id) ON DELETE RESTRICT,
    CONSTRAINT fk_clarifications_user FOREIGN KEY (answered_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_clarifications_previous_same_request FOREIGN KEY (supersedes_clarification_id, request_id) REFERENCES request_clarifications(clarification_id, request_id) ON DELETE RESTRICT
);
CREATE INDEX idx_clarifications_request ON request_clarifications(request_id);

CREATE TABLE audit_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type VARCHAR(20) NOT NULL CHECK (actor_type IN ('user','system','ai')),
    user_id UUID,
    request_id UUID,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    changes JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(changes) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_audit_actor CHECK ((actor_type = 'user' AND user_id IS NOT NULL) OR (actor_type <> 'user' AND user_id IS NULL)),
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_audit_request FOREIGN KEY (request_id) REFERENCES repair_requests(request_id) ON DELETE RESTRICT
);
CREATE INDEX idx_audit_request_time ON audit_events(request_id, created_at DESC);

-- ============================================================================
-- Service triggers: request timestamps, revisions, approval, audit immutability
-- ============================================================================

CREATE OR REPLACE FUNCTION fixrate_set_request_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_requests_updated_at
BEFORE UPDATE ON repair_requests
FOR EACH ROW EXECUTE FUNCTION fixrate_set_request_updated_at();

-- A version is mutable only while it is the latest draft/review version.
-- Terminal versions and versions with a successor never change. In particular,
-- an approved estimate stays approved as part of the version history; the latest
-- approved version is selected by version number, not by rewriting old rows.
CREATE OR REPLACE FUNCTION fixrate_assert_estimate_writable(p_estimate_id UUID)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_request_id UUID;
    v_version INTEGER;
    v_status VARCHAR(30);
BEGIN
    SELECT request_id, version, status
      INTO v_request_id, v_version, v_status
      FROM estimates WHERE estimate_id = p_estimate_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Estimate % does not exist', p_estimate_id;
    END IF;
    IF v_status IN ('approved','rejected','superseded') THEN
        RAISE EXCEPTION 'Estimate % is finalized (%)', p_estimate_id, v_status;
    END IF;
    IF EXISTS (
        SELECT 1 FROM estimates
         WHERE request_id = v_request_id AND version > v_version
    ) THEN
        RAISE EXCEPTION 'Estimate % has newer version and is read-only', p_estimate_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION fixrate_guard_estimate()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Estimate history cannot be deleted';
    END IF;
    IF NEW.estimate_id IS DISTINCT FROM OLD.estimate_id
       OR NEW.request_id IS DISTINCT FROM OLD.request_id
       OR NEW.version IS DISTINCT FROM OLD.version THEN
        RAISE EXCEPTION 'Estimate identity and version cannot be changed';
    END IF;
    PERFORM fixrate_assert_estimate_writable(OLD.estimate_id);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_guard_estimate
BEFORE UPDATE OR DELETE ON estimates
FOR EACH ROW EXECUTE FUNCTION fixrate_guard_estimate();

CREATE OR REPLACE FUNCTION fixrate_guard_estimate_item()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM fixrate_assert_estimate_writable(NEW.estimate_id);
        RETURN NEW;
    END IF;
    PERFORM fixrate_assert_estimate_writable(OLD.estimate_id);
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NEW.item_id IS DISTINCT FROM OLD.item_id
       OR NEW.estimate_id IS DISTINCT FROM OLD.estimate_id
       OR NEW.request_id IS DISTINCT FROM OLD.request_id THEN
        RAISE EXCEPTION 'Estimate item identity cannot be changed';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_guard_estimate_item
BEFORE INSERT OR UPDATE OR DELETE ON estimate_items
FOR EACH ROW EXECUTE FUNCTION fixrate_guard_estimate_item();

CREATE OR REPLACE FUNCTION fixrate_guard_estimate_material()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_estimate_id UUID;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT estimate_id INTO v_estimate_id FROM estimate_items WHERE item_id = NEW.item_id;
    ELSE
        SELECT estimate_id INTO v_estimate_id FROM estimate_items WHERE item_id = OLD.item_id;
    END IF;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Estimate item not found';
    END IF;
    PERFORM fixrate_assert_estimate_writable(v_estimate_id);
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' AND (
       NEW.item_id IS DISTINCT FROM OLD.item_id OR
       NEW.material_id IS DISTINCT FROM OLD.material_id) THEN
        RAISE EXCEPTION 'Estimate material identity cannot be changed';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_guard_estimate_material
BEFORE INSERT OR UPDATE OR DELETE ON estimate_materials
FOR EACH ROW EXECUTE FUNCTION fixrate_guard_estimate_material();

-- Approval checks are performed within the transaction that sets status=approved.
-- Only an authenticated human reviewer may approve via application authorization.
-- SQL FK ensures reviewer exists, but SQL cannot by itself verify session identity.
CREATE OR REPLACE FUNCTION fixrate_check_approval()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_item_count BIGINT;
    v_invalid_count BIGINT;
    v_items_total NUMERIC(20,2);
BEGIN
    IF NEW.status = 'approved' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'approved') THEN
        SELECT count(*), count(*) FILTER (WHERE validation_status <> 'valid'),
               COALESCE(sum(total_cost), 0)::NUMERIC(20,2)
          INTO v_item_count, v_invalid_count, v_items_total
          FROM estimate_items WHERE estimate_id = NEW.estimate_id;
        IF v_item_count = 0 OR v_invalid_count > 0 THEN
            RAISE EXCEPTION 'Cannot approve estimate: no items or unvalidated items';
        END IF;
        IF NEW.total_cost IS NULL OR NEW.total_cost <> v_items_total THEN
            RAISE EXCEPTION 'Cannot approve estimate: expected total %, got %',
                v_items_total, NEW.total_cost;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_check_estimate_approval
BEFORE INSERT OR UPDATE OF status ON estimates
FOR EACH ROW EXECUTE FUNCTION fixrate_check_approval();

-- Audit records are append-only at application level; DB owners/superusers
-- may bypass triggers, so backups and DB permissions remain necessary.
CREATE OR REPLACE FUNCTION fixrate_forbid_audit_change()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Audit events are append-only';
END;
$$;

CREATE TRIGGER trg_audit_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION fixrate_forbid_audit_change();

-- ============================================================================
-- Documentation stored in the database
-- ============================================================================
COMMENT ON TABLE users IS 'User accounts; deactivate instead of deleting to preserve history.';
COMMENT ON TABLE buildings IS 'Buildings with typed attributes and optional JSONB properties.';
COMMENT ON TABLE defect_types IS 'Version-stable defect type directory.';
COMMENT ON TABLE norm_sources IS 'Specific normative or commercial source editions and provenance.';
COMMENT ON TABLE repair_requests IS 'Repair requests and their processing lifecycle.';
COMMENT ON TABLE request_photos IS 'File metadata; photo bytes are stored outside PostgreSQL.';
COMMENT ON TABLE ai_runs IS 'Independent pipeline runs with input snapshots.';
COMMENT ON TABLE ai_results IS 'CV, NLP and RAG module results linked to a run.';
COMMENT ON TABLE defects IS 'Detected or confirmed defects related to repair requests.';
COMMENT ON TABLE defect_photos IS 'M:N photos-to-defects; at most one primary photo per defect.';
COMMENT ON TABLE defect_measurements IS 'Provenance, verification and history of measured defect parameters.';
COMMENT ON TABLE rates IS 'Edition-specific normative and commercial rates.';
COMMENT ON TABLE normative_chunks IS 'Source chunks for lexical and vector search; BM25 is not built-in PostgreSQL FTS.';
COMMENT ON TABLE estimates IS 'Versioned repair estimates; historical/finalized versions are immutable.';
COMMENT ON TABLE estimate_items IS 'Estimate jobs; manual jobs require documented price origin.';
COMMENT ON TABLE estimate_materials IS 'Material amounts and inclusion treatment (avoid double counting).';
COMMENT ON TABLE request_clarifications IS 'Questions/answers with preserved revision history.';
COMMENT ON TABLE audit_events IS 'Append-only application audit log.';
COMMENT ON COLUMN repair_requests.updated_at IS 'Automatically updated on each UPDATE.';
COMMENT ON COLUMN estimates.version IS 'Monotonic application-assigned version unique within request.';
COMMENT ON COLUMN estimates.status IS 'Finalized versions remain historical; do not rewrite old approval status.';
COMMENT ON COLUMN estimate_items.source_snapshot IS 'Price provenance; for manual jobs set origin=manual.';
COMMENT ON COLUMN estimate_items.base_cost IS 'Calculated work cost excluding additional materials.';
COMMENT ON COLUMN estimate_items.additional_materials_cost IS 'Additional material cost not already included in a rate.';
COMMENT ON COLUMN estimate_items.total_cost IS 'base_cost plus additional_materials_cost for validated items.';
COMMENT ON COLUMN rates.rate_unit_multiplier IS 'Unit basis multiplier, e.g. 100 for a rate per 100 m2.';
COMMENT ON COLUMN normative_chunks.embedding IS 'Vector dimension must match the embedding model; add a dedicated index later.';
COMMENT ON COLUMN normative_chunks.search_vector IS 'Russian full-text search vector, not BM25.';
COMMENT ON COLUMN estimate_materials.cost_treatment IS 'included_in_rate, additional, or informational.';
COMMENT ON COLUMN norm_sources.is_verified IS 'Verification flag applies to this edition and its cited source.';

-- Important application-level constraints not expressible as cheap row CHECKs:
-- • photo presence is in a separate table; input completeness validated by API;
-- • estimator identity/permissions are enforced by backend authorization;
-- • price applicability, normative indices and coefficients require the calculator;
-- • validate per-line arithmetic with Decimal and quantity / rate_unit_multiplier;
-- • compare sum of additional estimate_materials rows to additional_materials_cost;
-- • never approve unverified estimated quantities without reviewer judgement;
-- • version creation requires request-level serialization in backend (SELECT FOR UPDATE);
-- • embedded vector index requires a single embedding model and dimension;
-- • supersedes_* revision cycles and state transitions are backend responsibilities.

COMMIT;
