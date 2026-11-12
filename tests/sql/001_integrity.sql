\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
 s uuid; sys uuid; typ uuid; doc uuid; ed uuid; op uuid; rule uuid; usr uuid; plan uuid; equip uuid; binding uuid;
 row record; n integer;
BEGIN
 INSERT INTO sites(name) VALUES ('Тепловой пункт') RETURNING site_id INTO s;
 INSERT INTO users(full_name,email) VALUES ('Инженер','test@example.org') RETURNING user_id INTO usr;
 INSERT INTO site_memberships(site_id,user_id,role) VALUES(s,usr,'engineer');
 INSERT INTO engineering_systems(site_id,code,name) VALUES(s,'heat','Теплоснабжение') RETURNING system_id INTO sys;
 INSERT INTO regulation_documents(site_id,title,source_uri) VALUES(s,'График заказчика','docs/customer/techical_service_schedule.xlsx') RETURNING regulation_document_id INTO doc;
 INSERT INTO regulation_editions(site_id,regulation_document_id,edition_code,effective_from) VALUES(s,doc,'исходная','2026-01-01') RETURNING regulation_edition_id INTO ed;
 FOR row IN SELECT * FROM (VALUES
 ('1.1','Контроль параметров показаний приборов','ТО1','day',1,1),
 ('1.2','Протоколирование показаний счетчиков','ТО1','day',1,1),
 ('1.3','Проверка функционирования управляющего модуля','ТО1','day',1,1),
 ('1.4','Чистка всех узлов и агрегатов системы','ТО2','year',2,60),
 ('1.5','Проверка приборов измерения температуры и давления','ТО2','quarter',1,48),
 ('1.6','Выпустить воздух из системы отопления','ТО2','quarter',1,30)
 ) AS x(code,title,kind,unit,people,hours) LOOP
 INSERT INTO maintenance_types(code,name) VALUES(row.kind,row.kind) ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name RETURNING maintenance_type_id INTO typ;
 INSERT INTO operation_templates(site_id,system_id,code,title,maintenance_type_id) VALUES(s,sys,row.code,row.title,typ) RETURNING operation_template_id INTO op;
 INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,period_unit,occurrences_per_period,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref)
 VALUES(s,sys,op,ed,row.unit,CASE WHEN row.code='1.4' THEN 5 ELSE 1 END,CASE WHEN row.unit='day' THEN 'fixed_interval' ELSE 'calendar_window' END,row.people,row.hours,'2026-01-01',CASE row.unit WHEN 'day' THEN '1/день' WHEN 'year' THEN '5/год' ELSE '1/квар' END,'Excel row ' || row.code) RETURNING maintenance_rule_id INTO rule;
 END LOOP;
 SELECT count(*) INTO n FROM maintenance_rules WHERE site_id=s;
 IF n <> 6 THEN RAISE EXCEPTION 'expected six rules'; END IF;
 INSERT INTO equipment(site_id,system_id,asset_code,name) VALUES(s,sys,'TP','Thermal station') RETURNING equipment_id INTO equip;
 INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from) VALUES(s,sys,rule,equip,'2026-01-01') RETURNING binding_id INTO binding;
 UPDATE maintenance_rules SET norm_hours=30.123 WHERE maintenance_rule_id=rule;
 IF NOT EXISTS (SELECT 1 FROM maintenance_rules WHERE maintenance_rule_id=rule AND norm_hours=30.123) THEN RAISE EXCEPTION 'precision lost'; END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE entity_id=rule AND action='update' AND (after_snapshot->>'norm_hours')::numeric=30.123) THEN RAISE EXCEPTION 'audit missing'; END IF;
 INSERT INTO schedule_plans(site_id,period_year,period_month,created_by) VALUES(s,2026,10,usr) RETURNING schedule_plan_id INTO plan;
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES(s,sys,plan,rule,binding,'2026-10-01','2026-10-01','2026-10-01 23:59:59+05');
 BEGIN
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES(s,sys,plan,rule,binding,'2026-10-01','2026-10-01','2026-10-01 23:59:59+05');
 RAISE EXCEPTION 'duplicate accepted'; EXCEPTION WHEN unique_violation THEN NULL; END;
 BEGIN
 UPDATE maintenance_rules SET required_people=0 WHERE maintenance_rule_id=rule;
 RAISE EXCEPTION 'invalid people accepted'; EXCEPTION WHEN check_violation THEN NULL; END;
 BEGIN
 UPDATE schedule_entries SET planned_date='2026-10-02' WHERE schedule_plan_id=plan;
 RAISE EXCEPTION 'late entry accepted'; EXCEPTION WHEN check_violation THEN NULL; END;
 BEGIN
 UPDATE maintenance_rules SET regulation_edition_id=gen_random_uuid() WHERE maintenance_rule_id=rule;
 RAISE EXCEPTION 'missing edition accepted'; EXCEPTION WHEN foreign_key_violation THEN NULL; END;
END $$;
ROLLBACK;
