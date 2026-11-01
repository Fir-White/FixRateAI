-- FixRate AI: deployment contract test for migrations 001-004.
--
-- Run only on a clean, isolated database after applying:
--   database/migrations/001_tl02.sql
--   database/migrations/002_planning_contract.sql
--   database/migrations/003_occurrence_uniqueness.sql
--   database/migrations/004_tl03_safe_constraints.sql
--
-- The script is read-only for the target schema: every fixture is rolled back.
-- It checks:
--   1. all 35 TL02 tables and the columns added by 002/004 exist;
--   2. primary keys, mandatory foreign keys, unique occurrence indexes and
--      the TL03 audit triggers are installed;
--   3. forecast history survives updates and cannot be deleted while a
--      decision references it;
--   4. mandatory relations reject incomplete or cross-site rows;
--   5. invalid statuses, ranges and duplicate business keys are rejected.
\set ON_ERROR_STOP on

BEGIN;

\echo '== 1. schema: tables, columns, keys =='
DO $$
DECLARE
    missing text;
    pk_count integer;
BEGIN
    SELECT string_agg(name, ', ') INTO missing
    FROM unnest(ARRAY[
        'sites','users','site_memberships','engineering_systems',
        'equipment_types','equipment','skills','user_skills',
        'availability_slots','crews','crew_members','maintenance_types',
        'operation_templates','regulation_documents','regulation_editions',
        'maintenance_rules','rule_equipment','rule_required_skills',
        'schedule_plans','schedule_entries','incident_reports','work_orders',
        'work_order_equipment','work_assignments','checklist_templates',
        'work_reports','checklist_results','work_readings','evidence_files',
        'acceptance_reviews','predictor_versions','forecast_runs',
        'orchestration_decisions','ai_quality_checks','audit_events'
    ]) AS name
    WHERE to_regclass('public.' || name) IS NULL;

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'missing tables: %', missing;
    END IF;

    SELECT count(*) INTO pk_count
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public' AND c.contype = 'p';

    IF pk_count <> 35 THEN
        RAISE EXCEPTION 'expected 35 primary keys, found %', pk_count;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'work_orders'
          AND column_name = 'norm_hours_snapshot'
          AND data_type = 'numeric' AND numeric_precision = 13 AND numeric_scale = 3
    ) THEN
        RAISE EXCEPTION '004 did not widen work_orders.norm_hours_snapshot to NUMERIC(13,3)';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'maintenance_rules'
          AND column_name = 'norm_hours'
          AND data_type = 'numeric' AND numeric_precision = 12 AND numeric_scale = 3
          AND is_nullable = 'YES'
    ) THEN
        RAISE EXCEPTION '002 did not make maintenance_rules.norm_hours NUMERIC(12,3) NULL';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'maintenance_rules'
          AND column_name = 'data_origin'
    ) THEN
        RAISE EXCEPTION '002 did not add maintenance_rules.data_origin';
    END IF;

    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'rule_equipment'
          AND column_name IN ('binding_id','revision','baseline_runtime_hours')) <> 3 THEN
        RAISE EXCEPTION '002 did not add all rule_equipment binding columns';
    END IF;

    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'schedule_entries'
          AND column_name IN ('binding_id','revision','earliest_date','runtime_due_at_hours')) <> 4 THEN
        RAISE EXCEPTION '002 did not add all schedule_entries planning columns';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'work_orders' AND c.conname = 'fk_work_orders_entry_rule'
          AND c.contype = 'f' AND NOT c.convalidated
    ) THEN
        RAISE EXCEPTION '004 FK fk_work_orders_entry_rule is missing or already validated';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_class r ON r.oid = c.confrelid
        WHERE t.relname = 'schedule_entries' AND r.relname = 'rule_equipment'
          AND c.contype = 'f'
    ) THEN
        RAISE EXCEPTION '002 did not add schedule_entries -> rule_equipment FK';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'schedule_entries' AND c.conname = 'uq_schedule_entries_order_rule'
    ) THEN
        RAISE EXCEPTION '004 unique (site,system,entry,rule) is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'schedule_entries_binding_occurrence'
    ) THEN
        RAISE EXCEPTION '002 binding occurrence index is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'schedule_entries_unbound_occurrence'
    ) THEN
        RAISE EXCEPTION '003 unbound occurrence index is missing';
    END IF;

    IF (SELECT count(*) FROM pg_trigger tg
        JOIN pg_class t ON t.oid = tg.tgrelid
        WHERE NOT tg.tgisinternal AND t.relname IN (
            'operation_templates','maintenance_rules','rule_equipment',
            'schedule_plans','schedule_entries')) <> 5 THEN
        RAISE EXCEPTION 'expected 5 planning audit triggers';
    END IF;
