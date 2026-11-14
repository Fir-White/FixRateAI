-- Runtime schema contract after ALL migrations 001-009, with or without the CLI ledger.
-- Run only in a disposable database. Every fixture is rolled back.
\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE missing text; amount integer;
BEGIN
    SELECT string_agg(name,', ') INTO missing FROM unnest(ARRAY[
        'fixrate_sessions','planning_runs','employee_shift_rules','site_join_codes','employment_applications','maintenance_notifications'
    ]) name WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint c WHERE c.conrelid=to_regclass('public.'||name) AND c.contype='p');
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'Missing runtime table/primary key: %',missing; END IF;
    SELECT count(*) INTO amount FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
        WHERE n.nspname='public' AND c.contype='p' AND c.conrelid<>coalesce(to_regclass('public.fixrate_schema_migrations'),0::oid);
    IF amount<>41 THEN RAISE EXCEPTION 'Expected 41 application primary keys after 009, found %',amount; END IF;
    SELECT string_agg(expected.rel||'.'||expected.col,', ') INTO missing FROM (VALUES
        ('schedule_entries','source_date'),('work_orders','overdue_since_at'),('work_reports','execution_context'),('work_readings','phase'),('evidence_files','verification_context'),('equipment','revision'),('work_orders','revision'),('work_orders','planned_end_at'),
        ('work_reports','checklist_snapshot'),('acceptance_reviews','decision_context'),
        ('evidence_files','checklist_item_id'),('evidence_files','view_key'),('evidence_files','equipment_id'),
        ('work_assignments','start_at'),('work_assignments','end_at'),('work_assignments','qualification_snapshot'),
        ('work_assignments','reason'),('work_assignments','released_at'),('schedule_entries','source_occurrence_id'),
        ('site_memberships','revision'),('site_memberships','employed_from'),('site_memberships','employed_until'),
        ('crews','revision'),('availability_slots','revision'),('availability_slots','is_active'),('user_skills','revision')
    ) expected(rel,col) WHERE NOT EXISTS(SELECT 1 FROM information_schema.columns c
        WHERE c.table_schema='public' AND c.table_name=expected.rel AND c.column_name=expected.col);
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'Missing runtime columns: %',missing; END IF;
    SELECT string_agg(name,', ') INTO missing FROM unnest(ARRAY[
        'users_email_casefold','work_assignments_current_worker','work_assignments_worker_interval',
        'schedule_entries_source_occurrence','schedule_entries_binding_source_date','employee_shift_rules_worker'
    ]) name WHERE to_regclass('public.'||name) IS NULL;
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'Missing runtime indexes: %',missing; END IF;
END $$;

