# Демонстрационный seed графика

После миграций `001`–`004` из корня репозитория:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/seeds/001_customer_schedule_demo.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/seeds/001_customer_schedule_demo.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/005_demo_seed.sql
```

Тест загружает seed дважды и оставляет демонстрационные записи в базе. Используйте отдельную тестовую базу. Проверка выполнена на PostgreSQL 18.6 в однопользовательском режиме; для PostgreSQL 16 отдельно не проверялась. Seed рассчитан на выделенные им идентификаторы и коды `DEMO-*`; повторный запуск не обновляет уже изменённые записи (`ON CONFLICT DO NOTHING`), кроме перехода исходного демо-отчёта из `submitted` в `reviewed` при обновлении ранее загруженного seed. При конфликте с посторонними данными используйте чистую базу: seed не является механизмом синхронизации или восстановления изменённых значений.

Источник: `docs/customer/techical_service_schedule.xlsx`, лист `Лист1`, B6:F11. Названия, типы ТО, текст периодичности, число людей и значения колонки «Нормо-часы» сохранены из книги. Документ связан с SHA-256; правила остаются `draft`, `data_origin=customer`, основание нормы `unknown`. Единицы и смысл нормы требуют подтверждения; длительность не выводится. `5/год` и `1/квар` не задают конкретные даты. Дата начала правил и редакции — демонстрационная, не дата заказчика. В книге октябрь без года; seed не выдаёт демонстрационный 2026 год за год заказчика и не создаёт календарные назначения.

Объект, инвентарные единицы, даты ввода, исполнители, инженер, привязки, выполненная работа, показание, замечания, отчёт и приёмка — вымышленные. Объект и сотрудники имеют префикс `DEMO`, оборудование и снимок работы — `synthetic_demo`, показание — `is_estimated`. Завершённый наряд связан с проверенным отчётом и демонстрационной приёмкой инженера. Все исторические записи относятся к отдельному объекту `DEMO — тепловой пункт`; при выборках всегда проверяйте объект и происхождение работы. `demo-photo.png` — синтетическая заглушка с надписью DEMO, не фотография объекта. `storage_key` указывает на файл в репозитории; загрузку в объектное хранилище приложение должно выполнить отдельно.

```sql
-- Шесть строк заказчика, с исходным текстом периодичности.
SELECT o.code, o.title, t.name AS maintenance_type, r.source_text,
       r.required_people, r.norm_hours, r.norm_hours_basis, r.data_origin, r.source_ref
FROM maintenance_rules r
JOIN operation_templates o USING (site_id, operation_template_id)
JOIN maintenance_types t USING (maintenance_type_id)
WHERE r.site_id = md5('fixrate-demo-site')::uuid
ORDER BY o.code;

-- Искусственная история, показание и файл отчёта.
SELECT s.name, w.operation_snapshot->>'data_origin' AS origin,
       wr.comment, rd.parameter_code, rd.numeric_value, rd.unit_code,
       rd.is_estimated, f.storage_key
FROM work_orders w
JOIN sites s USING (site_id)
JOIN work_reports wr USING (site_id, work_order_id)
LEFT JOIN work_readings rd USING (site_id, work_order_id, work_report_id)
LEFT JOIN evidence_files f USING (site_id, work_order_id, work_report_id)
WHERE w.site_id = md5('fixrate-demo-site')::uuid;
```