END $$;

\echo '== 2. fixtures: full history chain =='
DO $$
DECLARE
    s uuid; s2 uuid; u uuid; e uuid; sys uuid; sys2 uuid; et uuid; eq uuid;
    mt uuid; doc uuid; ed uuid; op uuid; r1 uuid; r2 uuid; r3 uuid;
    b uuid; p uuid; entry uuid; entry_unbound uuid; wo uuid; report uuid;
    f1 uuid; f2 uuid; pv_rule uuid; pv_ai uuid; pv_orch uuid;
    fr_rule uuid; fr_ai uuid; fr_other uuid; decision uuid;
BEGIN
    INSERT INTO sites(name) VALUES ('Schema test') RETURNING site_id INTO s;
    INSERT INTO sites(name) VALUES ('Other site') RETURNING site_id INTO s2;
    INSERT INTO users(full_name,email) VALUES ('Engineer','engineer@example.test') RETURNING user_id INTO u;
    INSERT INTO users(full_name,email) VALUES ('Executor','executor@example.test') RETURNING user_id INTO e;
    INSERT INTO site_memberships(site_id,user_id,role) VALUES (s,u,'engineer'), (s,e,'technician');

    INSERT INTO engineering_systems(site_id,code,name) VALUES (s,'SYS','System') RETURNING system_id INTO sys;
    INSERT INTO engineering_systems(site_id,code,name) VALUES (s2,'SYS2','Other system') RETURNING system_id INTO sys2;

    INSERT INTO equipment_types(code,name) VALUES ('PUMP','Pump') RETURNING equipment_type_id INTO et;
    INSERT INTO equipment(site_id,system_id,equipment_type_id,asset_code,name)
        VALUES (s,sys,et,'A-1','Pump 1') RETURNING equipment_id INTO eq;

    INSERT INTO maintenance_types(code,name) VALUES ('TO1','TO1') RETURNING maintenance_type_id INTO mt;
    INSERT INTO regulation_documents(site_id,title) VALUES (s,'Regulation') RETURNING regulation_document_id INTO doc;
    INSERT INTO regulation_editions(site_id,regulation_document_id,edition_code,effective_from,is_approved,approved_by)
        VALUES (s,doc,'v1','2026-01-01',true,u) RETURNING regulation_edition_id INTO ed;
    INSERT INTO operation_templates(site_id,system_id,code,title,maintenance_type_id)
        VALUES (s,sys,'OP1','Operation',mt) RETURNING operation_template_id INTO op;

    INSERT INTO maintenance_rules(
        site_id,system_id,operation_template_id,regulation_edition_id,
        period_unit,scheduling_mode,source_text,source_ref,
        required_people,norm_hours,active_from)
    VALUES (s,sys,op,ed,'month','fixed_interval','1/month','sheet!A1',1,1.125,'2026-01-01')
    RETURNING maintenance_rule_id INTO r1;

    INSERT INTO maintenance_rules(
        site_id,system_id,operation_template_id,regulation_edition_id,rule_version,
        period_unit,scheduling_mode,source_text,source_ref,
        required_people,norm_hours,active_from)
    VALUES (s,sys,op,ed,2,'month','fixed_interval','1/month','sheet!A1',1,1.125,'2026-01-01')
    RETURNING maintenance_rule_id INTO r2;

    INSERT INTO maintenance_rules(
        site_id,system_id,operation_template_id,regulation_edition_id,rule_version,
        period_unit,scheduling_mode,source_text,source_ref,
        required_people,norm_hours,active_from)
    VALUES (s,sys,op,ed,3,'month','fixed_interval','1/month','sheet!A1',1,1.125,'2026-01-01')
    RETURNING maintenance_rule_id INTO r3;

    INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from)
        VALUES (s,sys,r1,eq,'2026-01-01') RETURNING binding_id INTO b;

    INSERT INTO schedule_plans(site_id,period_year,period_month,created_by)
        VALUES (s,2026,10,u) RETURNING schedule_plan_id INTO p;

    INSERT INTO schedule_entries(
        site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,
        planned_date,regulatory_deadline_on,regulatory_deadline_at,earliest_date)
    VALUES (s,sys,p,r1,b,'2026-10-05','2026-10-05','2026-10-05 23:59+05','2026-10-01')
    RETURNING schedule_entry_id INTO entry;

    INSERT INTO schedule_entries(
        site_id,system_id,schedule_plan_id,maintenance_rule_id,
        planned_date,regulatory_deadline_on,regulatory_deadline_at)
    VALUES (s,sys,p,r1,'2026-10-06','2026-10-06','2026-10-06 23:59+05')
    RETURNING schedule_entry_id INTO entry_unbound;

    INSERT INTO work_orders(
        site_id,system_id,maintenance_rule_id,schedule_entry_id,
        required_people_snapshot,norm_hours_snapshot,created_by)
    VALUES (s,sys,r1,entry,1,1.125,u) RETURNING work_order_id INTO wo;

    INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
        VALUES (s,sys,wo,eq);

    INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
        VALUES (s,wo,e,u);

    INSERT INTO work_reports(site_id,work_order_id,submitted_by,status,submitted_at)
        VALUES (s,wo,e,'submitted',now()) RETURNING work_report_id INTO report;

    INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision)
        VALUES (s,wo,report,u,'accepted');

    INSERT INTO evidence_files(
        site_id,work_order_id,work_report_id,uploaded_by,stage,storage_key,
        mime_type,file_size,sha256)
    VALUES (s,wo,report,e,'before','schema/before.jpg','image/jpeg',100,repeat('a',64))
    RETURNING evidence_file_id INTO f1;

    INSERT INTO evidence_files(
        site_id,work_order_id,work_report_id,uploaded_by,stage,storage_key,
        mime_type,file_size,sha256)
    VALUES (s,wo,report,e,'after','schema/after.jpg','image/jpeg',120,repeat('b',64))
    RETURNING evidence_file_id INTO f2;

    INSERT INTO predictor_versions(kind,name,version) VALUES ('rule','rule','1') RETURNING predictor_version_id INTO pv_rule;
    INSERT INTO predictor_versions(kind,name,version) VALUES ('ai','ai','1') RETURNING predictor_version_id INTO pv_ai;
    INSERT INTO predictor_versions(kind,name,version) VALUES ('orchestrator','orchestrator','1') RETURNING predictor_version_id INTO pv_orch;

    INSERT INTO forecast_runs(
        site_id,system_id,maintenance_rule_id,equipment_id,predictor_version_id,
        method,status,input_snapshot,proposal_at,regulatory_deadline_at,confidence)
    VALUES (s,sys,r1,eq,pv_rule,'rule','ok','{}','2026-10-01 08:00+05','2026-10-05 23:59+05',0.9)
    RETURNING forecast_run_id INTO fr_rule;

    INSERT INTO forecast_runs(
        site_id,system_id,maintenance_rule_id,equipment_id,predictor_version_id,
        method,status,input_snapshot,proposal_at,regulatory_deadline_at)
    VALUES (s,sys,r1,eq,pv_ai,'ai','unavailable','{}',NULL,'2026-10-05 23:59+05')
    RETURNING forecast_run_id INTO fr_ai;

    INSERT INTO forecast_runs(
        site_id,system_id,maintenance_rule_id,equipment_id,predictor_version_id,
        method,status,input_snapshot,proposal_at,regulatory_deadline_at)
    VALUES (s,sys,r3,eq,pv_rule,'rule','ok','{}','2026-10-02 08:00+05','2026-10-06 23:59+05')
    RETURNING forecast_run_id INTO fr_other;

    INSERT INTO orchestration_decisions(
        site_id,system_id,maintenance_rule_id,rule_forecast_id,ai_forecast_id,
        orchestrator_version_id,selected_method,selected_at,regulatory_deadline_at,reason)
    VALUES (s,sys,r1,fr_rule,fr_ai,pv_orch,'rule','2026-10-01 09:00+05','2026-10-05 23:59+05','rule within deadline')
    RETURNING orchestration_decision_id INTO decision;

    INSERT INTO ai_quality_checks(
        site_id,work_order_id,work_report_id,before_file_id,after_file_id,
        predictor_version_id,status,visible_change,assessment,confidence)
    VALUES (s,wo,report,f1,f2,pv_ai,'ok','visible','consistent',0.8);

    -- The old NUMERIC(12,2) integer range must still fit after the 004 widening.
    UPDATE work_orders SET norm_hours_snapshot = 9999999999.99 WHERE work_order_id = wo;
    IF (SELECT norm_hours_snapshot FROM work_orders WHERE work_order_id = wo) <> 9999999999.990 THEN
        RAISE EXCEPTION '004 lost the former NUMERIC(12,2) integer range';
    END IF;
    UPDATE work_orders SET norm_hours_snapshot = 1.125 WHERE work_order_id = wo;

    -- History is preserved: the update is recorded with both snapshots, while
    -- the forecast run keeps pointing at the same rule row.
    UPDATE maintenance_rules SET norm_hours = 2.500 WHERE maintenance_rule_id = r1;

    IF NOT EXISTS (
        SELECT 1 FROM audit_events
        WHERE entity_type = 'maintenance_rules' AND entity_id = r1
          AND action = 'update'
          AND before_snapshot->>'norm_hours' = '1.125'
          AND after_snapshot->>'norm_hours' = '2.500'
    ) THEN
        RAISE EXCEPTION 'planning audit trigger did not preserve the rule history';
    END IF;

    IF (SELECT count(*) FROM forecast_runs WHERE maintenance_rule_id = r1) <> 2 THEN
        RAISE EXCEPTION 'forecast history rows were lost';
    END IF;

    IF (SELECT count(*) FROM orchestration_decisions WHERE maintenance_rule_id = r1) <> 1 THEN
        RAISE EXCEPTION 'orchestration history row was lost';
    END IF;

    -- Mandatory relations: incomplete scheduled and incident orders are rejected.
    BEGIN
        INSERT INTO work_orders(site_id,system_id,origin,required_people_snapshot,norm_hours_snapshot)
        VALUES (s,sys,'scheduled',1,1);
        RAISE EXCEPTION 'scheduled order without entry/rule was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO work_orders(site_id,system_id,origin,required_people_snapshot,norm_hours_snapshot)
        VALUES (s,sys,'incident',1,1);
        RAISE EXCEPTION 'incident order without incident report was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO schedule_entries(
            site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,
            planned_date,regulatory_deadline_on,regulatory_deadline_at)
        VALUES (s,sys,p,r1,gen_random_uuid(),'2026-10-07','2026-10-07','2026-10-07 23:59+05');
        RAISE EXCEPTION 'schedule entry with unknown binding was accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        UPDATE work_orders SET maintenance_rule_id = r2 WHERE work_order_id = wo;
        RAISE EXCEPTION 'work order and schedule entry rule mismatch was accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    IF (SELECT maintenance_rule_id FROM work_orders WHERE work_order_id = wo) <> r1 THEN
        RAISE EXCEPTION 'failed mismatch update changed the work order';
    END IF;

    BEGIN
        INSERT INTO equipment(site_id,system_id,asset_code,name)
        VALUES (s2,sys,'CROSS-1','Cross-site pump');
        RAISE EXCEPTION 'cross-site equipment reference was accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    -- Invalid statuses and ranges are rejected.
    BEGIN
        INSERT INTO equipment(site_id,system_id,asset_code,name,status)
        VALUES (s,sys,'BAD-1','Bad status','broken');
        RAISE EXCEPTION 'invalid equipment status was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        UPDATE work_orders SET status = 'approved' WHERE work_order_id = wo;
        RAISE EXCEPTION 'invalid work order status was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        UPDATE work_reports SET status = 'accepted' WHERE work_report_id = report;
        RAISE EXCEPTION 'invalid report status was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        UPDATE schedule_plans SET status = 'published' WHERE schedule_plan_id = p;
        RAISE EXCEPTION 'invalid plan status was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        UPDATE work_assignments SET status = 'approved' WHERE work_order_id = wo;
        RAISE EXCEPTION 'invalid assignment status was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO forecast_runs(
            site_id,system_id,maintenance_rule_id,predictor_version_id,
            method,status,input_snapshot,regulatory_deadline_at)
        VALUES (s,sys,r1,pv_ai,'ai','needs_input','{}','2026-10-05 23:59+05');
        RAISE EXCEPTION 'invalid forecast status was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        UPDATE forecast_runs SET proposal_at = NULL WHERE forecast_run_id = fr_rule;
        RAISE EXCEPTION 'ok forecast without proposal date was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        UPDATE forecast_runs SET confidence = 1.5 WHERE forecast_run_id = fr_rule;
        RAISE EXCEPTION 'confidence outside [0,1] was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        UPDATE orchestration_decisions SET selected_method = 'manual_review'
        WHERE orchestration_decision_id = decision;
        RAISE EXCEPTION 'manual_review with selected_at was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO orchestration_decisions(
            site_id,system_id,maintenance_rule_id,rule_forecast_id,ai_forecast_id,
            orchestrator_version_id,selected_method,selected_at,regulatory_deadline_at,reason)
        VALUES (s,sys,r1,fr_rule,fr_ai,pv_orch,'rule',NULL,'2026-10-05 23:59+05','missing date');
        RAISE EXCEPTION 'selected method without date was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO orchestration_decisions(
            site_id,system_id,maintenance_rule_id,rule_forecast_id,ai_forecast_id,
            orchestrator_version_id,selected_method,selected_at,regulatory_deadline_at,reason)
        VALUES (s,sys,r1,fr_rule,fr_other,pv_orch,'rule','2026-10-01 09:00+05','2026-10-05 23:59+05','foreign forecast');
        RAISE EXCEPTION 'decision accepted a forecast from another rule';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision)
        VALUES (s,wo,report,u,'ok');
        RAISE EXCEPTION 'invalid acceptance decision was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision)
        VALUES (s,wo,report,u,'accepted');
        RAISE EXCEPTION 'second acceptance for the same report was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO work_reports(site_id,work_order_id,revision_no,submitted_by)
        VALUES (s,wo,1,e);
        RAISE EXCEPTION 'duplicate report revision was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO evidence_files(
            site_id,work_order_id,uploaded_by,stage,storage_key,mime_type,file_size,sha256)
        VALUES (s,wo,e,'during','schema/bad.jpg','image/jpeg',10,repeat('c',64));
        RAISE EXCEPTION 'invalid evidence stage was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO evidence_files(
            site_id,work_order_id,uploaded_by,stage,storage_key,mime_type,file_size,sha256)
        VALUES (s,wo,e,'before','schema/bad.jpg','image/gif',10,repeat('c',64));
        RAISE EXCEPTION 'invalid evidence MIME type was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO evidence_files(
            site_id,work_order_id,uploaded_by,stage,storage_key,mime_type,file_size,sha256)
        VALUES (s,wo,e,'before','schema/bad-hash.jpg','image/jpeg',10,'not-a-hash');
        RAISE EXCEPTION 'invalid evidence hash was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO audit_events(site_id,actor_type,entity_type,entity_id,action)
        VALUES (s,'user','work_orders',wo,'update');
        RAISE EXCEPTION 'user audit event without actor id was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO ai_quality_checks(
            site_id,work_order_id,predictor_version_id,status,assessment)
        VALUES (s,wo,pv_ai,'approved','consistent');
        RAISE EXCEPTION 'invalid AI quality status was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO schedule_entries(
            site_id,system_id,schedule_plan_id,maintenance_rule_id,
            planned_date,regulatory_deadline_on,regulatory_deadline_at)
        VALUES (s,sys,p,r1,'2026-10-06','2026-10-06','2026-10-06 23:59+05');
        RAISE EXCEPTION 'duplicate unbound occurrence was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO work_orders(
            site_id,system_id,maintenance_rule_id,schedule_entry_id,
            required_people_snapshot,norm_hours_snapshot)
        VALUES (s,sys,r1,entry,1,1);
        RAISE EXCEPTION 'second work order for the same occurrence was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- Referenced history cannot be deleted.
    BEGIN
        DELETE FROM forecast_runs WHERE forecast_run_id = fr_rule;
        RAISE EXCEPTION 'forecast referenced by a decision was deleted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        DELETE FROM work_orders WHERE work_order_id = wo;
        RAISE EXCEPTION 'work order with report was deleted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        DELETE FROM maintenance_rules WHERE maintenance_rule_id = r1;
        RAISE EXCEPTION 'rule with schedule history was deleted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    -- Final invariants: no fixture was lost or duplicated by the negative runs.
    IF (SELECT count(*) FROM work_orders WHERE work_order_id = wo) <> 1 THEN
        RAISE EXCEPTION 'work order disappeared';
    END IF;
    IF (SELECT count(*) FROM work_reports WHERE work_order_id = wo) <> 1 THEN
        RAISE EXCEPTION 'report history changed';
    END IF;
    IF (SELECT count(*) FROM acceptance_reviews WHERE work_order_id = wo) <> 1 THEN
        RAISE EXCEPTION 'acceptance history changed';
    END IF;
    IF (SELECT count(*) FROM evidence_files WHERE work_order_id = wo) <> 2 THEN
        RAISE EXCEPTION 'evidence history changed';
    END IF;
    IF (SELECT count(*) FROM forecast_runs WHERE maintenance_rule_id = r1) <> 2 THEN
        RAISE EXCEPTION 'forecast history changed';
    END IF;
    IF (SELECT count(*) FROM audit_events WHERE entity_type = 'maintenance_rules' AND entity_id = r1) < 2 THEN
        RAISE EXCEPTION 'audit history is incomplete';
    END IF;
END $$;

\echo '== 3. rollback fixtures =='
ROLLBACK;

\echo 'ALL SCHEMA CHECKS PASSED'
