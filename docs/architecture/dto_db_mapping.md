# Соответствие DTO и ER-модели ТО/ППР

> Таблицы ниже сопоставляют DTO с исходным каталогом TL02 и являются историческим срезом; изменения SQL после этого среза и предложения по их согласованию описаны в [проекте TL03](../database/tl03_target.md). Отдельные пробелы закрыты миграциями 002–004; полного DTO round-trip пока нет.

> Обновление runtime 31.10.2026: миграции 005–006 добавляют ревизию/конец интервала
> задания и интервалы/снимки допусков/основания назначений. [BE05](../algorithms/assignment_persistence.md)
> сохраняет полный состав и возвращает канонические `Assignment[]`; неизвестные поля
> старых записей не заполняются догадками. Таблицы исторического среза ниже не переписаны.

**Срез:** 27.10.2026 · **Контракт:** `maintenance-0.1` · **ER:** `0.9-architecture-draft`  
**Статус:** техническая сверка и предложения для обсуждения, **не подтверждение согласования командой**.

Источники: [DTO backend](../../backend/app/schemas/maintenance.py), [REST-модели Яны](../../backend/app/schemas/maintenance_api.py), [спецификация БД](../database/specification.md), [каталог полей и FK](../database/model_catalog.json), [ER](../database/erd.drawio). При проверке `origin/main` и `origin/new_backend` 27.10.2026 эти два файла DTO совпадали; последний изменивший их коммит — `bb300ec`. Новую версию от Яны нужно сверить повторно, если она есть вне этих веток.

## Как читать таблицы

- **Прямо** — поле есть в указанной таблице; имена DTO и БД могут различаться.
- **JOIN / сборка** — данные берутся из нескольких записей, связанных FK; требуется сохранить контекст объекта и версии.
- **Вычисление / ввод** — поле является параметром запроса, значением протокола или результатом вычисления, а не самостоятельной колонкой.
- **Пробел** — в текущем каталоге нет достаточного хранения или однозначного преобразования. Возможные расширения ниже — предложения, не существующие поля БД.

Таблицы описывают логический путь между DTO и текущей проектной ER, а не уже реализованные SQLAlchemy-модели или API. JOIN не решает проблему, если необходимый идентификатор, версия либо историческое значение в схеме не сохранены. `NULL` нельзя заменять нулём, пустой строкой или произвольной датой.

### Общие поля и наследование

| DTO / поле | Таблица БД или источник | Преобразование / статус |
|---|---|---|
| `Versioned.schema_version` и наследующие его DTO | Протокол `maintenance-0.1` | Константа сериализатора; хранение каждой копии необязательно. Версия сохранённых JSON-снимков должна быть определена отдельно. |
| `Contract.data_origin`, `SourceRef.data_origin` | `regulation_documents.source_kind`, снимки | **Пробел:** источник документа не равен происхождению каждого объекта. Нужен надёжный, версионированный источник `customer` / `synthetic_demo` либо явная политика его наследования; не определять по наличию документа. |
| `SourceRef.source_ref` | `regulation_documents.source_uri`, снимки | **Пробел:** URI документа не содержит гарантированно ссылку на лист и диапазон ячеек конкретной версии записи. Сохранить точное значение и связь с документом; не восстанавливать его из предположений. |
| `OperationResponse`, `RecurrenceRuleResponse`, `AssignmentResponse`, `TaskResponse`, `ExecutionResponse` | Соответственно `OperationVersion`, `RecurrenceRule`, `Assignment`, `Task`, `ExecutionReport` | Наследуют все поля и ограничения базовых DTO; см. строки соответствующих классов ниже. |
| `Value`, `Versioned`, `Contract`, `ApiModel`, `SourceRef` | Базовые модели | У `Value` и `ApiModel` нет собственных полей. `schema_version`, `data_origin`, `source_ref` разобраны выше и не повторяются в каждой таблице. |

## Оборудование, операции и регламенты

