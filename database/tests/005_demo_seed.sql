\set ON_ERROR_STOP on
-- Run in a disposable migrated database. Compare counts before/after a second load,
-- including audit rows created by planning triggers.
\ir ../seeds/001_customer_schedule_demo.sql
CREATE TEMP TABLE demo_seed_counts AS
SELECT (SELECT count(*) FROM sites WHERE site_id=md5('fixrate-demo-site')::uuid) sites,
 (SELECT count(*) FROM operation_templates WHERE site_id=md5('fixrate-demo-site')::uuid) operations,
 (SELECT count(*) FROM maintenance_rules WHERE site_id=md5('fixrate-demo-site')::uuid) rules,
 (SELECT count(*) FROM equipment WHERE site_id=md5('fixrate-demo-site')::uuid) equipment,
 (SELECT count(*) FROM rule_equipment WHERE site_id=md5('fixrate-demo-site')::uuid) bindings,
 (SELECT count(*) FROM work_orders WHERE site_id=md5('fixrate-demo-site')::uuid) orders,
 (SELECT count(*) FROM work_reports WHERE site_id=md5('fixrate-demo-site')::uuid) reports,
 (SELECT count(*) FROM acceptance_reviews WHERE site_id=md5('fixrate-demo-site')::uuid) reviews,
 (SELECT count(*) FROM site_memberships WHERE site_id=md5('fixrate-demo-site')::uuid) memberships,
 (SELECT count(*) FROM work_readings WHERE site_id=md5('fixrate-demo-site')::uuid) readings,
 (SELECT count(*) FROM evidence_files WHERE site_id=md5('fixrate-demo-site')::uuid) photos,
 (SELECT count(*) FROM incident_reports WHERE site_id=md5('fixrate-demo-site')::uuid) incidents,
 (SELECT count(*) FROM audit_events WHERE site_id=md5('fixrate-demo-site')::uuid) audits;
\ir ../seeds/001_customer_schedule_demo.sql
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM demo_seed_counts c WHERE
  c.sites <> (SELECT count(*) FROM sites WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.operations <> (SELECT count(*) FROM operation_templates WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.rules <> (SELECT count(*) FROM maintenance_rules WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.equipment <> (SELECT count(*) FROM equipment WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.bindings <> (SELECT count(*) FROM rule_equipment WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.orders <> (SELECT count(*) FROM work_orders WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.reports <> (SELECT count(*) FROM work_reports WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.reviews <> (SELECT count(*) FROM acceptance_reviews WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.memberships <> (SELECT count(*) FROM site_memberships WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.readings <> (SELECT count(*) FROM work_readings WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.photos <> (SELECT count(*) FROM evidence_files WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.incidents <> (SELECT count(*) FROM incident_reports WHERE site_id=md5('fixrate-demo-site')::uuid) OR
  c.audits <> (SELECT count(*) FROM audit_events WHERE site_id=md5('fixrate-demo-site')::uuid)) THEN
  RAISE EXCEPTION 'reloading seed changed counts';
 END IF;
 IF EXISTS (
  WITH expected(code,title,kind,frequency,people,norm) AS (VALUES
   ('1.1','Контроль параметров показаний приборов (давление, температура)','ТО1','1/день',1,1::numeric),
   ('1.2','Протоколирование показаний счетчиков (согласно инструкции)','ТО1','1/день',1,1::numeric),
   ('1.3','Проверка функционирования управляющего модуля','ТО1','1/день',1,1::numeric),
   ('1.4','Чистка всех узлов и агрегатов системы','ТО2','5/год',2,60::numeric),
   ('1.5','Проверка приборов измерения температуры и давления на повреждения и точность показаний','ТО2','1/квар',1,48::numeric),
   ('1.6','Выпустить воздух из системы отопления/теплоснабжения','ТО2','1/квар',1,30::numeric)
  ), actual AS (
   SELECT o.code,o.title,t.name kind,r.source_text frequency,r.required_people::int people,r.norm_hours norm
   FROM operation_templates o JOIN maintenance_types t USING(maintenance_type_id)
   JOIN maintenance_rules r USING(site_id,operation_template_id)
   WHERE o.site_id=md5('fixrate-demo-site')::uuid AND r.data_origin='customer' AND r.norm_hours_basis='unknown' AND r.publication_status='draft'
  )
  (SELECT * FROM expected EXCEPT SELECT * FROM actual)
  UNION ALL (SELECT * FROM actual EXCEPT SELECT * FROM expected)
 ) THEN RAISE EXCEPTION 'customer rows differ'; END IF;
 IF (SELECT count(*) FROM maintenance_rules WHERE site_id=md5('fixrate-demo-site')::uuid) <> 6 OR
    (SELECT count(*) FROM equipment WHERE site_id=md5('fixrate-demo-site')::uuid AND properties->>'data_origin'='synthetic_demo') <> 2 OR
    NOT EXISTS (SELECT 1 FROM work_orders WHERE work_order_id=md5('fixrate-demo-work')::uuid AND operation_snapshot->>'data_origin'='synthetic_demo') OR
    NOT EXISTS (SELECT 1 FROM work_orders w JOIN work_reports r USING(site_id,work_order_id)
      JOIN acceptance_reviews a USING(site_id,work_order_id,work_report_id)
      JOIN site_memberships m ON m.site_id=a.site_id AND m.user_id=a.reviewer_user_id
      JOIN users u ON u.user_id=m.user_id
      WHERE w.work_order_id=md5('fixrate-demo-work')::uuid AND w.status='completed'
       AND r.status='reviewed' AND a.decision='accepted' AND a.comment LIKE 'DEMO:%'
       AND m.role='engineer' AND u.full_name LIKE 'DEMO %') OR
    NOT EXISTS (SELECT 1 FROM work_readings WHERE work_reading_id=md5('fixrate-demo-reading')::uuid AND is_estimated) OR
    NOT EXISTS (SELECT 1 FROM evidence_files WHERE evidence_file_id=md5('fixrate-demo-photo')::uuid) THEN
  RAISE EXCEPTION 'missing or unmarked demo data';
 END IF;
END $$;
