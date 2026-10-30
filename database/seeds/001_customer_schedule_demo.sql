-- Run after migrations 001-004. Isolated synthetic site; stable IDs make reruns no-ops.
-- Customer fields are sourced from the workbook; all operational history is DEMO.
BEGIN;
SET LOCAL client_encoding = 'UTF8';

INSERT INTO sites(site_id,name,address) VALUES
 (md5('fixrate-demo-site')::uuid,'DEMO — тепловой пункт','DEMO: вымышленный объект') ON CONFLICT DO NOTHING;
INSERT INTO users(user_id,full_name,email) VALUES
 (md5('fixrate-demo-user-1')::uuid,'DEMO Исполнитель 1','fixrate-demo-1@example.test'),
 (md5('fixrate-demo-user-2')::uuid,'DEMO Исполнитель 2','fixrate-demo-2@example.test') ON CONFLICT DO NOTHING;
INSERT INTO site_memberships(site_id,user_id,role) VALUES
 (md5('fixrate-demo-site')::uuid,md5('fixrate-demo-user-1')::uuid,'technician'),
 (md5('fixrate-demo-site')::uuid,md5('fixrate-demo-user-2')::uuid,'technician') ON CONFLICT DO NOTHING;
INSERT INTO engineering_systems(system_id,site_id,code,name,notes) VALUES
 (md5('fixrate-demo-system')::uuid,md5('fixrate-demo-site')::uuid,'DEMO-HEAT','Система теплоснабжения','DEMO объект; название раздела из B4 книги') ON CONFLICT DO NOTHING;
INSERT INTO equipment_types(equipment_type_id,code,name,default_attributes) VALUES
 (md5('fixrate-demo-type')::uuid,'DEMO-HEAT-POINT','Тепловой пункт (комплекс устройств)','{"data_origin":"synthetic_demo"}') ON CONFLICT DO NOTHING;
