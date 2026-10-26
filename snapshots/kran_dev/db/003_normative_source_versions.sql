-- FixRate AI · normative source revisions and immutable price provenance.
-- Apply after 001_init.sql (and after 002_seed_demo.sql when DEMO data is used).
-- Existing source/rate rows are preserved; each legacy source starts its own series.

BEGIN;

-- A source series groups immutable editions of the same document or price list.
-- New revisions reuse source_series_id and point to the immediately preceding row.
ALTER TABLE norm_sources
    ADD COLUMN source_series_id UUID NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN supersedes_source_id UUID,
    ADD COLUMN provider_name TEXT,
    ADD COLUMN valid_to DATE,
    ADD COLUMN default_currency CHAR(3),
    ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE norm_sources
    DROP CONSTRAINT norm_sources_source_type_check,
    ADD CONSTRAINT norm_sources_source_type_check
        CHECK (source_type IN ('FER','FERR','TER','TERR','COMMERCIAL','DEMO')),
    ADD CONSTRAINT uq_norm_source_series_identity
        UNIQUE (source_id, source_series_id),
    ADD CONSTRAINT fk_norm_source_previous_same_series
        FOREIGN KEY (supersedes_source_id, source_series_id)
        REFERENCES norm_sources(source_id, source_series_id) ON DELETE RESTRICT,
    ADD CONSTRAINT chk_norm_source_title_nonempty
        CHECK (length(btrim(title)) > 0) NOT VALID,
    ADD CONSTRAINT chk_norm_source_edition_nonempty
        CHECK (edition IS NULL OR length(btrim(edition)) > 0) NOT VALID,
    ADD CONSTRAINT chk_norm_source_provider_nonempty
        CHECK (provider_name IS NULL OR length(btrim(provider_name)) > 0),
    ADD CONSTRAINT chk_norm_source_valid_period
        CHECK (valid_to IS NULL OR effective_date IS NULL OR valid_to >= effective_date),
    ADD CONSTRAINT chk_norm_source_currency
        CHECK (default_currency IS NULL OR default_currency ~ '^[A-Z]{3}$'),
    ADD CONSTRAINT chk_demo_source_unverified
        CHECK (source_type <> 'DEMO' OR NOT is_verified) NOT VALID,
    ADD CONSTRAINT chk_verified_source_details CHECK (
        NOT is_verified OR (
            COALESCE(NULLIF(btrim(edition), ''), effective_date::text) IS NOT NULL
            AND COALESCE(
                NULLIF(btrim(source_url), ''),
                NULLIF(btrim(document_reference), '')
            ) IS NOT NULL
            AND (
                source_type IN ('FER','FERR','TER','TERR')
                OR (
                    source_type = 'COMMERCIAL'
                    AND provider_name IS NOT NULL
                    AND default_currency IS NOT NULL
                )
            )
        )
    ) NOT VALID;

CREATE UNIQUE INDEX uq_norm_sources_current_series
    ON norm_sources(source_series_id) WHERE is_current;
CREATE INDEX idx_norm_sources_catalog_lookup
    ON norm_sources(source_type, region, is_current, effective_date DESC);
CREATE INDEX idx_norm_sources_series_effective
    ON norm_sources(source_series_id, effective_date DESC NULLS LAST);

-- price_date is the price-level base/period date when it differs from the
-- document effective date. NULL means "use the source edition/date".
ALTER TABLE rates
    ADD COLUMN price_date DATE,
    ADD CONSTRAINT chk_rate_code_nonempty
        CHECK (rate_code IS NOT NULL AND length(btrim(rate_code)) > 0) NOT VALID,
    ADD CONSTRAINT chk_rate_unit_nonempty
        CHECK (length(btrim(unit_code)) > 0) NOT VALID,
    ADD CONSTRAINT chk_rate_active_priced CHECK (
        NOT is_active OR (base_price IS NOT NULL AND currency IS NOT NULL)
    ) NOT VALID;

CREATE INDEX idx_rates_code ON rates(rate_code);

-- Cross-table validation prevents a normative, commercial or DEMO price from
-- being attached to an incompatible source category.
CREATE OR REPLACE FUNCTION fixrate_validate_rate_source()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_source_type VARCHAR(30);
    v_edition VARCHAR(100);
    v_effective_date DATE;
    v_is_verified BOOLEAN;
    v_default_currency CHAR(3);
    v_expected_basis VARCHAR(30);
