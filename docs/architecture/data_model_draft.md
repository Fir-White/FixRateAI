# Предварительная модель данных ТО/ППР

Дата: 26.10.2026. Статус: логическая модель для последующего согласования и проектирования БД. Имена ниже — целевые имена доменных сущностей, а не уже созданные таблицы. Типы API и перечисления — в [контрактах](api_contracts.md), правила переходов — в [архитектуре](system_architecture.md). Окончательные PK/FK, DDL, индексы и ER-диаграмма будут отдельной задачей.

## Пять раздельных уровней

| Уровень | Сущности | Смысл |
|---|---|---|
| Шаблон работы | Operation, OperationVersion, ChecklistItemVersion | Что именно выполнить и какие доказательства нужны |
| Периодичность и применимость | RegulationVersion, RecurrenceRule, EquipmentOperationBinding | Когда и к какому оборудованию применить конкретную версию |
| Плановое выполнение | CalendarPlan, PlanOccurrence, Task, Assignment | Одно вхождение в календарь и организация его выполнения |
| Фактическая попытка | ExecutionReport, ChecklistAnswer, PhotoReport | Что, кем и когда фактически сделано; повторная попытка хранится отдельно |
| Проверка и принятый факт | PhotoReviewResult, EngineerDecision, ServiceEvent | Рекомендация AI, решение человека и запись принятой истории |

Фотография, статус задания и принятие инженером не заменяют друг друга. `ServiceEvent` появляется только после принятия определённой попытки. История попыток шире принятой истории обслуживания.

## Доступ и справочники

| Сущность | Назначение и ключевые атрибуты | Основные связи |
|---|---|---|
| User | `user_id: UUID`, имя, уникальный email, password_hash, is_active, revision, created_at | M:N Role через UserRole; назначения, решения, аудит |
| Role / UserRole | Роли `admin/dispatcher/executor/engineer`; user_id + role_code | User имеет несколько ролей; разрешения проверяются сервером |
| UserSession | session_id, user_id, token_hash, csrf_hash, expires_at, revoked_at | N:1 User; секрет токена не хранится открыто |
| Site | site_id, name, address, timezone IANA, is_active | 1:N Equipment; M:N User через SiteMembership |
| SiteMembership | user_id, site_id, is_active | Ограничивает доступ к оборудованию, заданиям и фото по объекту |
| EquipmentType | equipment_type_id, code, name, description, is_active | 1:N Equipment; типовая применимость регламента |
| Equipment | equipment_id, site_id, equipment_type_id, inventory_code, name, commissioned_on?, state, revision | N:1 Site/Type; 1:N Binding, RuntimeReading, ServiceEvent. Уникальность инвентарного кода в Site |
| Qualification | qualification_id, code, name | M:N User через UserQualification; M:N OperationVersion через OperationQualificationRequirement |
| UserQualification | user_id, qualification_id, valid_from, valid_until?, document_ref, verified_by | Действует на весь интервал назначения; непроверенный документ не даёт допуск |
| AvailabilityInterval | availability_id, user_id, start_at, end_at, kind `available/absent`, revision | Смены и отсутствие; учитывается вместе с активными Assignment |

`state` Equipment: `active/out_of_service/retired`. Отсутствие работы оборудования не отменяет обязательный регламент само по себе: исключение подтверждает инженер. В v1 вывод из эксплуатации блокирует новые обычные задания до решения инженера, сохраняя историю и видимость обязательств.

## Регламент и происхождение

| Сущность | Назначение и ключевые атрибуты | Основные связи |
|---|---|---|
| SourceDocument | source_document_id, filename, sha256, storage_key, imported_at, source_kind, data_origin | 1:N OperationVersion/RecurrenceRule через ссылки на лист/ячейки; исходный Excel неизменяем |
| Operation | operation_id, стабильный code, is_active | 1:N OperationVersion; не содержит изменяемых исторических инструкций |
| OperationVersion | operation_version_id, operation_id, version, title, maintenance_type, instructions, crew_size, raw_norm_value, norm_unit, planning_duration_minutes?, status, source_ref, approved_by/at?, data_origin | 1:N ChecklistItemVersion; квалификации; N:M Equipment через Binding |
| ChecklistItemVersion | checklist_item_id, operation_version_id, order, text, answer_kind, unit?, required, visual_verifiability, photo_required | 1:N ChecklistAnswer; пункт новой версии получает новый ID |
| OperationQualificationRequirement | operation_version_id, qualification_id | Требования действуют на каждого участника бригады в v1 |
| Regulation / RegulationVersion | regulation_id, regulation_version_id, version, name, status, effective_from, supersedes_version_id?, source_document_id | 1:N Binding; подтверждённая версия неизменяема |
| RecurrenceRule | rule_version_id, regulation_version_id, source_text, kind, confirmed, interval?/calendar_unit?/anchor_date?/basis?, explicit_dates?, yearly_count?, runtime_interval_hours?, allowed_lead_days, source_ref | 1:N Binding; структура разных kind описана в контрактах |
| EquipmentOperationBinding | binding_id, equipment_id, operation_version_id, rule_version_id, regulation_version_id, effective_from/to?, baseline_runtime_hours?, revision | Соединяет одну версию операции, одно правило и оборудование; позволяет добавить оборудование к существующей операции |
| RuntimeReading | reading_id, equipment_id, measured_at, value_hours: Decimal, source, verified, meter_epoch | Снимки прогнозов и расчёт срока по наработке; сброс/замена счётчика начинается новым epoch |