CREATE FUNCTION pg_temp.expect_sqlstate(label text, statement text, expected text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual text;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE;
        IF actual<>expected THEN RAISE EXCEPTION '%: expected SQLSTATE %, got % (%)',label,expected,actual,SQLERRM; END IF;
        RAISE NOTICE 'Rejected % with SQLSTATE %',label,actual;
        RETURN;
    END;
    RAISE EXCEPTION '%: invalid input was accepted',label;
END $$;

DO $$
DECLARE s uuid; other_site uuid; u uuid; outsider uuid; sys uuid; mt uuid; doc uuid; ed uuid;
    op uuid; rule uuid; plan uuid; entry uuid; eq uuid; wo uuid; report uuid; assignment uuid;
    crew uuid; key uuid := gen_random_uuid(); run uuid; shift uuid; scenario record;
BEGIN
    INSERT INTO sites(name) VALUES ('Runtime schema contract') RETURNING site_id INTO s;
    INSERT INTO sites(name) VALUES ('Other runtime site') RETURNING site_id INTO other_site;
    INSERT INTO users(full_name,email) VALUES ('Runtime QA',gen_random_uuid()::text||'@example.test') RETURNING user_id INTO u;
    INSERT INTO users(full_name,email) VALUES ('Other runtime QA',gen_random_uuid()::text||'@example.test') RETURNING user_id INTO outsider;
    INSERT INTO site_memberships(site_id,user_id,role) VALUES (s,u,'dispatcher'),(other_site,outsider,'executor');
    INSERT INTO engineering_systems(site_id,code,name) VALUES (s,'runtime','Runtime') RETURNING system_id INTO sys;
    INSERT INTO equipment(site_id,system_id,asset_code,name) VALUES (s,sys,'runtime','Runtime equipment') RETURNING equipment_id INTO eq;
    INSERT INTO crews(site_id,name) VALUES (s,'Runtime crew') RETURNING crew_id INTO crew;
    INSERT INTO maintenance_types(code,name) VALUES (gen_random_uuid()::text,'Runtime type') RETURNING maintenance_type_id INTO mt;
    INSERT INTO regulation_documents(site_id,title) VALUES (s,'Runtime regulation') RETURNING regulation_document_id INTO doc;
    INSERT INTO regulation_editions(site_id,regulation_document_id,edition_code,effective_from) VALUES (s,doc,'runtime','2026-01-01') RETURNING regulation_edition_id INTO ed;
    INSERT INTO operation_templates(site_id,system_id,code,title,maintenance_type_id) VALUES (s,sys,'runtime','Runtime operation',mt) RETURNING operation_template_id INTO op;
    INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,period_unit,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref)
        VALUES (s,sys,op,ed,'day','fixed_interval',1,1,'2026-01-01','daily','runtime contract') RETURNING maintenance_rule_id INTO rule;
    INSERT INTO schedule_plans(site_id,period_year,period_month,created_by) VALUES (s,2026,11,u) RETURNING schedule_plan_id INTO plan;
    INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,planned_date,regulatory_deadline_on,regulatory_deadline_at)
        VALUES (s,sys,plan,rule,'2026-11-01','2026-11-01','2026-11-01 23:59+05') RETURNING schedule_entry_id INTO entry;
    INSERT INTO work_orders(site_id,system_id,maintenance_rule_id,schedule_entry_id,required_people_snapshot,norm_hours_snapshot,planned_start_at,planned_end_at)
        VALUES (s,sys,rule,entry,1,1,'2026-11-01 08:00+05','2026-11-01 09:00+05') RETURNING work_order_id INTO wo;
    INSERT INTO work_reports(site_id,work_order_id,submitted_by) VALUES (s,wo,u) RETURNING work_report_id INTO report;
    INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,start_at,end_at,qualification_snapshot)
        VALUES (s,wo,u,u,'2026-11-01 08:00+05','2026-11-01 09:00+05','[]') RETURNING work_assignment_id INTO assignment;
    INSERT INTO planning_runs(site_id,idempotency_key,request_sha256,period_year,period_month,created_by,response_snapshot)
        VALUES (s,key,repeat('a',64),2026,11,u,'{}') RETURNING planning_run_id INTO run;
    INSERT INTO employee_shift_rules(site_id,user_id,label,calendar_pattern,valid_from,starts_local,ends_local)
        VALUES (s,u,'Day shift','{}','2026-01-01','08:00','16:00') RETURNING shift_rule_id INTO shift;
    INSERT INTO site_join_codes(site_id,code) VALUES (s,key::text);
    INSERT INTO employment_applications(site_id,user_id) VALUES (s,u);

    FOR scenario IN SELECT * FROM (VALUES
        ('zero equipment revision',format('UPDATE equipment SET revision=0 WHERE equipment_id=%L',eq),'23514'),
        ('zero order revision',format('UPDATE work_orders SET revision=0 WHERE work_order_id=%L',wo),'23514'),
        ('reversed order interval',format('UPDATE work_orders SET planned_end_at=planned_start_at WHERE work_order_id=%L',wo),'23514'),
        ('non-array checklist snapshot',format('UPDATE work_reports SET checklist_snapshot=%L WHERE work_report_id=%L','{}',report),'23514'),
        ('partial assignment interval',format('UPDATE work_assignments SET end_at=NULL WHERE work_assignment_id=%L',assignment),'23514'),
        ('reversed assignment interval',format('UPDATE work_assignments SET end_at=start_at WHERE work_assignment_id=%L',assignment),'23514'),
        ('non-array qualification snapshot',format('UPDATE work_assignments SET qualification_snapshot=%L WHERE work_assignment_id=%L','{}',assignment),'23514'),
        ('duplicate active worker',format('INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by) VALUES (%L,%L,%L,%L)',s,wo,u,u),'23505'),
        ('duplicate planning key',format('INSERT INTO planning_runs(site_id,idempotency_key,request_sha256,period_year,period_month,created_by,response_snapshot) SELECT site_id,idempotency_key,request_sha256,period_year,period_month,created_by,response_snapshot FROM planning_runs WHERE planning_run_id=%L',run),'23505'),
        ('invalid planning year',format('UPDATE planning_runs SET period_year=1999 WHERE planning_run_id=%L',run),'23514'),
        ('invalid planning month',format('UPDATE planning_runs SET period_month=13 WHERE planning_run_id=%L',run),'23514'),
        ('non-object planning response',format('UPDATE planning_runs SET response_snapshot=%L WHERE planning_run_id=%L','[]',run),'23514'),
        ('cross-site plan creator',format('UPDATE planning_runs SET created_by=%L WHERE planning_run_id=%L',outsider,run),'23503'),
        ('reversed employment dates',format('UPDATE site_memberships SET employed_from=%L,employed_until=%L WHERE site_id=%L AND user_id=%L','2026-12-01','2026-01-01',s,u),'23514'),
        ('zero membership revision',format('UPDATE site_memberships SET revision=0 WHERE site_id=%L AND user_id=%L',s,u),'23514'),
        ('zero crew revision',format('UPDATE crews SET revision=0 WHERE crew_id=%L',crew),'23514'),
        ('empty shift label',format('UPDATE employee_shift_rules SET label=%L WHERE shift_rule_id=%L',' ',shift),'23514'),
        ('non-object shift calendar',format('UPDATE employee_shift_rules SET calendar_pattern=%L WHERE shift_rule_id=%L','[]',shift),'23514'),
        ('reversed shift validity',format('UPDATE employee_shift_rules SET valid_until=%L WHERE shift_rule_id=%L','2025-12-31',shift),'23514'),
        ('unsupported 24:00 clock',format('UPDATE employee_shift_rules SET ends_local=%L WHERE shift_rule_id=%L','24:00',shift),'23514'),
        ('invalid shift status',format('UPDATE employee_shift_rules SET status=%L WHERE shift_rule_id=%L','broken',shift),'23514'),
        ('cross-site shift worker',format('UPDATE employee_shift_rules SET user_id=%L WHERE shift_rule_id=%L',outsider,shift),'23503'),
        ('duplicate join code',format('INSERT INTO site_join_codes(site_id,code) VALUES (%L,%L)',other_site,key::text),'23505'),
        ('invalid application status',format('UPDATE employment_applications SET status=%L WHERE site_id=%L','broken',s),'23514'),
        ('cross-site application reviewer',format('UPDATE employment_applications SET decided_by=%L WHERE site_id=%L',outsider,s),'23503'),
        ('session for missing user',format('INSERT INTO fixrate_sessions(token_hash,csrf_hash,user_id,site_id,expires_at) VALUES (%L,%L,%L,%L,now())',repeat('a',64),repeat('b',64),gen_random_uuid(),s),'23503')
    ) cases(label,statement,expected) LOOP
        PERFORM pg_temp.expect_sqlstate(scenario.label,scenario.statement,scenario.expected);
    END LOOP;
    UPDATE employee_shift_rules SET ends_local=starts_local WHERE shift_rule_id=shift;
    IF NOT (SELECT starts_local=ends_local FROM employee_shift_rules WHERE shift_rule_id=shift)
        THEN RAISE EXCEPTION 'Full-day shift was not preserved'; END IF;
    -- Reassignment creates a new row; it must never delete the previous assignment.
    UPDATE work_assignments SET status='cancelled',released_at=now() WHERE work_assignment_id=assignment;
    INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by) VALUES (s,wo,u,u);
    IF (SELECT count(*) FROM work_assignments WHERE work_order_id=wo)<>2 THEN RAISE EXCEPTION 'Assignment history was lost'; END IF;
    IF (SELECT revision FROM work_orders WHERE work_order_id=wo)<>1 THEN RAISE EXCEPTION 'Failed negative updates changed the order'; END IF;
END $$;
ROLLBACK;
\echo 'ALL RUNTIME SCHEMA CHECKS PASSED'
