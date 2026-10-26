-- FixRate AI · demo/reference data v1
-- Apply AFTER db/001_init.sql on a clean database:
--   psql -X -v ON_ERROR_STOP=1 -U fixrate -d fixrate -f db/002_seed_demo.sql
--
-- ВАЖНО:
-- * Расценки ниже — DEMO. Они не являются ФЕР/ТЕР и не должны использоваться
--   в реальных сметах. source_type='DEMO' и price_basis='demo' фиксируют это.
-- * Seed идемпотентен: повторный запуск не создаёт дубликаты.
-- * Цены не обновляются через UPDATE. Для новой цены создайте новый norm_source
--   (новую редакцию) и новые rates, чтобы история осталась неизменной.
-- * Пароли демо-пользователей не заданы (password_hash IS NULL). Учётные записи
--   нужны для created_by/reviewed_by; вход через API появится в карточке 3.

BEGIN;

-- ---------------------------------------------------------------------------
-- Справочник типов дефектов (пилотные сценарии MVP)
-- ---------------------------------------------------------------------------
INSERT INTO defect_types (defect_type_id, code, name, description, is_active) VALUES
    ('d2000000-0000-4000-8000-000000000001', 'facade_crack',
     'Трещина фасада', 'Пилотный сценарий: вертикальная/горизонтальная трещина наружной стены', TRUE),
    ('d2000000-0000-4000-8000-000000000002', 'tile_chip',
     'Скол плитки', 'Пилотный сценарий: повреждение облицовочной плитки', TRUE),
    ('d2000000-0000-4000-8000-000000000003', 'parking_leak',
     'Протечка парковки', 'Пилотный сценарий: протечка/разрушение гидроизоляции парковки', TRUE)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Демонстрационный источник расценок
-- ---------------------------------------------------------------------------
INSERT INTO norm_sources (
    source_id, source_type, title, edition, region,
    publication_date, effective_date, source_url, document_reference, is_verified
) VALUES (
    'd0000000-0000-4000-8000-000000000001',
    'DEMO',
    'DEMO-прайс FixRate AI (иллюстративные расценки)',
    '2026.1',
    'Свердловская область',
    NULL,
    NULL,
    NULL,
    'Учебный демонстрационный прайс. Не является ФЕР/ТЕР и не подлежит применению в реальных сметах.',
    FALSE
)
ON CONFLICT (source_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Демонстрационные расценки (одна на пилотный сценарий)
-- ---------------------------------------------------------------------------
INSERT INTO rates (
    rate_id, source_id, rate_code, work_name, description,
    unit_code, rate_unit_multiplier, base_price, currency,
    price_basis, cost_scope, is_active
) VALUES
    ('d1000000-0000-4000-8000-000000000001',
     'd0000000-0000-4000-8000-000000000001',
     'DEMO-FACADE-CRACK-01',
     'Заделка трещин фасада',
     'DEMO: очистка, расшивка и заделка трещины; состав работ условный',
     'm2', 1, 850.0000, 'RUB', 'demo', 'work_only', TRUE),
    ('d1000000-0000-4000-8000-000000000002',
     'd0000000-0000-4000-8000-000000000001',
     'DEMO-TILE-CHIP-01',
     'Замена повреждённой облицовочной плитки',
     'DEMO: демонтаж и укладка плитки; состав работ условный',
     'm2', 1, 1200.0000, 'RUB', 'demo', 'work_only', TRUE),
    ('d1000000-0000-4000-8000-000000000003',
     'd0000000-0000-4000-8000-000000000001',
     'DEMO-PARKING-LEAK-01',
     'Гидроизоляция парковки',
     'DEMO: подготовка основания и устройство гидроизоляции; состав работ условный',
     'm2', 1, 1500.0000, 'RUB', 'demo', 'work_only', TRUE)
ON CONFLICT (source_id, rate_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Демо-пользователи и объект
-- ---------------------------------------------------------------------------
INSERT INTO users (user_id, full_name, email, password_hash, role, is_active) VALUES
    ('d3000000-0000-4000-8000-000000000001', 'Демо Оператор',
     'demo.operator@fixrate.local', NULL, 'operator', TRUE),
    ('d3000000-0000-4000-8000-000000000002', 'Демо Сметчик',
     'demo.estimator@fixrate.local', NULL, 'estimator', TRUE),
    ('d3000000-0000-4000-8000-000000000003', 'Демо Администратор',
     'demo.admin@fixrate.local', NULL, 'admin', TRUE)
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO buildings (
    building_id, address, building_type, construction_year, floors_count,
    total_area, wall_material, additional_properties, is_active
) VALUES (
    'd4000000-0000-4000-8000-000000000001',
    'г. Екатеринбург, ул. Демонстрационная, 1',
    U&'\0436\0438\043B\043E\0435',
    1985,
    9,
    5400.00,
    U&'\043F\0430\043D\0435\043B\044C',
    '{"demo": true, "source": "db/002_seed_demo.sql"}'::jsonb,
    TRUE
)
ON CONFLICT (building_id) DO NOTHING;

-- Восстанавливаем контекст демо-объекта при повторном применении seed.
-- U&-литералы не зависят от кодировки клиентской консоли.
UPDATE buildings
SET building_type = U&'\0436\0438\043B\043E\0435',
    wall_material = U&'\043F\0430\043D\0435\043B\044C'
WHERE building_id = 'd4000000-0000-4000-8000-000000000001';

COMMIT;

-- Проверка после применения:
--   SELECT count(*) FROM defect_types WHERE code IN ('facade_crack','tile_chip','parking_leak');
--   SELECT count(*) FROM rates WHERE source_id = 'd0000000-0000-4000-8000-000000000001';
--   SELECT count(*) FROM users WHERE email LIKE 'demo.%@fixrate.local';
