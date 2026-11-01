# Соответствие DTO и действующей PostgreSQL

Срез: `dev`, миграции 001–008. Физическая схема определяется SQL и reflection ORM,
не базовой картинкой ER. [Контракты runtime](api_contracts.md) и
[словарь](../domain/data_dictionary.md) описывают единые текущие значения.

| DTO / проекция | Хранение / точное преобразование |
|---|---|
| Site | `sites`; timezone IANA задаёт все местные даты |
| Equipment | `equipment`; `asset_code→inventory_code/inventoryCode`, `under_repair→out_of_service`; source API использует физические snake_case поля, UI — явную проекцию |
| OperationVersion | Устойчивый `operation_templates`; `operation_version_id=maintenance_rule_id`, `version=rule_version`; текст и IDs чек-листа фиксируются в `schedule_parameters.operation_metadata/checklist_ids` |
| RecurrenceRule | `maintenance_rules` и JSON `calendar_pattern/calendar_basis`; исходные `source_text/source_ref` сохраняются; quarter — календарный квартал, интервал 3 месяца — отдельный режим |
| Binding | `rule_equipment.binding_id/revision`, ссылки на конкретное оборудование, правило и редакцию; периоды действия пересекаются при расчёте |
| Норма / длительность | `norm_hours NUMERIC(12,3)`, `norm_hours_basis`, `schedule_parameters.norm_unit/planning_duration_minutes/duration_basis`; исходное значение не преобразуется без выбранной единицы |
| Calendar occurrence | `schedule_entries.binding_id/source_occurrence_id`, правило и снимок; генерация использует одно оборудование одной привязки; нормативная дата `regulatory_deadline_on` и исключающая верхняя граница `regulatory_deadline_at` |
| Task | `work_orders` + `work_order_equipment`, замороженные операция/длительность/допуски/чек-лист; ревизия и точный плановый интервал |
| Назначение | `work_assignments.start_at/end_at/qualification_snapshot/reason/released_at`; переназначение закрывает прежние строки и создаёт новые UUID |
| Сотрудник / роль | `users/site_memberships`; новые роли `admin/dispatcher/engineer/executor`, явная совместимость со старыми SQL ролями; ревизия и период работы |
| Смены / отсутствия | `employee_shift_rules` с общим CalendarPattern + `availability_slots`; ночные интервалы, DST, даты работы и недоступность учитываются до подбора |
| Бригада | `crews/crew_members`, ревизия, действительность каждого участника; отдельный работник не обязан состоять в бригаде |
| Регистрация | `site_join_codes/employment_applications`; случайный код допускает заявку, роль выдаёт администратор |
| ForecastSnapshot | Полный канонический снимок в `forecast_runs.input_snapshot`; одинаковые ID/hash/отсечка у двух методов |
| ForecastResult | `forecast_runs.method=rule/ai`; канонический результат в `output_snapshot.canonical`; `needs_input→insufficient_data` только на SQL-границе |
| OrchestrationDecision | `orchestration_decisions` с FK к двум результатам и каноническим решением; исходные предложения не переписываются |
| ExecutionReport / accepted history | `work_reports` с отдельными попытками и checklist_snapshot; `acceptance_reviews` и принятое completed_at; прошлый отчёт не редактируется сервисами |
| Фото / проверка | `evidence_files` привязаны к попытке, пункту, оборудованию, stage/view_key и SHA; `ai_quality_checks` фиксирует анализ, не приёмку |
| Идемпотентность генерации | `planning_runs` с site/key/request hash/response; уникальный source_occurrence_id и повторная проверка существующего обязательства |
| ErrorResponse | Формируется на HTTP-границе: schema_version/error/detail/request_id; не отдельная предметная таблица |

Базовые таблицы/картинки TL02 сохранены как описание исходного каркаса; новые
колонки и служебные таблицы добавляются только последующими миграциями.
Текущий код не использует старые имена `equipment_items/employees/brigades/maintenance_tasks`
как вторую модель данных. [Примеры](../domain/examples/operation_to_equipment_links.json)
валидируются теми же Pydantic-классами, что используются backend/ML.

## История и изменения

Новая настройка обслуживания создаёт новую редакцию/правило, фиксирует инструкцию
и чек-лист и завершает действие прежней привязки. Существующие задания не
перестраиваются молча; конфликтующая будущая работа требует явной отмены до начала
либо выбора более поздней даты настройки. Завершённая работа остаётся в истории.

Назначение, переназначение и отмена сериализуются через locks задания, пользователей
и метаданных. Изменение смен/допуска/роли не должно нарушать существующую бронь.
Сервисное API ограничивает все действия объектом сессии. Прямой SQL администратора
БД не подменяет публичный сервис и не является способом редактирования из веба.