BEGIN
    SELECT source_type, edition, effective_date, is_verified, default_currency
      INTO v_source_type, v_edition, v_effective_date, v_is_verified,
           v_default_currency
      FROM norm_sources
     WHERE source_id = NEW.source_id;

    IF NOT FOUND THEN
        RETURN NEW; -- the FK reports the missing source with its standard error
    END IF;

    IF COALESCE(NULLIF(btrim(v_edition), ''), v_effective_date::text) IS NULL THEN
        RAISE EXCEPTION 'Rate source % has no edition or effective date', NEW.source_id;
    END IF;

    v_expected_basis := CASE
        WHEN v_source_type IN ('FER','FERR','TER','TERR') THEN 'normative_base'
        WHEN v_source_type = 'COMMERCIAL' THEN 'commercial'
        WHEN v_source_type = 'DEMO' THEN 'demo'
    END;

    IF NEW.price_basis IS DISTINCT FROM v_expected_basis THEN
        RAISE EXCEPTION 'Rate price_basis % is incompatible with source type %',
            NEW.price_basis, v_source_type;
    END IF;

    IF NEW.is_active
       AND v_source_type IN ('FER','FERR','TER','TERR','COMMERCIAL')
       AND NOT v_is_verified THEN
        RAISE EXCEPTION 'Active rate requires a verified normative/commercial source';
    END IF;

    IF v_default_currency IS NOT NULL
       AND NEW.currency IS DISTINCT FROM v_default_currency THEN
        RAISE EXCEPTION 'Rate currency % differs from source currency %',
            NEW.currency, v_default_currency;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_rate_source
BEFORE INSERT OR UPDATE OF source_id, price_basis, currency, is_active ON rates
FOR EACH ROW EXECUTE FUNCTION fixrate_validate_rate_source();

-- Canonical immutable snapshot used when an estimate item accepts a catalog
-- rate. The function returns only stored facts; it does not invent missing data.
CREATE OR REPLACE FUNCTION fixrate_rate_snapshot(p_rate_id UUID)
RETURNS JSONB LANGUAGE sql STABLE STRICT AS $$
    SELECT jsonb_build_object(
        'origin', CASE
            WHEN s.source_type IN ('FER','FERR','TER','TERR') THEN 'normative'
            WHEN s.source_type = 'COMMERCIAL' THEN 'commercial'
            ELSE 'demo'
        END,
        'source_id', s.source_id,
        'source_series_id', s.source_series_id,
        'source_type', s.source_type,
        'source_title', s.title,
        'source_version', COALESCE(NULLIF(btrim(s.edition), ''), s.effective_date::text),
        'source_region', s.region,
        'provider_name', s.provider_name,
        'publication_date', s.publication_date,
        'effective_date', s.effective_date,
        'valid_to', s.valid_to,
        'document_reference', s.document_reference,
        'source_url', s.source_url,
        'is_verified', s.is_verified,
        'rate_id', r.rate_id,
        'rate_code', r.rate_code,
        'work_name', r.work_name,
        'unit_code', r.unit_code,
        'rate_unit_multiplier', r.rate_unit_multiplier,
        'base_price', r.base_price,
        'currency', r.currency,
        'price_basis', r.price_basis,
        'price_date', COALESCE(r.price_date, s.effective_date, s.publication_date),
        'cost_scope', r.cost_scope
    )
      FROM rates r
      JOIN norm_sources s ON s.source_id = r.source_id
     WHERE r.rate_id = p_rate_id;
$$;

-- Valid items must carry either the canonical catalog snapshot or an explicit
-- manual-price audit trail. NOT VALID preserves legacy rows while enforcing the
-- rule for every new or changed row.
ALTER TABLE estimate_items
    ADD CONSTRAINT chk_item_source_snapshot_complete CHECK (
        validation_status <> 'valid' OR (
            source_snapshot IS NOT NULL
            AND jsonb_typeof(source_snapshot) = 'object'
            AND source_snapshot ? 'origin'
            AND (
                (
                    rate_id IS NOT NULL
                    AND COALESCE(source_snapshot ->> 'origin', '')
                        IN ('normative','commercial','demo')
                    AND COALESCE(source_snapshot ->> 'rate_id', '') = rate_id::text
                    AND COALESCE(length(btrim(source_snapshot ->> 'source_id')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'source_series_id')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'source_type')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'source_title')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'source_version')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'rate_code')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'work_name')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'unit_code')), 0) > 0
                    AND COALESCE(
                        (source_snapshot ->> 'rate_unit_multiplier')::NUMERIC, -1
                    ) > 0
                    AND COALESCE((source_snapshot ->> 'base_price')::NUMERIC, -1) >= 0
                    AND COALESCE(source_snapshot ->> 'currency', '') ~ '^[A-Z]{3}$'
                    AND COALESCE(length(btrim(source_snapshot ->> 'price_basis')), 0) > 0
                )
                OR (
                    rate_id IS NULL
                    AND COALESCE(source_snapshot ->> 'origin', '') = 'manual'
                    AND COALESCE(length(btrim(source_snapshot ->> 'source_description')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'entered_by')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'basis')), 0) > 0
                    AND COALESCE(length(btrim(source_snapshot ->> 'unit_code')), 0) > 0
                    AND COALESCE((source_snapshot ->> 'unit_price')::NUMERIC, -1) >= 0
                    AND COALESCE(source_snapshot ->> 'currency', '') ~ '^[A-Z]{3}$'
                )
            )
        )
    ) NOT VALID;

