# Архитектура ТО/ППР в dev

Срез 01.11.2026. Исполняемая система: FastAPI, PostgreSQL 001–008, React SPA, общий CalendarPattern, чистые алгоритмы подбора и ML-адаптеры. Процесс: оборудование → конфигурация → календарь → задание → предложение состава → подтверждение диспетчером → выполнение → приёмка инженером.

| Документ | Назначение |
|---|---|
| [SYSTEM_OVERVIEW](../SYSTEM_OVERVIEW.md) | Запуск и компоненты |
| [Рабочий процесс](../WORKFORCE_PLANNING.md) | Регистрация, оборудование, периоды, смены, допуски, бригады |
| [API](api_contracts.md) | Действующие endpoints, DTO и ошибки |
| [DTO/SQL](dto_db_mapping.md) | Фактические поля и преобразования |
| [Календарь](../algorithms/scheduling_rules.md) | Реальные кварталы/годы и ISO-недели |
| [Назначение](../algorithms/assignment_rules.md) | Ранжирование и ручной выбор |
| [BE05](../algorithms/assignment_persistence.md) | Транзакция и повторная проверка |
| [Границы](prototype_scope.md) | Объём и следующие функции |
| [Материал заказчика](customer_schedule_analysis.md) | Факты Excel и происхождение нормативов |
| [Сверка задач](../YOUGILE_TASK_CORRECTIONS.md) | Уточнения задач BE/FE/QA/AN |

Канонический контракт: [Python](contracts/maintenance_contracts.py), [JSON Schema](contracts/maintenance.schema.json), [примеры](contracts/examples.json). Код-источник: backend/app/schemas/maintenance.py; копия и схема обновляются совместно. Физический источник — database/migrations; ER-изображения показывают базовые 35 таблиц, расширения описаны в mapping.

repository_audit, architecture_validation и fx26-be01-implementation — исторические срезы. Последняя проверка: [flexible_planning_verification](../../reports/flexible_planning_verification.md). Архивный оценщик повреждений исключён.