| DTO | Поле | Таблица БД | Преобразование / статус |
|---|---|---|---|
| `Site` | `site_id`, `name`, `address`, `timezone` | `sites` | Прямо. В ER `address` допускает NULL, DTO требует строку: договориться об обязательности, не подставлять фиктивный адрес. |
| `Equipment`, `EquipmentCreate`, `EquipmentResponse` | `equipment_id`, `site_id`, `equipment_type_id`, `name`, `commissioned_on` | `equipment` | Прямо; `equipment_id` выдаётся сервером. |
| те же | `inventory_code` | `equipment.asset_code` | Прямое смысловое соответствие; уникальность внутри `site_id`. |
| те же | `state` | `equipment.status` | **Пробел:** `out_of_service` и `under_repair` не тождественны по смыслу. Утвердить состояния и преобразование. |
| `Equipment`, `EquipmentResponse` | `revision` | `equipment` | **Пробел:** версии строки в каталоге нет; требуется хранение и атомарное увеличение при изменении, если optimistic locking сохраняется в DTO. |
| `EquipmentCreate` | `state` | `equipment.status` | Вход создания; применить согласованное преобразование состояний. `source_ref` и `data_origin` в этой модели отсутствуют, хотя присутствуют в `EquipmentResponse`. |
| `ChecklistItem`, `ChecklistItemCreate` | `checklist_item_id`, `text`, `unit`, `required` | `checklist_templates.checklist_template_id`, `prompt`, `unit_code`, `is_required` | Прямо с переименованием. Для create ID выдаётся сервером. Версию пункта необходимо связывать с версией инструкции, а не только с изменяемым шаблоном. |
| те же | `answer_kind` | `checklist_templates.input_kind` | `boolean` ↔ `checkbox`, `number` ↔ `number`, `text` ↔ `text` — предлагаемый mapping; ER `photo` не имеет соответствия в перечислении DTO. |
| те же | `visual_verifiability`, `photo_required` | `checklist_templates` | **Пробел:** поля отсутствуют; добавить к версии пункта либо в типизированную версию инструкции, если потребители подтверждают эти требования. |
| `OperationVersion`, `OperationCreate` | `operation_id`, `code`, `title`, `instructions` | `operation_templates.operation_template_id`, `code`, `title`, `description` | ID и основные атрибуты — прямые кандидаты; `instructions` можно читать из `description` только после определения неизменяемой версии текста и обязательности. |
| те же | `operation_version_id`, `version` | `operation_templates`, `maintenance_rules` | **Пробел:** отдельной версии инструкции нет. `maintenance_rule_id` версионирует вместе периодичность и норму и не является автоматически ID версии операции. Нужен независимый идентификатор и версия содержимого либо согласованная и проверяемая составная модель версий. |
| те же | `maintenance_type` | `operation_templates.maintenance_type_id` → `maintenance_types.code` | JOIN по FK; сохранять код `ТО1` / `ТО2`. |
| те же | `crew_size`, `raw_norm_value` | `maintenance_rules.required_people`, `norm_hours` | JOIN через конкретную версию правила. В DTO норма nullable и допускает 3 знака; ER `NUMERIC(12,2)` и NOT NULL: не округлять и не заменять NULL нулём. |
| те же | `norm_unit`, `planning_duration_minutes`, `duration_basis` | `maintenance_rules.norm_hours_basis` | **Пробел:** `unknown` может обозначать неподтверждённую семантику, но `total_person_hours / per_person` не эквивалентны автоматически `person_hour / elapsed_hour`; длительность и её основание отдельно не сохранены. До согласования сохранять исходную норму без конверсии. |
| те же | `qualification_ids`, `checklist` | `rule_required_skills.skill_id`, `checklist_templates` | JOIN и сборка массива; состав навыков относится к версии правила, checklist в ER — к шаблону и его собственной версии. Нужна связь с неизменяемой версией операции. |
| те же | `status` | `maintenance_rules.publication_status`, `operation_templates.is_active` | **Пробел:** `draft / approved / retired` и `draft / published / archived` применяются к разным уровням. Не преобразовывать автоматически без согласования жизненного цикла версии инструкции. |
| `OperationCreate` | `operation_id` | `operation_templates.operation_template_id` | Необязательный вход для существующей операции; при создании новой сервер создаёт ID и проверяет контекст `site_id/system_id`. |
| `RegulationCreate`, `RegulationResponse` | `regulation_id`, `regulation_version_id`, `name`, `effective_from` | `regulation_documents.regulation_document_id`, `regulation_editions.regulation_edition_id`, `regulation_documents.title`, `regulation_editions.effective_from` | JOIN документа и редакции; сервер создаёт отсутствующие ID. |
| те же | `version`, `status`, `supersedes_version_id` | `regulation_editions.edition_code`, `is_approved` | **Пробел:** строковый `edition_code` не является гарантированно числовой версией; одного boolean недостаточно для `draft / approved / retired`; ссылки на предыдущую редакцию нет. Нужна политика версий, статусов и преемственности. |
| `RecurrenceRule`, `RecurrenceRuleCreate` | `rule_version_id`, `regulation_version_id` | `maintenance_rules.maintenance_rule_id`, `regulation_edition_id` | Прямой кандидат: одна строка ER — версия правила с конкретной редакцией; при изменении создаётся новая строка. ID выдаёт сервер. |
| те же | `source_text`, `source_ref` | `maintenance_rules.schedule_parameters`, документ | **Пробел:** отдельные поля для точной исходной строки и ссылки отсутствуют. Можно дополнить правило или определить обязательную версионированную структуру JSONB; ссылка должна сохраняться без потери координат. |
| те же | `kind`, `confirmed` | `maintenance_rules.scheduling_mode`, `publication_status` | **Пробел:** перечисления различаются, `confirmed` не эквивалентен автоматически `published`; режим `runtime` не предусмотрен CHECK. Уточнить значения и запретить неизвестные преобразования. |
| те же | `interval`, `calendar_unit`, `yearly_count` | `maintenance_rules.period_count`, `period_unit`, `occurrences_per_period` | Частичный mapping зависит от `kind`: квартал может быть 3 месяцами; годовой счёт хранит число вхождений. Не выводить конкретные даты из частоты. |
| те же | `anchor_date`, `basis`, `explicit_dates`, `runtime_interval_hours`, `allowed_lead_days` | `maintenance_rules.schedule_parameters` | **Пробел:** JSONB существует, но схема и ограничения для этих параметров не определены; runtime исключён текущими CHECK. Утвердить версионированную структуру или отдельное нормализованное хранение, сохраняя все поля и типы. |
| `EquipmentOperationBindingCreate`, `EquipmentOperationBindingResponse` | `equipment_id`, `rule_version_id`, `effective_from`, `effective_to` | `rule_equipment.equipment_id`, `maintenance_rule_id`, `valid_from`, `valid_to` | JOIN к правилу с `site_id/system_id`; `valid_from` в ER NOT NULL, а в запросе DTO допускается NULL — согласовать семантику. |
| те же | `operation_version_id`, `regulation_version_id` | `rule_equipment` → `maintenance_rules` → операция и `regulation_edition_id` | Редакция — JOIN; версия операции пока не имеет независимого ID. Проверять все переданные ссылки на одну комбинацию. |
| те же | `binding_id`, `revision`, `baseline_runtime_hours` | `rule_equipment` | **Пробел:** составной PK не равен отдельному UUID; revision и baseline отсутствуют. Требуется стабильный surrogate ID или согласованное изменение DTO, хранение revision и подтверждённого baseline. |

