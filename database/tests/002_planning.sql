\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE s uuid; other_site uuid; sys uuid; typ uuid; doc uuid; ed uuid; op uuid;
 r uuid; r2 uuid; u uuid; p uuid; e1 uuid; e2 uuid; b1 uuid; b2 uuid; entry uuid;
BEGIN
 INSERT INTO sites(name) VALUES('site') RETURNING site_id INTO s;
 INSERT INTO sites(name) VALUES('other') RETURNING site_id INTO other_site;
 INSERT INTO users(full_name,email) VALUES('user','user@example.test') RETURNING user_id INTO u;
 INSERT INTO site_memberships(site_id,user_id,role) VALUES(s,u,'engineer');
 INSERT INTO engineering_systems(site_id,code,name) VALUES(s,'sys','system') RETURNING system_id INTO sys;
 INSERT INTO maintenance_types(code,name) VALUES('TO','TO') RETURNING maintenance_type_id INTO typ;
 INSERT INTO regulation_documents(site_id,title) VALUES(s,'document') RETURNING regulation_document_id INTO doc;
 INSERT INTO regulation_editions(site_id,regulation_document_id,edition_code,effective_from) VALUES(s,doc,'v1','2026-01-01') RETURNING regulation_edition_id INTO ed;
 INSERT INTO operation_templates(site_id,system_id,code,title,maintenance_type_id) VALUES(s,sys,'op','operation',typ) RETURNING operation_template_id INTO op;
 INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,period_unit,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref) VALUES(s,sys,op,ed,'day','fixed_interval',1,NULL,'2026-01-01','1/day','source') RETURNING maintenance_rule_id INTO r;
 INSERT INTO maintenance_rules(site_id,system_id,operation_template_id,regulation_edition_id,rule_version,supersedes_rule_id,period_unit,scheduling_mode,required_people,norm_hours,active_from,source_text,source_ref) VALUES(s,sys,op,ed,2,r,'day','fixed_interval',1,1.123,'2026-01-01','1/day','source') RETURNING maintenance_rule_id INTO r2;
 INSERT INTO equipment(site_id,system_id,asset_code,name) VALUES(s,sys,'a','a') RETURNING equipment_id INTO e1;
 INSERT INTO equipment(site_id,system_id,asset_code,name) VALUES(s,sys,'b','b') RETURNING equipment_id INTO e2;
 INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from) VALUES(s,sys,r,e1,'2026-01-01') RETURNING binding_id INTO b1;
 INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from) VALUES(s,sys,r,e2,'2026-01-01') RETURNING binding_id INTO b2;
 INSERT INTO schedule_plans(site_id,period_year,period_month,created_by) VALUES(s,2026,10,u) RETURNING schedule_plan_id INTO p;
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES(s,sys,p,r,b1,'2026-10-01','2026-10-02','2026-10-02 23:00+05') RETURNING schedule_entry_id INTO entry;
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES(s,sys,p,r,b2,'2026-10-01','2026-10-02','2026-10-02 23:00+05');
 BEGIN
 INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,regulatory_deadline_on,regulatory_deadline_at) VALUES(s,sys,p,r2,b1,'2026-10-02','2026-10-02','2026-10-02 23:00+05');
 RAISE EXCEPTION 'binding from another rule accepted'; EXCEPTION WHEN foreign_key_violation THEN NULL; END;
 BEGIN
 UPDATE schedule_entries SET earliest_date='2026-10-02' WHERE schedule_entry_id=entry;
 RAISE EXCEPTION 'inverted window accepted'; EXCEPTION WHEN check_violation THEN NULL; END;
 BEGIN
 UPDATE equipment SET site_id=other_site WHERE equipment_id=e1;
 RAISE EXCEPTION 'cross-site equipment accepted'; EXCEPTION WHEN foreign_key_violation THEN NULL; END;
 UPDATE schedule_entries SET status='cancelled' WHERE schedule_entry_id=entry;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE entity_id=entry AND action='update' AND before_snapshot->>'status'='planned' AND after_snapshot->>'status'='cancelled') THEN RAISE EXCEPTION 'audit snapshots missing'; END IF;
 IF NOT EXISTS (SELECT 1 FROM maintenance_rules WHERE maintenance_rule_id=r AND norm_hours IS NULL) OR NOT EXISTS (SELECT 1 FROM maintenance_rules WHERE maintenance_rule_id=r2 AND norm_hours=1.123 AND supersedes_rule_id=r) THEN RAISE EXCEPTION 'rule versions or norms lost'; END IF;
END $$;
ROLLBACK;