INSERT INTO equipment(equipment_id,site_id,system_id,equipment_type_id,asset_code,name,commissioned_on,properties) VALUES
 (md5('fixrate-demo-equipment-1')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-type')::uuid,'DEMO-TP-01','DEMO тепловой пункт 01','2026-01-01','{"data_origin":"synthetic_demo"}'),
 (md5('fixrate-demo-equipment-2')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-type')::uuid,'DEMO-TP-02','DEMO тепловой пункт 02','2026-10-01','{"data_origin":"synthetic_demo"}') ON CONFLICT DO NOTHING;
INSERT INTO maintenance_types(maintenance_type_id,code,name,description) VALUES
 (md5('fixrate-demo-to1')::uuid,'DEMO-TO1','ТО1','Тип из графика заказчика'),
 (md5('fixrate-demo-to2')::uuid,'DEMO-TO2','ТО2','Тип из графика заказчика') ON CONFLICT DO NOTHING;
INSERT INTO regulation_documents(regulation_document_id,site_id,title,source_kind,source_uri) VALUES
 (md5('fixrate-demo-document')::uuid,md5('fixrate-demo-site')::uuid,'График ТО заказчика','customer','docs/customer/techical_service_schedule.xlsx') ON CONFLICT DO NOTHING;
INSERT INTO regulation_editions(regulation_edition_id,site_id,regulation_document_id,edition_code,effective_from,source_sha256,is_approved) VALUES
 (md5('fixrate-demo-edition')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-document')::uuid,'DEMO-import','2026-01-01','8608662fe5d66519e990f65d1377f3fad32c1e6d29d6524dc4aeed24cd079957',false) ON CONFLICT DO NOTHING;

-- The effective date, IDs, and equipment bindings are demonstration choices.
-- Column F is retained verbatim as a number, with its basis unconfirmed.
WITH source(code,title,kind,frequency,unit,occurrences,people,norm,row_no) AS (VALUES
 ('1.1','Контроль параметров показаний приборов (давление, температура)','to1','1/день','day',1,1,1,6),
 ('1.2','Протоколирование показаний счетчиков (согласно инструкции)','to1','1/день','day',1,1,1,7),
 ('1.3','Проверка функционирования управляющего модуля','to1','1/день','day',1,1,1,8),
 ('1.4','Чистка всех узлов и агрегатов системы','to2','5/год','year',5,2,60,9),
 ('1.5','Проверка приборов измерения температуры и давления на повреждения и точность показаний','to2','1/квар','quarter',1,1,48,10),
 ('1.6','Выпустить воздух из системы отопления/теплоснабжения','to2','1/квар','quarter',1,1,30,11)
)
INSERT INTO operation_templates(operation_template_id,site_id,system_id,code,title,maintenance_type_id,description)
SELECT md5('fixrate-demo-operation-'||code)::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,code,title,md5('fixrate-demo-'||kind)::uuid,'Источник: Excel, строка '||row_no FROM source ON CONFLICT DO NOTHING;

WITH source(code,frequency,unit,occurrences,people,norm,row_no) AS (VALUES
 ('1.1','1/день','day',1,1,1,6),('1.2','1/день','day',1,1,1,7),('1.3','1/день','day',1,1,1,8),
 ('1.4','5/год','year',5,2,60,9),('1.5','1/квар','quarter',1,1,48,10),('1.6','1/квар','quarter',1,1,30,11)
)
INSERT INTO maintenance_rules(maintenance_rule_id,site_id,system_id,operation_template_id,regulation_edition_id,period_unit,occurrences_per_period,scheduling_mode,source_text,source_ref,required_people,norm_hours,norm_hours_basis,active_from,publication_status,data_origin,schedule_parameters)
SELECT md5('fixrate-demo-rule-'||code)::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-operation-'||code)::uuid,md5('fixrate-demo-edition')::uuid,unit,occurrences,CASE WHEN unit='day' THEN 'fixed_interval' ELSE 'calendar_window' END,frequency,'B'||row_no||':F'||row_no,people,norm,'unknown','2026-01-01','draft','customer','{"effective_date_origin":"synthetic_demo","dates_require_confirmation":true}' FROM source ON CONFLICT DO NOTHING;

INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from,binding_id)
SELECT md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-rule-'||code)::uuid,md5('fixrate-demo-equipment-1')::uuid,'2026-01-01',md5('fixrate-demo-binding-'||code)::uuid
FROM (VALUES ('1.1'),('1.2'),('1.3'),('1.4'),('1.5'),('1.6')) AS s(code) ON CONFLICT DO NOTHING;

-- Synthetic historical work: no calendar marks are represented as completed customer work.
INSERT INTO work_orders(work_order_id,site_id,system_id,maintenance_rule_id,origin,status,operation_snapshot,required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot,created_by,started_at,completed_at)
VALUES (md5('fixrate-demo-work')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-rule-1.1')::uuid,'manual','completed','{"data_origin":"synthetic_demo","label":"DEMO — вымышленная история"}',1,1,'unknown',md5('fixrate-demo-user-1')::uuid,'2026-09-30 09:00+05','2026-09-30 10:00+05') ON CONFLICT DO NOTHING;
INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id,asset_snapshot) VALUES
 (md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-work')::uuid,md5('fixrate-demo-equipment-1')::uuid,'{"data_origin":"synthetic_demo"}') ON CONFLICT DO NOTHING;
INSERT INTO work_assignments(work_assignment_id,site_id,work_order_id,user_id,assigned_by,assigned_at,status) VALUES
 (md5('fixrate-demo-assignment')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-work')::uuid,md5('fixrate-demo-user-1')::uuid,md5('fixrate-demo-user-1')::uuid,'2026-09-30 08:00+05','finished') ON CONFLICT DO NOTHING;
INSERT INTO work_reports(work_report_id,site_id,work_order_id,submitted_by,comment,status,submitted_at) VALUES
 (md5('fixrate-demo-report')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-work')::uuid,md5('fixrate-demo-user-1')::uuid,'DEMO: вымышленный отчёт и замечание: требуется повторная проверка манометра.','submitted','2026-09-30 10:00+05') ON CONFLICT DO NOTHING;
INSERT INTO work_readings(work_reading_id,site_id,system_id,work_order_id,work_report_id,equipment_id,parameter_code,numeric_value,unit_code,measured_at,is_estimated) VALUES
 (md5('fixrate-demo-reading')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-work')::uuid,md5('fixrate-demo-report')::uuid,md5('fixrate-demo-equipment-1')::uuid,'DEMO-pressure',2.4,'bar','2026-09-30 09:30+05',true) ON CONFLICT DO NOTHING;
INSERT INTO incident_reports(incident_report_id,site_id,system_id,equipment_id,reported_by,description,created_at) VALUES
 (md5('fixrate-demo-incident')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-system')::uuid,md5('fixrate-demo-equipment-1')::uuid,md5('fixrate-demo-user-1')::uuid,'DEMO: вымышленное замечание — проверить манометр.','2026-09-30 10:00+05') ON CONFLICT DO NOTHING;
INSERT INTO evidence_files(evidence_file_id,site_id,work_order_id,work_report_id,uploaded_by,stage,storage_key,mime_type,file_size,sha256,captured_at,uploaded_at) VALUES
 (md5('fixrate-demo-photo')::uuid,md5('fixrate-demo-site')::uuid,md5('fixrate-demo-work')::uuid,md5('fixrate-demo-report')::uuid,md5('fixrate-demo-user-1')::uuid,'issue','database/demo/demo-photo.png','image/png',2672,'a862f05afb320fbbebcaacc1cc1488f9f1abed8812990d1dcaa5bada4ec1a850','2026-09-30 09:30+05','2026-09-30 10:00+05') ON CONFLICT DO NOTHING;
COMMIT;
