-- Smoke/negative tests for db/001_init.sql on a clean test database.
-- Run AFTER migration. Entire test is rolled back; no demo records remain.
-- PostgreSQL 16 + pgvector required.
BEGIN;

DO $smoke$
DECLARE
    v_updated_before TIMESTAMPTZ;
    v_updated_after TIMESTAMPTZ;
    v_total NUMERIC(18,2);
BEGIN
    IF (SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE') <> 18 THEN
        RAISE EXCEPTION 'Unexpected number of tables';
    END IF;
    IF (SELECT count(*) FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace) <> 32 THEN
        RAISE EXCEPTION 'Unexpected number of foreign keys';
    END IF;

    INSERT INTO users(user_id, full_name, email, role) VALUES
      ('11111111-1111-4111-8111-111111111111', 'Demo Operator', 'smoke.operator@example.test', 'operator'),
      ('22222222-2222-4222-8222-222222222222', 'Demo Estimator', 'smoke.estimator@example.test', 'estimator');
    INSERT INTO buildings(building_id, address)
      VALUES ('33333333-3333-4333-8333-333333333333','Demo test building');
    INSERT INTO repair_requests(request_id, building_id, created_by, title, updated_at)
      VALUES ('44444444-4444-4444-8444-444444444444',
              '33333333-3333-4333-8333-333333333333',
              '11111111-1111-4111-8111-111111111111','Wall repair', now() - interval '1 day');
    SELECT updated_at INTO v_updated_before FROM repair_requests
      WHERE request_id = '44444444-4444-4444-8444-444444444444';
    UPDATE repair_requests SET title='Wall repair updated'
      WHERE request_id = '44444444-4444-4444-8444-444444444444';
    SELECT updated_at INTO v_updated_after FROM repair_requests
      WHERE request_id = '44444444-4444-4444-8444-444444444444';
    IF v_updated_after <= v_updated_before THEN
        RAISE EXCEPTION 'updated_at trigger failed';
    END IF;

    INSERT INTO estimates(estimate_id, request_id, version, total_cost)
      VALUES ('55555555-5555-4555-8555-555555555555',
              '44444444-4444-4444-8444-444444444444', 1, 200.00);

    -- A manual valid item is allowed without rate_id only with documented origin.
    INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name,
               quantity, unit_code, unit_price, base_cost,
               additional_materials_cost, total_cost, validation_status, source_snapshot)
      VALUES ('66666666-6666-4666-8666-666666666666',
              '55555555-5555-4555-8555-555555555555',
              '44444444-4444-4444-8444-444444444444','Manual wall preparation',
              2,'m2',100,200,0,200,'valid','{"origin":"manual","note":"demo"}'::jsonb);

    INSERT INTO estimate_materials(material_id,item_id,material_name,quantity,unit_code,cost_treatment)
      VALUES ('77777777-7777-4777-8777-777777777777',
              '66666666-6666-4666-8666-666666666666',
              'Primer',1,'l','informational');

    BEGIN
        INSERT INTO estimate_items(estimate_id,request_id,work_name,quantity,unit_code,
           unit_price,base_cost,total_cost,validation_status,source_snapshot)
        VALUES ('55555555-5555-4555-8555-555555555555',
                '44444444-4444-4444-8444-444444444444','Missing origin',
                1,'m2',100,100,100,'valid','{}'::jsonb);
        RAISE EXCEPTION 'Expected missing manual source snapshot failure';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO estimate_items(estimate_id,request_id,work_name,quantity,unit_code,
           unit_price,base_cost,total_cost,validation_status,source_snapshot)
        VALUES ('55555555-5555-4555-8555-555555555555',
                '44444444-4444-4444-8444-444444444444','Wrong sum',
                1,'m2',100,100,99,'valid','{"origin":"manual"}'::jsonb);
        RAISE EXCEPTION 'Expected arithmetic constraint failure';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    UPDATE estimates SET status='approved',
        reviewed_by='22222222-2222-4222-8222-222222222222',
        reviewed_at=now()
      WHERE estimate_id = '55555555-5555-4555-8555-555555555555';

    BEGIN
        UPDATE estimates SET total_cost=1
          WHERE estimate_id = '55555555-5555-4555-8555-555555555555';
        RAISE EXCEPTION 'Expected finalized estimate update to fail';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected finalized estimate update to fail' THEN RAISE; END IF;
    END;
    BEGIN
        UPDATE estimate_items SET work_name='Changed after approval'
          WHERE item_id = '66666666-6666-4666-8666-666666666666';
        RAISE EXCEPTION 'Expected finalized item update to fail';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected finalized item update to fail' THEN RAISE; END IF;
    END;
    BEGIN
        DELETE FROM estimate_materials
          WHERE material_id = '77777777-7777-4777-8777-777777777777';
        RAISE EXCEPTION 'Expected finalized material deletion to fail';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected finalized material deletion to fail' THEN RAISE; END IF;
    END;

    INSERT INTO estimates(estimate_id,request_id,version,total_cost)
       VALUES ('88888888-8888-4888-8888-888888888888',
               '44444444-4444-4444-8444-444444444444',2,100);
    INSERT INTO estimate_items(estimate_id,request_id,work_name,quantity,unit_code,
        unit_price,base_cost,total_cost,validation_status,source_snapshot)
       VALUES ('88888888-8888-4888-8888-888888888888',
               '44444444-4444-4444-8444-444444444444','Mispriced job',
               1,'m2',90,90,90,'valid','{"origin":"manual"}'::jsonb);
    BEGIN
        UPDATE estimates SET status='approved',
            reviewed_by='22222222-2222-4222-8222-222222222222',reviewed_at=now()
          WHERE estimate_id = '88888888-8888-4888-8888-888888888888';
        RAISE EXCEPTION 'Expected approval mismatch to fail';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected approval mismatch to fail' THEN RAISE; END IF;
    END;
    SELECT total_cost INTO v_total FROM estimates WHERE estimate_id='88888888-8888-4888-8888-888888888888';
    IF v_total <> 100 THEN RAISE EXCEPTION 'Estimate mutated unexpectedly'; END IF;

    -- An approved estimate cannot be inserted directly, even with a reviewer:
    -- it must go through the draft -> items -> approve lifecycle.
    BEGIN
        INSERT INTO estimates(estimate_id,request_id,version,status,total_cost,
            reviewed_by,reviewed_at)
        VALUES ('99999999-9999-4999-8999-999999999999',
                '44444444-4444-4444-8444-444444444444',3,'approved',0,
                '22222222-2222-4222-8222-222222222222',now());
        RAISE EXCEPTION 'Expected direct approved insert to fail';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected direct approved insert to fail' THEN RAISE; END IF;
    END;

    BEGIN
        INSERT INTO estimate_items(estimate_id,request_id,work_name,quantity,unit_code,
            unit_price,base_cost,total_cost,validation_status,source_snapshot)
        VALUES ('55555555-5555-4555-8555-555555555555',
                '44444444-4444-4444-8444-444444444444','Late item',
                1,'m2',10,10,10,'valid','{"origin":"manual"}'::jsonb);
        RAISE EXCEPTION 'Expected item insert into finalized estimate to fail';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected item insert into finalized estimate to fail' THEN RAISE; END IF;
    END;

    INSERT INTO audit_events(event_id,actor_type,request_id,entity_type,entity_id,action)
      VALUES ('99999999-9999-4999-8999-999999999999','system',
              '44444444-4444-4444-8444-444444444444',
              'estimates','55555555-5555-4555-8555-555555555555','approved');
    BEGIN
        DELETE FROM audit_events WHERE event_id = '99999999-9999-4999-8999-999999999999';
        RAISE EXCEPTION 'Expected audit deletion to fail';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Expected audit deletion to fail' THEN RAISE; END IF;
    END;

    RAISE NOTICE 'PASS: 18 tables, 32 FK, timestamps, manual items, approval, immutable history, audit';
END;
$smoke$;

ROLLBACK;