## Календарь и исполнение

| DTO | Поле | Таблица БД | Преобразование / статус |
|---|---|---|---|
| `CalendarQuery` | `site_id`, `year`, `month`, `include_cancelled` | `schedule_plans`, `schedule_entries` | Параметры запроса; фильтр по объекту и локальному месяцу. `include_cancelled` — фильтр, не хранится. |
| `CalendarResponse` | `site_id`, `year`, `month`, `timezone`, `items`, `total` | `schedule_plans`, `sites`, `schedule_entries` | `timezone` — JOIN `sites`; `items` — выбранные события; `total` — число возвращённых элементов. `schema_version` — константа. |
| `CalendarOccurrence` | `occurrence_id`, `occurrence_date`, `planned_task_id` | `schedule_entries.schedule_entry_id`, `planned_date`; `work_orders` | ID/дата прямо, задание — LEFT JOIN по `schedule_entry_id`. |
| тот же | `equipment_id`, `operation_version_id` | `schedule_entries` → `maintenance_rules` / `work_orders` → `work_order_equipment` | **Пробел:** у события нет привязки к оборудованию, пока не создан наряд; несколько устройств в наряде допустимы. Версия инструкции отдельно не хранится. Нужна однозначная связь события с binding и одной версией операции либо новое правило DTO. |
| тот же | `maintenance_type`, `recurrence`, `crew_size`, `raw_norm_value`, `norm_unit`, `planning_duration_minutes`, `source_ref` | Правило → шаблон → `maintenance_types`; источник и версия правила | JOIN и те же ограничения нормы, источника и периодичности, что у `OperationVersion` / `RecurrenceRule`. Исходное `1/день` / `1/квар` / `5/год` сохранить как текст; не восстанавливать по догадке. |
| тот же | `actual_execution_id`, `status` | `work_reports`, `acceptance_reviews`, `schedule_entries.status` | **Пробел:** несколько попыток отчёта; требуется определить, какую возвращать. `fulfilled` зависит от принятого отчёта и не входит в enum `schedule_entries`; предусмотреть вычисление без потери `superseded`. |
| `PlanOccurrence` | `occurrence_id`, `occurrence_date`, `mandatory_due_date`, `task_id` | `schedule_entries.schedule_entry_id`, `planned_date`, `regulatory_deadline_on`; `work_orders` | Прямо / LEFT JOIN. `planned_date` считается датой вхождения только при согласованной семантике. |
| тот же | `binding_id`, `rule_version_id`, `operation_version_id` | `schedule_entries.maintenance_rule_id`, привязка / версия операции | Rule ID — прямо; **пробел** идентификации binding и версии инструкции, как выше. |
| тот же | `earliest_date`, `runtime_due_at_hours`, `status`, `revision` | `schedule_entries.rule_snapshot`, `status` | **Пробел:** границы и revision отдельно не определены; значение можно вычислять только из сохранённой версии правила и согласованного источника. Семантику статусов нужно утвердить. |
| `Schedule` | `plan_id`, `site_id`, `status`, `revision`, `occurrences` | `schedule_plans`, `schedule_entries` | ID/site/revision прямо, массив — JOIN; ER `superseded` отсутствует в DTO, не отождествлять с draft. |
| тот же | `period_start`, `period_end` | `schedule_plans.period_year`, `period_month` | Для месячного плана — первый и последний локальный день месяца; DTO допускает произвольный диапазон, ER план ограничен месяцем. Согласовать разбиение диапазона и идентификаторы планов. |
| `Assignment`, `AssignmentResponse` | `assignment_id`, `task_id`, `executor_id`, `assigned_by` | `work_assignments.work_assignment_id`, `work_order_id`, `user_id`, `assigned_by` | Прямо с переименованием и проверкой `site_id`. |
| те же | `start_at`, `end_at`, `qualification_ids`, `status` | `work_assignments`, `user_skills`, `availability_slots` | **Пробел:** в assignment нет запланированного интервала и снимка допусков; текущие `user_skills` не восстанавливают состояние на момент назначения. Статусы ER шире двух статусов DTO; без отдельной политики преобразование потерь не гарантирует. |
| `Task`, `TaskResponse` | `task_id`, `occurrence_id`, `equipment_id`, `operation_version_id` | `work_orders`, `schedule_entries`, `work_order_equipment`, правило | JOIN; оборудование может быть множественным, ID версии операции отсутствует. DTO требует один `equipment_id` и `occurrence_id`, ER допускает внеплановые наряды. Согласовать границу scheduled v1. |
| те же | `state`, `revision`, `scheduled_start`, `scheduled_end` | `work_orders.status`, `planned_start_at` | **Пробел:** состояния ER и DTO различны; нет revision и конца интервала. Не подменять `in_review` фактом принятия или `clarification` состоянием draft. |
| те же | `assignment_ids`, `active_execution_id`, `deadline_breached` | `work_assignments`, `work_reports`, дедлайн наряда / отчёт | Массив — JOIN; **пробел:** выбор активной попытки и исторический факт нарушения дедлайна не определены. Текущее вычисление просрочки не заменяет сохранённый факт нарушения. |
| `ChecklistAnswer` | `checklist_item_id`, `value`, `unit`, `comment`, `completed_at`, `status` | `checklist_results.checklist_template_id`, `response_value`, `recorded_at` | ID прямо; **пробел:** форма `response_value` не определена. Зафиксировать типизированный JSONB status/value/unit/comment/completed_at; `recorded_at` не обязательно равно времени выполнения. |
| `ExecutionReport`, `ExecutionResponse` | `execution_id`, `task_id`, `attempt_number`, `submitted_at`, `submitted_by`, `narrative` | `work_reports.work_report_id`, `work_order_id`, `revision_no`, `submitted_at`, `submitted_by`, `comment` | Прямые кандидаты при условии, что `revision_no` обозначает именно отдельную попытку, а не редактирование той же попытки; DTO narrative обязательно, ER comment nullable. |
| те же | `state`, `performed_at`, `answers`, `photo_ids` | `work_reports.status`; `checklist_results`; `evidence_files` | Массивы — JOIN по отчёту; **пробел:** `performed_at` отсутствует, `reviewed` в ER не является состоянием DTO. Нельзя брать время приёмки или отправки вместо фактического выполнения. |
| `ExecutionListResponse` | `items`, `total`, `limit`, `offset` | `work_reports` | Выборка и пагинация; `total` — полный размер выборки, может быть больше `len(items)`. `schema_version` — протокол. |
| `AssignmentCommand` | `expected_revision`, `executor_ids`, `start_at`, `end_at`, `reason` | `work_orders`, `work_assignments`, аудит | Вход команды, не отдельная таблица. Сверить revision, проверить всех исполнителей и записать назначения атомарно; revision, интервал и причина в ER явно не хранятся. |
| `ReviewCommand` | `expected_revision`, `execution_id`, `verdict`, `reason`, `reviewed_ai_result_id`, `additional_evidence_refs` | `work_orders`, `acceptance_reviews`, `ai_quality_checks` | Команда проверки и записи решения; хранение недостающих полей и проверка принадлежности к попытке описаны ниже в `EngineerDecision`. |
| `RolePermissions` | `role`, `permissions` | `site_memberships.role`; `ROLE_PERMISSIONS` в backend | Permissions — вычисление из политики, не отдельное поле ER. **Пробел:** роль ER (`executive/chief_engineer/engineer/technician`) и DTO (`admin/dispatcher/executor/engineer`) различаются; не назначать права по догадке. |

