\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE s uuid; sys uuid; typ uuid; doc uuid; ed uuid; op uuid; r1 uuid; r2 uuid; u uuid; p uuid; entry uuid; entry2 uuid; wo uuid;
BEGIN
 INSERT INTO sites(name) VALUES ('TL03 test') RETURNING site_id INTO s;
 INSERT INTO users(full_name,email) VALUES ('engineer','tl03@example.test') RETURNING user_id INTO u;
 INSERT INTO site_memberships(site_id,user_id,role) VALUES (s,u,'engineer');
 INSERT INTO engineering_systems(site_id,code,name) VALUES (s,'sys','system') RETURNING system_id INTO sys;
 INSERT INTO maintenance_types(code,name) VALUES ('TL03','TL03') RETURNING maintenance_type_id INTO typ;
 INSERT INTO regulation_documents(site_id,title) VALUES (s,'document') RETURNING regulation_document_id INTO doc;
 INSERT INTO regulation_editions(site_id,regulation_document_id,edition_code,effective_from) VALUES (s,doc,'v1','2026-01-01') RETURNING regulation_edition_id INTO ed;
 INSERT INTO operation_templates(site_id,system_id,code,title,maintenance_type_id) VALUES (s,sys,'op','operation',typ) RETURNING operation_template_id INTO op;
 INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,period_unit,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref) VALUES (s,sys,op,ed,'day','fixed_interval',1,1.125,'2026-01-01','daily','source') RETURNING maintenance_rule_id INTO r1;
 INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,rule_version,period_unit,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref) VALUES (s,sys,op,ed,2,'day','fixed_interval',1,1.125,'2026-01-01','daily','source') RETURNING maintenance_rule_id INTO r2;
 INSERT INTO schedule_plans(site_id,period_year,period_month,created_by) VALUES (s,2026,10,u) RETURNING schedule_plan_id INTO p;
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES (s,sys,p,r1,'2026-10-01','2026-10-01','2026-10-01 23:59+05') RETURNING schedule_entry_id INTO entry;
 INSERT INTO work_orders(site_id,system_id,maintenance_rule_id,schedule_entry_id,required_people_snapshot,norm_hours_snapshot) VALUES (s,sys,r1,entry,1,1.125) RETURNING work_order_id INTO wo;
 IF (SELECT norm_hours_snapshot FROM work_orders WHERE work_order_id=wo) <> 1.125 THEN RAISE EXCEPTION 'precision lost'; END IF;
 BEGIN
  UPDATE work_orders SET maintenance_rule_id=r2 WHERE work_order_id=wo;
  RAISE EXCEPTION 'mismatched rule accepted';
 EXCEPTION WHEN foreign_key_violation THEN NULL; END;
 BEGIN
  UPDATE schedule_entries SET maintenance_rule_id=r2 WHERE schedule_entry_id=entry;
  RAISE EXCEPTION 'changing referenced schedule rule accepted';
 EXCEPTION WHEN foreign_key_violation THEN NULL; END;
 BEGIN
  UPDATE work_orders SET norm_hours_snapshot=-0.001 WHERE work_order_id=wo;
  RAISE EXCEPTION 'negative norm accepted';
 EXCEPTION WHEN check_violation THEN NULL; END;
 -- Preserve the full integer range of the former NUMERIC(12,2).
 UPDATE work_orders SET norm_hours_snapshot=9999999999.99 WHERE work_order_id=wo;
 IF (SELECT norm_hours_snapshot FROM work_orders WHERE work_order_id=wo) <> 9999999999.990 THEN RAISE EXCEPTION 'old range lost'; END IF;
 -- Simulate a legacy mismatch before the new FK is installed. NOT VALID must
 -- preserve it while enforcing future writes; VALIDATE must still reject it.
 ALTER TABLE work_orders DROP CONSTRAINT fk_work_orders_entry_rule;
 UPDATE work_orders SET maintenance_rule_id=r2 WHERE work_order_id=wo;
 ALTER TABLE work_orders ADD CONSTRAINT fk_work_orders_entry_rule
   FOREIGN KEY (site_id,system_id,schedule_entry_id,maintenance_rule_id)
   REFERENCES schedule_entries (site_id,system_id,schedule_entry_id,maintenance_rule_id)
   ON DELETE RESTRICT NOT VALID;
 IF NOT EXISTS (SELECT 1 FROM work_orders WHERE work_order_id=wo AND maintenance_rule_id=r2) THEN RAISE EXCEPTION 'legacy row lost'; END IF;
 BEGIN
  ALTER TABLE work_orders VALIDATE CONSTRAINT fk_work_orders_entry_rule;
  RAISE EXCEPTION 'invalid legacy row validated';
 EXCEPTION WHEN foreign_key_violation THEN NULL; END;
 BEGIN
  INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES (s,sys,p,r1,'2026-10-02','2026-10-02','2026-10-02 23:59+05') RETURNING schedule_entry_id INTO entry2;
  INSERT INTO work_orders(site_id,system_id,maintenance_rule_id,schedule_entry_id,required_people_snapshot,norm_hours_snapshot) VALUES (s,sys,r2,entry2,1,1.125);
  RAISE EXCEPTION 'new mismatch accepted';
 EXCEPTION WHEN foreign_key_violation THEN NULL; END;
END $$;
ROLLBACK;
