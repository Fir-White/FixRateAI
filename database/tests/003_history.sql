\set ON_ERROR_STOP on
-- Verifies the append-and-supersede workflow, not immutability against arbitrary updates.
BEGIN;
DO $$
DECLARE s uuid; sys uuid; typ uuid; doc uuid; ed1 uuid; ed2 uuid; op uuid;
 r1 uuid; r2 uuid; u uuid; eq uuid; b1 uuid; b2 uuid; p1 uuid; p2 uuid;
 old_entry uuid; future_entry uuid; new_entry uuid; wo uuid; report uuid; photo uuid; review uuid;
BEGIN
 INSERT INTO sites(name) VALUES ('history test') RETURNING site_id INTO s;
 INSERT INTO users(full_name,email) VALUES ('engineer','history@example.test') RETURNING user_id INTO u;
 INSERT INTO site_memberships(site_id,user_id,role) VALUES (s,u,'engineer');
 INSERT INTO engineering_systems(site_id,code,name) VALUES (s,'sys','system') RETURNING system_id INTO sys;
 INSERT INTO equipment(site_id,system_id,asset_code,name) VALUES (s,sys,'asset','equipment') RETURNING equipment_id INTO eq;
 INSERT INTO maintenance_types(code,name) VALUES ('history','history') RETURNING maintenance_type_id INTO typ;
 INSERT INTO operation_templates(site_id,system_id,code,title,maintenance_type_id) VALUES (s,sys,'op','operation',typ) RETURNING operation_template_id INTO op;
 INSERT INTO regulation_documents(site_id,title) VALUES (s,'regulation') RETURNING regulation_document_id INTO doc;
 INSERT INTO regulation_editions(site_id,regulation_document_id,edition_code,effective_from) VALUES (s,doc,'A','2026-01-01') RETURNING regulation_edition_id INTO ed1;
 INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,period_unit,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref)
 VALUES (s,sys,op,ed1,'day','fixed_interval',1,1.125,'2026-01-01','daily','source A') RETURNING maintenance_rule_id INTO r1;
 INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from) VALUES (s,sys,r1,eq,'2026-01-01') RETURNING binding_id INTO b1;
 INSERT INTO schedule_plans(site_id,period_year,period_month,revision,created_by) VALUES (s,2026,10,1,u) RETURNING schedule_plan_id INTO p1;
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at,rule_snapshot)
 VALUES (s,sys,p1,r1,b1,'2026-10-01','2026-10-01','2026-10-01 23:59+05','{"norm_hours":1.125}') RETURNING schedule_entry_id INTO old_entry;
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at)
 VALUES (s,sys,p1,r1,b1,'2026-10-02','2026-10-02','2026-10-02 23:59+05') RETURNING schedule_entry_id INTO future_entry;
 -- work_orders currently stores only two decimal places: preserve the exact raw value in the JSON snapshot.
 INSERT INTO work_orders(site_id,system_id,maintenance_rule_id,schedule_entry_id,status,required_people_snapshot,norm_hours_snapshot,operation_snapshot,completed_at)
 VALUES (s,sys,r1,old_entry,'completed',1,1.13,'{"raw_norm_value":"1.125"}','2026-10-01 14:00+05') RETURNING work_order_id INTO wo;
 INSERT INTO work_reports(site_id,work_order_id,revision_no,submitted_by,status,submitted_at) VALUES (s,wo,1,u,'reviewed','2026-10-01 14:00+05') RETURNING work_report_id INTO report;
 INSERT INTO evidence_files(site_id,work_order_id,work_report_id,uploaded_by,stage,storage_key,mime_type,file_size,sha256) VALUES (s,wo,report,u,'after','history-test','image/jpeg',10,repeat('a',64)) RETURNING evidence_file_id INTO photo;
 INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision) VALUES (s,wo,report,u,'accepted') RETURNING acceptance_review_id INTO review;
 INSERT INTO regulation_editions(site_id,regulation_document_id,edition_code,effective_from) VALUES (s,doc,'B','2026-10-02') RETURNING regulation_edition_id INTO ed2;
 INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,supersedes_rule_id,rule_version,period_unit,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref)
 VALUES (s,sys,op,ed2,r1,2,'day','fixed_interval',2,2.125,'2026-10-02','daily','source B') RETURNING maintenance_rule_id INTO r2;
 INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from) VALUES (s,sys,r2,eq,'2026-10-02') RETURNING binding_id INTO b2;
 UPDATE schedule_entries SET status='superseded' WHERE schedule_entry_id=future_entry;
 INSERT INTO schedule_plans(site_id,period_year,period_month,revision,created_by) VALUES (s,2026,10,2,u) RETURNING schedule_plan_id INTO p2;
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at)
 VALUES (s,sys,p2,r2,b2,'2026-10-02','2026-10-02','2026-10-02 23:59+05') RETURNING schedule_entry_id INTO new_entry;
 IF NOT EXISTS (SELECT 1 FROM work_orders w JOIN schedule_entries e ON e.schedule_entry_id=w.schedule_entry_id JOIN maintenance_rules r ON r.maintenance_rule_id=w.maintenance_rule_id JOIN work_reports wr ON wr.work_order_id=w.work_order_id JOIN evidence_files f ON f.work_report_id=wr.work_report_id JOIN acceptance_reviews a ON a.work_report_id=wr.work_report_id WHERE w.work_order_id=wo AND e.schedule_entry_id=old_entry AND r.regulation_edition_id=ed1 AND r.norm_hours=1.125 AND w.operation_snapshot->>'raw_norm_value'='1.125' AND w.completed_at='2026-10-01 14:00+05' AND wr.work_report_id=report AND f.evidence_file_id=photo AND a.acceptance_review_id=review AND a.decision='accepted') THEN
  RAISE EXCEPTION 'historical work or evidence lost';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM schedule_entries WHERE schedule_entry_id=future_entry AND status='superseded') OR NOT EXISTS (SELECT 1 FROM schedule_entries WHERE schedule_entry_id=new_entry AND maintenance_rule_id=r2 AND binding_id=b2) THEN RAISE EXCEPTION 'replacement plan invalid'; END IF;
 BEGIN
  INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES (s,sys,p2,r2,b2,'2026-10-02','2026-10-02','2026-10-02 23:59+05');
  RAISE EXCEPTION 'duplicate occurrence accepted';
 EXCEPTION WHEN unique_violation THEN NULL; END;
END $$;
ROLLBACK;
