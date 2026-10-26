-- Behavioural test for db/003_normative_source_versions.sql.
-- Run after 001_init.sql + 003_normative_source_versions.sql.
-- Every test record is rolled back.

BEGIN;

DO $test$
DECLARE
    v_series UUID := '90000000-0000-4000-8000-000000000001';
    v_commercial_series UUID := '90000000-0000-4000-8000-000000000002';
    v_snapshot JSONB;
    v_price NUMERIC(18,4);
    v_count INTEGER;
BEGIN
    INSERT INTO users(user_id, full_name, email, role) VALUES
        ('90000000-0000-4000-8000-000000000010', 'Norm Test Operator', 'norm.operator@example.test', 'operator'),
        ('90000000-0000-4000-8000-000000000011', 'Norm Test Estimator', 'norm.estimator@example.test', 'estimator');
    INSERT INTO buildings(building_id, address)
    VALUES ('90000000-0000-4000-8000-000000000012', 'Norm test building');
    INSERT INTO repair_requests(request_id, building_id, created_by, title)
    VALUES (
        '90000000-0000-4000-8000-000000000013',
        '90000000-0000-4000-8000-000000000012',
        '90000000-0000-4000-8000-000000000010',
        'Normative history test'
    );

    -- Two immutable editions of one normative series. Only v2 is recommended.
    INSERT INTO norm_sources(
        source_id, source_series_id, source_type, title, edition, region,
        publication_date, effective_date, valid_to, document_reference,
        is_verified, is_current
    ) VALUES (
        '90000000-0000-4000-8000-000000000020', v_series, 'TERR',
        'ТЕРр test collection', '2025.1', 'Свердловская область',
        DATE '2025-01-10', DATE '2025-02-01', DATE '2025-12-31',
        'TEST-TERR-2025.1', TRUE, FALSE
    );
    INSERT INTO rates(
        rate_id, source_id, rate_code, work_name, description, unit_code,
        rate_unit_multiplier, base_price, currency, price_basis, price_date,
        cost_scope, is_active
    ) VALUES (
        '90000000-0000-4000-8000-000000000021',
        '90000000-0000-4000-8000-000000000020',
        'TERR-TEST-001', 'Repair 100 square metres', 'Normative unit test',
        'm2', 100, 1000.0000, 'RUB', 'normative_base', DATE '2025-01-01',
        'work_only', TRUE
    );

    INSERT INTO norm_sources(
        source_id, source_series_id, supersedes_source_id, source_type,
        title, edition, region, publication_date, effective_date,
        document_reference, is_verified, is_current
    ) VALUES (
        '90000000-0000-4000-8000-000000000022', v_series,
        '90000000-0000-4000-8000-000000000020', 'TERR',
        'ТЕРр test collection', '2026.1', 'Свердловская область',
        DATE '2026-01-10', DATE '2026-02-01', 'TEST-TERR-2026.1', TRUE, TRUE
    );
    INSERT INTO rates(
        rate_id, source_id, rate_code, work_name, unit_code,
        rate_unit_multiplier, base_price, currency, price_basis, price_date,
        cost_scope, is_active
    ) VALUES (
        '90000000-0000-4000-8000-000000000023',
        '90000000-0000-4000-8000-000000000022',
        'TERR-TEST-001', 'Repair 100 square metres', 'm2',
        100, 1400.0000, 'RUB', 'normative_base', DATE '2026-01-01',
        'work_only', TRUE
    );

    SELECT count(*) INTO v_count
      FROM rates r JOIN norm_sources s USING (source_id)
     WHERE r.rate_code = 'TERR-TEST-001'
       AND s.region = 'Свердловская область'
       AND s.source_type = 'TERR';
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'Expected two searchable normative editions, got %', v_count;
    END IF;

    SELECT count(*) INTO v_count
      FROM rates r JOIN norm_sources s USING (source_id)
     WHERE s.source_series_id = v_series AND s.is_current;
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'Expected exactly one current edition, got %', v_count;
    END IF;

    -- A commercial list uses the same series/revision mechanism.
    INSERT INTO norm_sources(
        source_id, source_series_id, source_type, title, edition, provider_name,
        region, effective_date, valid_to, default_currency, source_url,
        is_verified, is_current
    ) VALUES (
        '90000000-0000-4000-8000-000000000030', v_commercial_series,
        'COMMERCIAL', 'Supplier test price list', '2025-09', 'Test Supplier',
        'Свердловская область', DATE '2025-09-01', DATE '2025-12-31', 'RUB',
        'https://example.test/prices/2025-09', TRUE, FALSE
    );
    INSERT INTO norm_sources(
        source_id, source_series_id, supersedes_source_id, source_type, title,
        edition, provider_name, region, effective_date, default_currency,
        source_url, is_verified, is_current
    ) VALUES (
        '90000000-0000-4000-8000-000000000031', v_commercial_series,
        '90000000-0000-4000-8000-000000000030', 'COMMERCIAL',
        'Supplier test price list', '2026-01', 'Test Supplier',
        'Свердловская область', DATE '2026-01-01', 'RUB',
        'https://example.test/prices/2026-01', TRUE, TRUE
    );
    INSERT INTO rates(
        source_id, rate_code, work_name, unit_code, rate_unit_multiplier,
        base_price, currency, price_basis, price_date, cost_scope
    ) VALUES
        ('90000000-0000-4000-8000-000000000030', 'SUP-001', 'Commercial work',
         'h', 1, 500, 'RUB', 'commercial', DATE '2025-09-01', 'work_only'),
        ('90000000-0000-4000-8000-000000000031', 'SUP-001', 'Commercial work',
         'h', 1, 650, 'RUB', 'commercial', DATE '2026-01-01', 'work_only');

    -- 250 m2 × 1000 RUB × 1.1 / 100 m2 = 2750 RUB.
    INSERT INTO estimates(estimate_id, request_id, version, total_cost, currency)
    VALUES (
        '90000000-0000-4000-8000-000000000040',
        '90000000-0000-4000-8000-000000000013', 1, 2750.00, 'RUB'
    );
    INSERT INTO estimate_items(
        item_id, estimate_id, request_id, rate_id, work_name, quantity,
        unit_code, unit_price, coefficient, base_cost,
        additional_materials_cost, total_cost, calculation_details,
        validation_status, source_snapshot
    ) VALUES (
        '90000000-0000-4000-8000-000000000041',
        '90000000-0000-4000-8000-000000000040',
        '90000000-0000-4000-8000-000000000013',
        '90000000-0000-4000-8000-000000000021',
        'Repair 100 square metres', 250, 'm2', 1000, 1.1, 2750, 0, 2750,
        '{"formula":"quantity * unit_price * coefficient / rate_unit_multiplier"}'::jsonb,
        'valid', fixrate_rate_snapshot('90000000-0000-4000-8000-000000000021')
    );
    UPDATE estimates
       SET status = 'approved',
           reviewed_by = '90000000-0000-4000-8000-000000000011',
           reviewed_at = now()
     WHERE estimate_id = '90000000-0000-4000-8000-000000000040';

    -- Even a later catalog correction cannot rewrite the accepted line/snapshot.
    UPDATE rates SET base_price = 1100
     WHERE rate_id = '90000000-0000-4000-8000-000000000021';
    SELECT unit_price, source_snapshot INTO v_price, v_snapshot
      FROM estimate_items
     WHERE item_id = '90000000-0000-4000-8000-000000000041';
    IF v_price <> 1000 OR (v_snapshot ->> 'base_price')::NUMERIC <> 1000
       OR v_snapshot ->> 'source_version' <> '2025.1' THEN
        RAISE EXCEPTION 'Historical estimate price/source snapshot changed';
    END IF;

    -- A documented manual price remains possible without a catalog rate.
    INSERT INTO estimates(estimate_id, request_id, version, total_cost, currency)
    VALUES (
        '90000000-0000-4000-8000-000000000042',
        '90000000-0000-4000-8000-000000000013', 2, 500.00, 'RUB'
    );
    INSERT INTO estimate_items(
        estimate_id, request_id, work_name, quantity, unit_code, unit_price,
        coefficient, base_cost, total_cost, validation_status, source_snapshot
    ) VALUES (
        '90000000-0000-4000-8000-000000000042',
        '90000000-0000-4000-8000-000000000013', 'Manual inspection',
        2, 'h', 250, 1, 500, 500, 'valid',
        '{"origin":"manual","source_description":"Supplier quotation #42","entered_by":"90000000-0000-4000-8000-000000000011","basis":"Written quotation dated 2026-10-22","unit_code":"h","unit_price":250,"currency":"RUB"}'::jsonb
    );

    -- Negative: manual origin alone is insufficient without documented provenance.
    BEGIN
        INSERT INTO estimate_items(
            estimate_id, request_id, work_name, quantity, unit_code, unit_price,
            coefficient, base_cost, total_cost, validation_status, source_snapshot
        ) VALUES (
            '90000000-0000-4000-8000-000000000042',
            '90000000-0000-4000-8000-000000000013', 'Undocumented manual price',
            1, 'h', 1, 1, 1, 1, 'valid',
            '{"origin":"manual","unit_code":"h","unit_price":1,"currency":"RUB"}'::jsonb
        );
        RAISE EXCEPTION 'Expected incomplete manual provenance rejection';
    EXCEPTION
        WHEN check_violation THEN NULL;
        WHEN raise_exception THEN
            IF SQLERRM = 'Expected incomplete manual provenance rejection' THEN RAISE; END IF;
    END;

    -- Negative: a caller cannot forge descriptive fields in a catalog snapshot.
    BEGIN
        INSERT INTO estimate_items(
            estimate_id, request_id, rate_id, work_name, quantity, unit_code,
            unit_price, coefficient, base_cost, total_cost, validation_status,
            source_snapshot
        ) VALUES (
            '90000000-0000-4000-8000-000000000042',
            '90000000-0000-4000-8000-000000000013',
            '90000000-0000-4000-8000-000000000023', 'Forged snapshot',
            100, 'm2', 1400, 1, 1400, 1400, 'valid',
            jsonb_set(
                fixrate_rate_snapshot('90000000-0000-4000-8000-000000000023'),
                '{source_title}', '"Forged source"'::jsonb
            )
        );
        RAISE EXCEPTION 'Expected forged snapshot rejection';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected forged snapshot rejection' THEN RAISE; END IF;
    END;

    -- Negative: an unverified source cannot expose an active normative rate.
    BEGIN
        INSERT INTO norm_sources(
            source_id, source_type, title, edition, document_reference,
            is_verified, is_current
        ) VALUES (
            '90000000-0000-4000-8000-000000000050', 'FER',
            'Unverified FER', 'test', 'UNVERIFIED', FALSE, TRUE
        );
        INSERT INTO rates(
            source_id, rate_code, work_name, unit_code, base_price, currency,
            price_basis, cost_scope, is_active
        ) VALUES (
            '90000000-0000-4000-8000-000000000050', 'BAD-UNVERIFIED',
            'Bad normative work', 'm2', 1, 'RUB', 'normative_base',
            'work_only', TRUE
        );
        RAISE EXCEPTION 'Expected unverified active normative rate rejection';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected unverified active normative rate rejection' THEN RAISE; END IF;
    END;

    -- Negative: DEMO can never claim verified provenance.
    BEGIN
        INSERT INTO norm_sources(source_type, title, edition, document_reference, is_verified)
        VALUES ('DEMO', 'Fake verified demo', '1', 'fake', TRUE);
        RAISE EXCEPTION 'Expected verified DEMO rejection';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Negative: a series cannot have two recommended editions.
    BEGIN
        INSERT INTO norm_sources(
            source_series_id, source_type, title, edition, document_reference,
            is_verified, is_current
        ) VALUES (v_series, 'TERR', 'Duplicate current', '2027.1', 'TEST', TRUE, TRUE);
        RAISE EXCEPTION 'Expected duplicate current edition rejection';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- Negative: source type and price basis must agree.
    BEGIN
        INSERT INTO rates(
            source_id, rate_code, work_name, unit_code, base_price, currency,
            price_basis, cost_scope
        ) VALUES (
            '90000000-0000-4000-8000-000000000022', 'BAD-BASIS',
            'Commercial masquerading as normative', 'm2', 1, 'RUB',
            'commercial', 'work_only'
        );
        RAISE EXCEPTION 'Expected incompatible price_basis rejection';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected incompatible price_basis rejection' THEN RAISE; END IF;
    END;

    -- Negative: a rate cannot exist without a real source row.
    BEGIN
        INSERT INTO rates(
            source_id, rate_code, work_name, unit_code, base_price, currency,
            price_basis, cost_scope
        ) VALUES (
            '90000000-0000-4000-8000-000000000099', 'MISSING-SOURCE',
            'Orphan price', 'm2', 1, 'RUB', 'demo', 'work_only'
        );
        RAISE EXCEPTION 'Expected missing source rejection';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    -- Negative: unit and normative multiplier cannot be silently ignored.
    BEGIN
        INSERT INTO estimate_items(
            estimate_id, request_id, rate_id, work_name, quantity, unit_code,
            unit_price, coefficient, base_cost, total_cost, validation_status,
            source_snapshot
        ) VALUES (
            '90000000-0000-4000-8000-000000000042',
            '90000000-0000-4000-8000-000000000013',
            '90000000-0000-4000-8000-000000000023', 'Bad unit',
            100, 'h', 1400, 1, 1400, 1400, 'valid',
            fixrate_rate_snapshot('90000000-0000-4000-8000-000000000023')
        );
        RAISE EXCEPTION 'Expected incompatible unit rejection';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected incompatible unit rejection' THEN RAISE; END IF;
    END;

    -- Negative: a used source cannot be removed and approved lines are immutable.
    BEGIN
        DELETE FROM norm_sources
         WHERE source_id = '90000000-0000-4000-8000-000000000020';
        RAISE EXCEPTION 'Expected used source deletion rejection';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        UPDATE estimate_items SET unit_price = 999
         WHERE item_id = '90000000-0000-4000-8000-000000000041';
        RAISE EXCEPTION 'Expected approved estimate mutation rejection';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected approved estimate mutation rejection' THEN RAISE; END IF;
    END;


    -- Negative: a material already included in a rate cannot be added to the
    -- additional-material subtotal during approval.
    INSERT INTO estimates(estimate_id, request_id, version, total_cost, currency)
    VALUES (
        '90000000-0000-4000-8000-000000000043',
        '90000000-0000-4000-8000-000000000013', 3, 1500.00, 'RUB'
    );
    INSERT INTO estimate_items(
        item_id, estimate_id, request_id, rate_id, work_name, quantity,
        unit_code, unit_price, coefficient, base_cost,
        additional_materials_cost, total_cost, validation_status, source_snapshot
    ) VALUES (
        '90000000-0000-4000-8000-000000000044',
        '90000000-0000-4000-8000-000000000043',
        '90000000-0000-4000-8000-000000000013',
        '90000000-0000-4000-8000-000000000023',
        'Rate with included material', 100, 'm2', 1400, 1, 1400, 100, 1500,
        'valid', fixrate_rate_snapshot('90000000-0000-4000-8000-000000000023')
    );
    INSERT INTO estimate_materials(
        item_id, material_name, quantity, unit_code, unit_price, total_cost,
        price_snapshot, cost_treatment
    ) VALUES (
        '90000000-0000-4000-8000-000000000044', 'Already included material',
        1, 'pcs', 100, 100, '{"origin":"rate"}'::jsonb, 'included_in_rate'
    );
    BEGIN
        UPDATE estimates
           SET status = 'approved',
               reviewed_by = '90000000-0000-4000-8000-000000000011',
               reviewed_at = now()
         WHERE estimate_id = '90000000-0000-4000-8000-000000000043';
        RAISE EXCEPTION 'Expected duplicate material total rejection';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected duplicate material total rejection' THEN RAISE; END IF;
    END;

    RAISE NOTICE 'PASS: normative revisions, commercial versions, source search, canonical snapshot, historical price, manual provenance and negative guards';
END;
$test$;

ROLLBACK;