`norm_unit`: `unconfirmed/person_hour/elapsed_hour`; это смысл исходного числа, не обязательная длительность бронирования. Для публикации инструкции допустима неуточнённая норма, но для назначения нужно отдельно подтверждённое `planning_duration_minutes > 0`. Сохраняется основание подтверждения. Значение `null` не заменяется нулём.

`status` версии операции/регламента: `draft/approved/retired`. Только approved применим к утверждаемым планам. `confirmed=false` у правила запрещает вычислять обязательный срок для реального назначения. Проект сохраняет исходную запись `1/квар`; нормализованные параметры появляются после решения аналитика/инженера.

В этой модели `RegulationVersion` объединяет подтверждённый набор привязок; членство операции в регламенте выражено Binding, отдельная дублирующая «операция регламента» не требуется в v1. При новом оборудовании создаётся Binding к существующей версии; при новой работе — Operation и OperationVersion. Изменение текста/чек-листа/частоты создаёт новые версии и новые действующие привязки, а не UPDATE исторического содержания.

## План и выполнение

| Сущность | Назначение и ключевые атрибуты | Основные связи |
|---|---|---|
| CalendarPlan | plan_id, site_id, period_start/end, status `draft/approved`, revision, created_by, approved_by/at? | 1:N PlanOccurrence; отображение месяца — запрос по диапазону дат |
| PlanOccurrence | occurrence_id, plan_id, binding_id, rule_version_id, occurrence_date, earliest_date, mandatory_due_date?, runtime_due_at_hours?, status `draft/planned/fulfilled/cancelled`, revision | 0..1 Task в v1; unique ключ вхождения. `overdue` — вычисляемый признак, не status |
| Task | task_id, occurrence_id, operation_version_id, state, revision, scheduled_start/end?, active_execution_id?, created_by, deadline_breached | 1:N Assignment, ExecutionReport; snapshot версии инструкции фиксируется при создании |
| Assignment | assignment_id, task_id, executor_id, start_at, end_at, status `active/released`, qualification_snapshot, assigned_by, released_at?, reason? | Одна строка на работника и интервал; повторное назначение создаёт новую запись |
| ExecutionReport | execution_id, task_id, attempt_number, state `draft/submitted`, performed_at?, submitted_at?, submitted_by, narrative, checklist_snapshot_hash | 1:N ChecklistAnswer, PhotoReport, PhotoReviewResult; 0..1 EngineerDecision. Уникально `(task_id,attempt_number)` |
| ChecklistAnswer | execution_id, checklist_item_id, status `done/not_done/not_applicable`, value?, unit?, comment?, completed_at? | Принадлежит пункту закреплённой OperationVersion; not_applicable требует основания и допуска шаблона |
| PhotoReport | photo_id, execution_id, checklist_item_id, equipment_id, phase `before/after`, view_key, storage_key, processed_storage_key, original_sha256, MIME, file_size_bytes, width/height, captured_at?, uploaded_at, uploaded_by | N:1 ExecutionReport; ссылка из AI-результата. Один набор фото не привязывается к другой попытке незаметно |
| EngineerDecision | decision_id, execution_id, engineer_id, verdict `accepted/rejected`, reason, decided_at, reviewed_ai_result_id?, additional_evidence_refs | Неизменяемое решение по конкретной отправленной попытке; engineer не исполнитель этой попытки |
| ServiceEvent | service_event_id, equipment_id, binding_id, occurrence_id, execution_id, engineer_decision_id, operation_version_id, performed_at, accepted_at, runtime_hours? | N:1 Equipment; уникально на принятую попытку и вхождение, источник следующего расчёта |

Дублирование equipment_id и operation_version_id в исторических записях допускается как проверяемая денормализация: сервер обязан сверять их с Task/Binding. Нельзя прикрепить фото другого оборудования, заключение к чужому отчёту или принять пункт от новой версии чек-листа.

В v1 одно вхождение имеет одно задание. Отклонение не создаёт второе конкурирующее задание для того же вхождения: новое назначение и попытка продолжают существующее Task. Группировка нескольких операций в одно задание оставлена за границей v1.

## Прогнозы, контроль и аудит