-- Validate provenance, unit compatibility, currency and the deterministic
-- quantity × price × coefficient / normative-unit formula before accepting a
-- line as valid. Totals including extra materials remain covered by the v3.1
-- chk_item_valid_math constraint.
CREATE OR REPLACE FUNCTION fixrate_validate_estimate_item_provenance()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_estimate_currency CHAR(3);
    v_rate rates%ROWTYPE;
    v_source norm_sources%ROWTYPE;
    v_expected_origin TEXT;
    v_expected_base_cost NUMERIC(18,2);
BEGIN
    IF NEW.validation_status <> 'valid' THEN
        RETURN NEW;
    END IF;

    SELECT currency INTO v_estimate_currency
      FROM estimates WHERE estimate_id = NEW.estimate_id;

    IF NEW.rate_id IS NULL THEN
        IF NEW.source_snapshot ->> 'origin' IS DISTINCT FROM 'manual' THEN
            RAISE EXCEPTION 'Manual estimate item requires origin=manual';
        END IF;
        IF COALESCE(length(btrim(NEW.source_snapshot ->> 'source_description')), 0) = 0
           OR COALESCE(length(btrim(NEW.source_snapshot ->> 'entered_by')), 0) = 0
           OR COALESCE(length(btrim(NEW.source_snapshot ->> 'basis')), 0) = 0 THEN
            RAISE EXCEPTION 'Manual estimate item requires documented price provenance';
        END IF;
        IF NEW.source_snapshot ->> 'unit_code' IS DISTINCT FROM NEW.unit_code
           OR (NEW.source_snapshot ->> 'unit_price')::NUMERIC IS DISTINCT FROM NEW.unit_price
           OR NEW.source_snapshot ->> 'currency' IS DISTINCT FROM btrim(v_estimate_currency) THEN
            RAISE EXCEPTION 'Manual price snapshot differs from estimate item';
        END IF;
        v_expected_base_cost := round(
            NEW.quantity * NEW.unit_price * NEW.coefficient, 2
        );
    ELSE
        SELECT * INTO v_rate FROM rates WHERE rate_id = NEW.rate_id;
        SELECT * INTO v_source FROM norm_sources WHERE source_id = v_rate.source_id;

        v_expected_origin := CASE
            WHEN v_source.source_type IN ('FER','FERR','TER','TERR') THEN 'normative'
            WHEN v_source.source_type = 'COMMERCIAL' THEN 'commercial'
            ELSE 'demo'
        END;

        IF NEW.source_snapshot ->> 'origin' IS DISTINCT FROM v_expected_origin
           OR NEW.source_snapshot ->> 'source_id' IS DISTINCT FROM v_source.source_id::text
           OR NEW.source_snapshot ->> 'source_series_id' IS DISTINCT FROM v_source.source_series_id::text
           OR NEW.source_snapshot ->> 'source_type' IS DISTINCT FROM v_source.source_type
           OR NEW.source_snapshot ->> 'source_title' IS DISTINCT FROM v_source.title
           OR NEW.source_snapshot ->> 'source_version' IS DISTINCT FROM
                COALESCE(NULLIF(btrim(v_source.edition), ''), v_source.effective_date::text)
           OR NEW.source_snapshot ->> 'source_region' IS DISTINCT FROM v_source.region
           OR NEW.source_snapshot ->> 'provider_name' IS DISTINCT FROM v_source.provider_name
           OR NEW.source_snapshot ->> 'publication_date' IS DISTINCT FROM v_source.publication_date::text
           OR NEW.source_snapshot ->> 'effective_date' IS DISTINCT FROM v_source.effective_date::text
           OR NEW.source_snapshot ->> 'valid_to' IS DISTINCT FROM v_source.valid_to::text
           OR NEW.source_snapshot ->> 'document_reference' IS DISTINCT FROM v_source.document_reference
           OR NEW.source_snapshot ->> 'source_url' IS DISTINCT FROM v_source.source_url
           OR NEW.source_snapshot ->> 'is_verified' IS DISTINCT FROM v_source.is_verified::text
           OR NEW.source_snapshot ->> 'rate_id' IS DISTINCT FROM v_rate.rate_id::text
           OR NEW.source_snapshot ->> 'rate_code' IS DISTINCT FROM v_rate.rate_code
           OR NEW.source_snapshot ->> 'work_name' IS DISTINCT FROM v_rate.work_name
           OR NEW.source_snapshot ->> 'unit_code' IS DISTINCT FROM v_rate.unit_code
           OR (NEW.source_snapshot ->> 'rate_unit_multiplier')::NUMERIC IS DISTINCT FROM v_rate.rate_unit_multiplier
           OR (NEW.source_snapshot ->> 'base_price')::NUMERIC IS DISTINCT FROM v_rate.base_price
           OR NEW.source_snapshot ->> 'currency' IS DISTINCT FROM btrim(v_rate.currency)
           OR NEW.source_snapshot ->> 'price_basis' IS DISTINCT FROM v_rate.price_basis
           OR NEW.source_snapshot ->> 'price_date' IS DISTINCT FROM
                COALESCE(v_rate.price_date, v_source.effective_date, v_source.publication_date)::text
           OR NEW.source_snapshot ->> 'cost_scope' IS DISTINCT FROM v_rate.cost_scope THEN
            RAISE EXCEPTION 'Catalog price snapshot differs from selected rate/source';
        END IF;

        IF NEW.unit_code IS DISTINCT FROM v_rate.unit_code
           OR NEW.unit_price IS DISTINCT FROM v_rate.base_price
           OR btrim(v_estimate_currency) IS DISTINCT FROM btrim(v_rate.currency) THEN
            RAISE EXCEPTION 'Estimate item unit/price/currency is incompatible with rate';
        END IF;

        v_expected_base_cost := round(
            NEW.quantity * NEW.unit_price * NEW.coefficient
            / v_rate.rate_unit_multiplier, 2
        );
    END IF;

    IF NEW.base_cost IS DISTINCT FROM v_expected_base_cost THEN
        RAISE EXCEPTION 'Invalid base_cost: expected %, got %',
            v_expected_base_cost, NEW.base_cost;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_estimate_item_provenance