## Снимок, два прогноза и оркестратор

| DTO | Поле | Таблица БД | Преобразование / статус |
|---|---|---|---|
| `AcceptedEvent` | `service_event_id`, `performed_at`, `accepted_at`, `runtime_hours`, `observed_need_date` | `work_reports`, `acceptance_reviews`, `work_readings` | **Пробел:** отдельного `ServiceEvent` и стабильного ID нет; фактическое время выполнения и observed need не определены. `accepted_at` может быть `acceptance_reviews.reviewed_at` только для принятой попытки. Показания должны иметь заданную семантику и единицу. |
| `RuntimeReading` | `reading_id`, `measured_at`, `value_hours`, `meter_epoch`, `verified` | `work_readings.work_reading_id`, `measured_at`, `numeric_value`, `unit_code` | ID/время/значение — возможное соответствие для подтверждённого часового счётчика; **пробел:** нет `meter_epoch` и `verified`, существующий `is_estimated` им не равен. |
| `ForecastSnapshot` | `snapshot_id`, `content_sha256`, `binding_id`, `binding_revision` | `forecast_runs.input_snapshot` | **Пробел:** единая сущность снимка, её ID/hash и binding revision не определены. Копии JSON в двух результатах не обеспечивают идентичность; нужен неизменяемый общий снимок и проверяемая ссылка обоих результатов. |
| тот же | `site`, `equipment`, `operation`, `rule` | `sites`, `equipment`, шаблон/версия операции, `maintenance_rules`, общая фиксация входа | Сборка до запуска; сохранить **значения на `as_of`**, а не перечитывать изменённые текущие записи. Отдельной версии операции пока нет. |
| тот же | `as_of`, `horizon_end`, `earliest_date`, `mandatory_due_date`, `runtime_due_at_hours`, `accepted_events`, `runtime_reading`, `feature_schema_version` | `input_snapshot` | **Пробел:** JSONB допускает хранение, но контракт структуры, ID, hash, ограничения и источники значений не определены. Нужны обязательная версия схемы и доказуемое единое содержимое для двух методов. История не должна содержать будущих событий. |
| `Uncertainty` | `kind`, `lower_date`, `upper_date`, `calibrated`, `note` | `forecast_runs.output_snapshot` | **Пробел:** структура output JSONB не определена. Сохранить объект целиком и проверить допустимость границ; `tree_dispersion` не является калиброванной вероятностью. |
| `ForecastResult` | `result_id`, `equipment_id` | `forecast_runs.forecast_run_id`, `equipment_id` | Прямые кандидаты; ER допускает NULL оборудования, DTO требует ID. `forecast_run_id` здесь ID **результата метода**, а не DTO `run_id`. |
| тот же | `run_id`, `snapshot_id`, `snapshot_sha256`, `binding_id`, `as_of` | `forecast_runs.input_snapshot` | **Пробел:** нет общего ID запуска сравнения и ссылок на один снимок/привязку. Требуется общий неизменяемый контекст; две несвязанные строки forecast_runs недостаточны. |
| тот же | `method`, `method_version`, `model_ref` | `forecast_runs.method`, `predictor_versions.version`, `artifact_ref` | `algorithmic` ↔ `rule`, `ai` ↔ `ai` — предлагаемое обратимое преобразование. JOIN по `predictor_version_id`; сохранить версию и ссылку артефакта на момент запуска. Для `ai/ok` DTO требует `model_ref`. |
| тот же | `status` | `forecast_runs.status` | `ok`, `unavailable`, `failed` совпадают; `needs_input` в DTO и `insufficient_data` в ER требуют согласования, они не автоматически равнозначны. Неудачные результаты сохраняются с NULL датой и причиной. |
| тот же | `recommended_date`, `mandatory_due_date` | `proposal_at`, `regulatory_deadline_at`; `sites.timezone` | Timestamp → локальная дата через timezone объекта. Обратное преобразование date → timestamp неоднозначно: согласовать правило границы суток и отдельно сохранить исходные значения; не выдумывать время. |
| тот же | `runtime_due_at_hours`, `overdue`, `uncertainty`, `warnings`, `error_code`, `elapsed_ms` | `output_snapshot` / общий snapshot | **Пробел:** версии и обязательная структура JSONB не определены; `overdue` требуется восстанавливать на `as_of`, а не пересчитывать по текущим часам. |
| тот же | `explanation` | `forecast_runs.rationale` | Прямой кандидат; проверить ограничение непустого текста DTO. |
| `OrchestrationDecision` | `orchestration_id`, `algorithmic_result_id`, `ai_result_id`, `created_at` | `orchestration_decisions.orchestration_decision_id`, `rule_forecast_id`, `ai_forecast_id`, `created_at` | Прямо с переименованием и составными FK по объекту/системе/правилу. Дополнительно проверять метод, оборудование, binding и общий snapshot двух результатов. |
| тот же | `run_id`, `snapshot_id` | Связи результатов / общий snapshot | **Пробел:** текущая ER не задаёт общего запуска и снимка. JOIN по правилу и объекту недостаточен для проверки одного входа. |
| тот же | `status`, `selected_date`, `policy_version`, `reasons` | `selected_method`, `selected_at`, `predictor_versions`, `reason`, `comparison_snapshot` | `selected_method` не равен DTO status; `needs_input` не представлен. Дата требует правила локальной зоны; policy version — JOIN по `orchestrator_version_id`; массив причин не восстанавливается из одной строки без определённой структуры. Сохранить статус и причины явно либо в версионированном JSONB. |