| Сущность | Назначение и ключевые атрибуты | Основные связи |
|---|---|---|
| ForecastRun | run_id, binding_id, snapshot_id, status `running/completed/failed`, started_at, expires_at, completed_at?, correlation_id | Один запуск сравнения, ровно два терминальных ForecastResult при завершении |
| ForecastSnapshot | snapshot_id, content_sha256, data_origin, as_of, horizon_end, equipment/binding/operation/rule versions, earliest_date, mandatory_due_date?, runtime_due_at_hours?, accepted_events, runtime_reading?, feature_schema_version | Неизменяемый вход обоих методов; ссылки плюс JSONB снимок фактических значений |
| ForecastResult | result_id, run_id, snapshot_id, method `algorithmic/ai`, status, method_version, model_ref?, recommended_date?, mandatory_due_date?, uncertainty, overdue, explanation, warnings, error_code?, elapsed_ms, data_origin | Две записи одной структуры, unique `(run_id,method)`; неуспех — тоже запись |
| OrchestrationDecision | orchestration_id, run_id, algorithmic_result_id, ai_result_id, status `selected/fallback/needs_input/manual_review`, selected_date?, policy_version, reasons, created_at | Ссылается на оба исходных результата и их общий снимок; не меняет их |
| ModelArtifact | model_ref, kind `forecast/photo_review`, model_version, file_sha256, dataset_sha256?, data_origin, feature/prompt schema, training_cutoff?, metrics, created_at | Выбирается настройкой, не загружается из произвольного пользовательского файла |
| PhotoReviewResult | ai_review_id, execution_id, status `completed/uncertain/not_verifiable/unavailable/failed`, model_ref, operation_version_id, input_photo_ids, item_results, limitations, elapsed_ms, created_at | N:1 ExecutionReport; EngineerDecision хранит конкретный использованный результат |
| AuditEvent | event_id, actor_type `user/system/ai`, actor_user_id?, entity_type/id, action, before/after_revision?, reason?, correlation_id, created_at | Append-only; бизнес-мутация и соответствующее событие фиксируются одной транзакцией |
| IdempotencyRecord | principal_id, route, key, payload_sha256, state, resource_id, expires_at | Повтор команды возвращает тот же ресурс; иной payload с прежним ключом → 409 |

`algorithmic` и `ai` — значения method, не разные таблицы с несовместимыми наборами полей. Аналогично model output хранится структурированно и с JSONB снимком для воспроизводимости; JSONB не заменяет внешние ключи к Run/Equipment/Execution. Фото и весовые файлы хранятся вне БД.

## Целостность и границы транзакций

| Инвариант | Предлагаемое обеспечение в следующей задаче БД | Проверка в приложении |
|---|---|---|
| Нет ссылок на чужое оборудование/версию/попытку | FK, при необходимости составные FK; RESTRICT для истории | DTO → сервис сверяет полный контекст |
| Повторная генерация не дублирует работу | UNIQUE ключа PlanOccurrence и Task.occurrence_id | Идемпотентный генератор |
| Прогнозы одного сравнения используют один снимок | FK + unique `(run_id,method)`, неизменяемый Snapshot | Совпадение snapshot/hash, as_of и происхождения |
| Все участники бригады свободны и квалифицированы | Транзакция с блокировкой строк User; исключающее ограничение интервалов рассматривается при проектировании DDL | Проверка допусков, site scope, смен, `crew_size`, длительности и занятости внутри блокировки |
| Нет гонки при смене статуса/назначении/приёмке | optimistic revision / блокировка Task | expected_revision обязателен, несоответствие → 409 |
| Приёмка создаёт ровно один принятый факт | Уникальность EngineerDecision.execution_id и ServiceEvent.occurrence_id, одна транзакция | Только submitted, engineer не исполнитель, frozen checklist и допустимое основание |
| Исторические данные не переписываются | Запрет UPDATE/DELETE принятых версий/отчётов/решений/аудита правами/триггерами будущей схемы | Новая версия или новая попытка вместо исправления старой строки |
| Счётчик не уменьшается незаметно | Число ≥ 0; индекс по equipment/epoch/time | Новое epoch при сбросе, timestamp не из будущего |
| Неизвестные нормы не превращаются в 0 | Nullable нормализованные поля, положительные CHECK для известных | Блокирующая ошибка до назначения |
| Поздняя дата AI не меняет регламент | Отдельные обязательная и рекомендованная даты | Общий deadline guard всех команд изменения плана/задания |

История позволяет восстановить: исходную ячейку Excel → версию операции/правила → привязку → вхождение → задание/назначения → попытку/фото → AI-заключение → решение инженера → принятый факт → снимок следующего прогноза. Изменение регламента не разрывает эту цепочку.

Новая схема создаётся в отдельной пустой БД. Использование `users`/`audit_events` из сметного проекта предполагает адаптацию структуры, а не совместное подключение к их старым таблицам. Конфликт архивных миграций и механизм новой цепочки описаны в [аудите](repository_audit.md) и [стеке](tech_stack.md).