BEFORE INSERT OR UPDATE OF rate_id, quantity, unit_code, unit_price, coefficient,
    base_cost, validation_status, source_snapshot ON estimate_items
FOR EACH ROW EXECUTE FUNCTION fixrate_validate_estimate_item_provenance();

-- Approval also reconciles item.additional_materials_cost with only the
-- material rows explicitly marked as additional. included_in_rate and
-- informational rows therefore cannot be counted a second time.
CREATE OR REPLACE FUNCTION fixrate_check_approval()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_item_count BIGINT;
    v_invalid_count BIGINT;
    v_material_mismatch_count BIGINT;
    v_items_total NUMERIC(20,2);
BEGIN
    IF NEW.status = 'approved' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'approved') THEN
        SELECT count(*), count(*) FILTER (WHERE validation_status <> 'valid'),
               COALESCE(sum(total_cost), 0)::NUMERIC(20,2)
          INTO v_item_count, v_invalid_count, v_items_total
          FROM estimate_items WHERE estimate_id = NEW.estimate_id;

        SELECT count(*) INTO v_material_mismatch_count
          FROM estimate_items i
         WHERE i.estimate_id = NEW.estimate_id
           AND COALESCE(i.additional_materials_cost, 0) <> COALESCE((
               SELECT sum(m.total_cost)
                 FROM estimate_materials m
                WHERE m.item_id = i.item_id
                  AND m.cost_treatment = 'additional'
           ), 0);

        IF v_item_count = 0 OR v_invalid_count > 0 THEN
            RAISE EXCEPTION 'Cannot approve estimate: no items or unvalidated items';
        END IF;
        IF v_material_mismatch_count > 0 THEN
            RAISE EXCEPTION 'Cannot approve estimate: additional material totals do not match';
        END IF;
        IF NEW.total_cost IS NULL OR NEW.total_cost <> v_items_total THEN
            RAISE EXCEPTION 'Cannot approve estimate: expected total %, got %',
                v_items_total, NEW.total_cost;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON COLUMN norm_sources.source_series_id IS
    'Stable family identifier shared by immutable editions of one source.';
COMMENT ON COLUMN norm_sources.supersedes_source_id IS
    'Previous edition in the same source series.';
COMMENT ON COLUMN norm_sources.is_current IS
    'Explicit recommended edition; at most one current row per source series.';
COMMENT ON COLUMN norm_sources.valid_to IS
    'Inclusive end of the source applicability period when known.';
COMMENT ON COLUMN rates.price_date IS
    'Price base/period date; falls back to source dates when NULL.';
COMMENT ON FUNCTION fixrate_rate_snapshot(UUID) IS
    'Canonical provenance snapshot for a catalog rate used in an estimate item.';

COMMIT;