Оба метода используют **один** [ForecastResult](../../backend/app/schemas/maintenance.py), включая `method`, `equipment_id`, `recommended_date`, `method_version`, `model_ref`, `status`, `uncertainty`, `explanation` и общий snapshot. Предложенный пример с `predicted_date`, `confidence`, `model_version` — иллюстрация, а не действующая модель. `forecast_runs.confidence` в ER nullable, но прямого поля `confidence` в текущем DTO нет; числовая оценка не считается вероятностью. Не переименовывать `recommended_date` и не вводить новое поле без решения Яны и Артёма и обновления схемы/примеров.

Для невозможности смешения результатов требуется проверка **одного объекта, оборудования, binding, rule version, snapshot ID/hash и запуска**; также один метод должен быть `algorithmic`, другой `ai`. Текущие составные FK решения проверяют объект, систему и правило, но не обеспечивают совпадение оборудования и снимка. Предпочтительная доработка — один неизменяемый snapshot и запуск сравнения, ссылки результатов на них и ограничения уникальности метода в запуске; допустимый вариант с JSONB требует явной схемы и механизмов проверки. Окончательный вариант — на согласование с DB/backend/ALG.

## Фото, AI-проверка и приёмка

| DTO | Поле | Таблица БД | Преобразование / статус |
|---|---|---|---|
| `PhotoReport` | `photo_id`, `execution_id`, `phase`, `mime_type`, `file_size_bytes`, `original_sha256`, `captured_at`, `uploaded_at`, `uploaded_by` | `evidence_files.evidence_file_id`, `work_report_id`, `stage`, `mime_type`, `file_size`, `sha256`, `captured_at`, `uploaded_at`, `uploaded_by` | Прямо с переименованием; `stage` в ER шире `before/after` DTO, выдавать только поддержанные фото. `work_report_id` в ER nullable, DTO требует конкретную попытку. |
| тот же | `equipment_id`, `checklist_item_id`, `view_key`, `width`, `height` | `evidence_files`, `work_order_equipment`, `checklist_results` | **Пробел:** в `evidence_files` нет ни одной из этих привязок/характеристик; JOIN по наряду не определяет конкретное оборудование, пункт и ракурс при нескольких вариантах. Необходимо надёжное хранение и проверка принадлежности к версии отчёта. |
| тот же | `content_url` | `evidence_files.evidence_file_id` | Генерируется сервером по ID и маршруту, не из пользовательского `storage_key`; доступ проверять по объекту и заданию. |
| `PhotoReviewRequest` | `execution_id`, `operation`, `photos`, `report`, `prompt_set_version` | `work_reports`, версия операции, `evidence_files`, версия prompt | Вход AI формируется из замороженной отправленной попытки и её фото. `prompt_set_version` в текущих таблицах явно не определён; текущий запрос сам по себе не является сохраняемой сущностью. |
| `ImageLabelScore` | `photo_id`, `label`, `score` | `ai_quality_checks.findings` | **Пробел:** JSONB `findings` не задаёт обязательную структуру и FK фото. Нужны versioned schema, ссылки и проверка принадлежности каждой фотографии к попытке. |
| `ItemPhotoReview` | `checklist_item_id`, `verdict`, `before_photo_id`, `after_photo_id`, `observation`, `scores` | `ai_quality_checks.findings`, `evidence_files` | **Пробел:** `findings` не определяет структуру по пунктам; пара FK на уровне `ai_quality_checks` представляет только одну пару фото, а DTO допускает результат для каждого пункта. Выбрать типизированный JSONB или дочернюю таблицу и проверить все связи. |
| `PhotoReviewResult` | `ai_review_id`, `execution_id`, `model_ref`, `created_at` | `ai_quality_checks.ai_quality_check_id`, `work_report_id`, `predictor_versions.artifact_ref`, `created_at` | ID/отчёт прямо; model_ref — JOIN по `predictor_version_id`; `artifact_ref` nullable и должна соответствовать версии модели. |
| тот же | `operation_version_id`, `status`, `prompt_set_version`, `input_photo_ids`, `item_results`, `limitations`, `error_code`, `elapsed_ms` | `ai_quality_checks`, `findings` | **Пробел:** отдельной версии операции и согласованной схемы findings нет; статусы DTO шире ER `ok/inconclusive/failed`; только двух колонок фото недостаточно для списка. Сохранить сведения о входах, промпте, результатах и ограничениях без потерь. |
| `EngineerDecision` | `decision_id`, `execution_id`, `engineer_id`, `reason`, `decided_at` | `acceptance_reviews.acceptance_review_id`, `work_report_id`, `reviewer_user_id`, `comment`, `reviewed_at` | Прямые кандидаты; `comment` в ER nullable, `reason` в DTO обязателен. |
| тот же | `verdict`, `reviewed_ai_result_id`, `additional_evidence_refs` | `acceptance_reviews.decision`, `ai_quality_checks` | **Пробел:** ER различает `accepted/rework/rejected`, а DTO — `accepted/rejected`; ссылка на рассмотренный AI-результат и дополнительные доказательства не хранятся. Не сводить разные решения к одному без согласования. |

Составные FK фото и AI-проверки сейчас проверяют объект и наряд, но ссылки `before_file_id` / `after_file_id` не включают `work_report_id`; при двух попытках одного наряда это не доказывает принадлежность к одной попытке. Нужны составные FK по `(site_id, work_order_id, work_report_id, evidence_file_id)` с совместимым UNIQUE и семантикой NULL либо транзакционная проверка с эквивалентными гарантиями. Проверка этапа `before/after`, версии пункта, оборудования и ракурса также должна быть явной.

## Протокольные ошибки

| DTO | Поле | Таблица БД | Преобразование / статус |
|---|---|---|---|
| `ErrorDetail` | `field`, `issue` | Нет обязательного хранения | Формируется при обработке ошибки из результата валидации; не раскрывать чужие данные. |
| `ErrorInfo` | `code`, `message`, `details`, `request_id` | Нет обязательного хранения | HTTP envelope; `request_id` генерируется/принимается сервером. Для аудита correlation ID нужно отдельное определённое хранение, текущий `audit_events` его не содержит. |
| `ErrorResponse` | `schema_version`, `error` | Нет обязательного хранения | Версия протокола и вложенный `ErrorInfo`. Ошибки не являются доменными записями. |

## Проверка шести операций заказчика

| Код | Вид ТО | Исходная частота | Работников | Норма | Сопоставление |
|---|---|---|---:|---:|---|
| `1.1` | `ТО1` | `1/день` | 1 | 1 | template + тип + правило + исходный текст/ссылка |
| `1.2` | `ТО1` | `1/день` | 1 | 1 | то же |
| `1.3` | `ТО1` | `1/день` | 1 | 1 | то же |
| `1.4` | `ТО2` | `5/год` | 2 | 60 | то же; точные даты и смысл нормы не подтверждены |
| `1.5` | `ТО2` | `1/квар` | 1 | 48 | то же; anchor и basis не подтверждены |
| `1.6` | `ТО2` | `1/квар` | 1 | 30 | то же; anchor и basis не подтверждены |

Источник: [анализ Excel с координатами](customer_schedule_analysis.md). Это **ручная сверка покрытия**, а не выполненный round-trip через API/БД: в каталоге ER ещё нужно определить точное хранение исходной частоты, ссылки на ячейку и неподтверждённой нормы. В DTO для неподтверждённого значения используется `norm_unit=unconfirmed`; в ER `norm_hours_basis=unknown` сохраняет неопределённость о базе нормы, но не доказывает единицу `person_hour` или `elapsed_hour`. Год графика, точные даты и трактовку 60 нормо-часов не выдумывать. 93 отметки ТО1 октября — исходные отметки, а не записи выполненных работ.

## Решения для согласования до миграций

| Приоритет | Что требует решения | Предложение для обсуждения | Участники |
|---|---|---|---|
| P0 | Версия операции, rule и binding ID | Сохранить независимую неизменяемую версию инструкции и стабильный binding ID/revision; оставить нормализованные связи к ER. Выбрать, как разделить правило и версию операции. | Яна, архитектор БД |
| P0 | Происхождение, нормативы, ссылки на Excel | Сохранить точный `source_ref`/`source_text` и `data_origin` на соответствующей версии; поддержать `NUMERIC(12,3)` и NULL нормы, подтверждённую длительность/основание отдельно. Формат и миграция существующих данных обсуждаются отдельно. | Яна, архитектор БД, аналитик |
| P0 | Периодичность и календарь | Утвердить `kind`/параметры, вариант runtime и общую версию JSONB либо нормализованные таблицы; привязать событие к конкретному binding, уточнить произвольный диапазон Schedule и статусы. | Яна, архитектор БД, Артём |
| P0 | Общий снимок и результаты | Определить единый snapshot ID/hash, run ID, два результата и ссылки решения на них; предусмотреть все статусы, причины, версии и отказ AI. `confidence` nullable только в отдельном согласованном расширении. | Яна, архитектор БД, Артём |
| P0 | Фото и конкретная попытка | Обеспечить принадлежность фото, пункта и AI-проверки одной попытке/оборудованию; определить хранение нескольких пар, размеров, ракурса и ограничений. | Яна, архитектор БД |
| P0 | История и concurrency | Хранить фактическое время выполнения, revision, интервалы назначения и неизменяемые версии; определить служебные записи и полученный ServiceEvent. | Яна, архитектор БД |
| P0 | Роли и статусы | Совместно утвердить права и переходы, в том числе `rework`/`rejected`, без неявного преобразования. | Яна, аналитик, архитектор БД |
| P1 | Представление клиенту | После решений выпустить примеры и контракт API; frontend получает DTO, а не читает таблицы напрямую. | Михаил Видякин, Яна |

До явного решения эти пункты остаются открытыми: рекомендации не доказывают согласие участников и не меняют `erd.drawio`, `model_catalog.json`, Pydantic или данные заказчика. После решения следует синхронно обновить ER, спецификацию и каталог; если изменится DTO — также JSON Schema и fixtures, а затем реализовать и проверить SQLAlchemy/Pydantic-преобразование в задаче backend.
