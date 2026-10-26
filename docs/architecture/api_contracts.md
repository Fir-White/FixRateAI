# Контракты взаимодействия maintenance-0.1

Дата: 26.10.2026. Статус: первоначальная спецификация для параллельной разработки модулей; перечисленные endpoints ещё не реализованы. Новый контракт изолирован от сметного `schema_version=1.0`; универсального адаптера между предметными областями нет.

## Канонические артефакты и общие правила

- [Pydantic 2 DTO](contracts/maintenance_contracts.py) задают полный перечень обязательных полей, вложенные типы, перечисления и часть межполевых проверок.
- [JSON Schema Draft 2020-12](contracts/maintenance.schema.json) содержит определения `$defs`; конкретное сообщение валидируется по фрагменту `#/$defs/Equipment`, `#/$defs/ForecastResult` и т. д. Корневая схема — каталог определений, а не универсальное сообщение.
- [examples.json](contracts/examples.json) содержит самостоятельные JSON-сообщения с полями `name`, `contract`, `payload`. Все примеры — `synthetic_demo`; UUID, hashes фото и файлы изображают формат, а не существующие ресурсы сервера.
- [Валидатор артефактов](validate_artifacts.py) проверяет примеры, связанные ID/версии/даты, выбранную дату, согласованность schema, ссылки и диаграммы. Pydantic model validators содержат семантические проверки, не полностью выражаемые JSON Schema; одной проверки схемы для приёмки работы недостаточно.

Во всех DTO `schema_version` обязателен и равен `maintenance-0.1`. `data_origin=customer/synthetic_demo` обязателен для предметных DTO; отсутствует у команд и HTTP error envelope. Происхождение назначает сервер при импорте/подготовке demo, а не обычный пользователь произвольным полем. Все поля, объявленные без default, обязательны даже если их значение допускает `null`. Неизвестные поля отклоняются (`extra=forbid`). Отсутствие данных — `null` или явный статус, а не пустая дата, нулевой срок или выдуманный процент уверенности.

| Тип/величина | Передача | Хранение/правило |
|---|---|---|
| Идентификатор | UUID string | PostgreSQL UUID; server-generated у новых ресурсов |
| Локальная дата | `YYYY-MM-DD` | DATE, относится к Site.timezone |
| Момент времени | ISO 8601 с `Z` или offset, например `2026-10-26T12:00:00+05:00` | TIMESTAMPTZ; naive timestamp отклоняется |
| Часовой пояс | IANA string | Например `Asia/Yekaterinburg`; проверить существование |
| Наработка/норма | Decimal как JSON string, например `"120.500"` | NUMERIC, до 3 десятичных знаков, не IEEE float; час — 60 минут |
| Длительность бронирования | Положительный integer в минутах | Отдельна от исходных нормо-часов |
| Размер фото/разрешение | Integer: bytes, pixels | ≤10 485 760 bytes, ≤20 000 000 pixels |
| Model label score | number `[0,1]` | Относительная оценка класса, не вероятность правильного выполнения |
| SHA-256 | 64 строчных hex символа | Hash оригинального файла либо канонического снимка |
| Revision | Integer ≥1 | При каждой мутации агрегата увеличивается; команда несёт expected_revision |

`mandatory_due_date` включительна: последняя допустимая дата в Site.timezone. `earliest_date` — начало разрешённого окна. Интервалы назначений `[start_at,end_at)`; полночь после due уже за пределами срока. `overdue` рассчитывается относительно `as_of`; для UI текущая просрочка пересчитывается отдельно. `deadline_breached` сохраняет факт нарушения в восстановительной работе.

Версия формата отделена от `method_version`, `policy_version`, версии операции/правила и model revision. Изменение обязательного поля или enum требует новой версии контракта и одновременного обновления обоих потребителей. Пока интерфейсы не реализованы, изменение этого draft допустимо только вместе со schema, fixtures и зависимыми документами.

## Предметные структуры

Таблица поясняет смысл полей; точный полный набор обязательных свойств и типов содержится в одноимённых `$defs` и Pydantic-классах.

| Контракт | Ключевые поля и связи | Статусы и специальные правила |
|---|---|---|
| Site | site_id, name, address, timezone, происхождение | Точка определения локальных суток |
| Equipment | equipment_id, site_id, equipment_type_id, inventory_code, name, commissioned_on nullable, revision | `state=active/out_of_service/retired`; номер уникален в Site |
| OperationVersion | operation_id/version_id, version, code/title, maintenance_type `ТО1/ТО2`, instructions, crew_size, raw_norm_value, norm_unit, planning_duration_minutes, duration_basis, qualification_ids, checklist, source_ref | `status=draft/approved/retired`; известная duration требует основания. `norm_unit=unconfirmed/person_hour/elapsed_hour` |
| RecurrenceRule | rule_version_id, regulation_version_id, source_text, kind, confirmed, interval/unit/anchor/basis, explicit_dates, yearly_count, runtime_interval_hours, allowed_lead_days | `kind=calendar_interval/explicit_dates/runtime`; для каждого вида несовместимые поля пусты; неполные параметры допустимы только при confirmed=false |
| Schedule / PlanOccurrence | plan_id/site_id, period_start/end, revision, occurrences; у вхождения ID, binding/rule/operation versions, occurrence_date, earliest_date, mandatory_due_date, runtime_due_at_hours, task_id | Plan `draft/approved`; occurrence `draft/planned/fulfilled/cancelled`; `overdue` не статус |
| ForecastSnapshot | snapshot_id/hash, binding_id/revision, вложенные Site/Equipment/OperationVersion/Rule, as_of, horizon_end, earliest_date, mandatory_due_date, runtime_due_at_hours, accepted_events, runtime_reading, feature_schema_version | Один неизменяемый снимок для двух методов; происхождение всех вложенных объектов совпадает; нет событий после as_of |
| ForecastResult | result/run/snapshot/equipment/binding IDs, hash, as_of, method/version/model_ref, status, recommended_date, обязательные дата/порог, overdue, uncertainty, explanation, warnings, error_code, elapsed_ms | **Одна структура** для `method=algorithmic/ai`. `status=ok/needs_input/unavailable/failed`; ok требует дату, остальные — null дату и error_code |
| OrchestrationDecision | orchestration_id, run/snapshot IDs, оба result_id, selected_date, policy_version, reasons, created_at | `selected/fallback` требуют дату; `needs_input/manual_review` требуют null. Сервис дополнительно проверяет окно/deadline и совпадение обоих снимков |
| Assignment | assignment_id, task/executor IDs, start_at/end_at, qualification_ids, assigned_by | `active/released`; строка на каждого участника бригады, не одна строка с неструктурированным списком |
| Task | task/occurrence/equipment/operation_version IDs, state, revision, scheduled_start/end, assignment_ids, active_execution_id, deadline_breached | `draft/assigned/in_progress/submitted/rework_required/accepted/cancelled`; сроки и assignees сверяются с Assignment |
| ExecutionReport | execution/task IDs, attempt_number, state, performed_at/submitted_at, submitted_by, narrative, answers, photo_ids | `draft/submitted`; отправленный отчёт заморожен. Answer `done/not_done/not_applicable`, значение соответствует answer_kind и unit шаблона |
| PhotoReport | photo/execution/equipment/item IDs, phase, view_key, MIME, bytes, width/height, original_sha256, captured/uploaded_at, uploaded_by, content_url | `phase=before/after`; content_url — авторизованный маршрут, не путь диска. Оригинал не заменяется JPEG-копией при проверке hash |
| PhotoReviewRequest | execution_id, operation, photos, report, prompt_set_version | Только submitted попытка; фото относятся к этой попытке/оборудованию/версии пунктов. Байты получает storage adapter по photo_id |
| PhotoReviewResult | ai_review/execution/operation_version IDs, status, model_ref, prompt_set_version, input_photo_ids, item_results, limitations, error_code, elapsed_ms, created_at | `completed/uncertain/not_verifiable/unavailable/failed`; verdict пункта `visible_change/no_visible_change/uncertain/not_verifiable`. Нет общего `approved=true` от AI |
| EngineerDecision | decision/execution/engineer IDs, verdict, reason, reviewed_ai_result_id nullable, additional_evidence_refs, decided_at | `accepted/rejected`; неизменяемый серверный результат. reason обязателен в обоих случаях, при uncertain/недоступном AI указывает основание ручной оценки |

ChecklistItem содержит `answer_kind=boolean/number/text`, `required`, `unit`, `visual_verifiability=visible/partial/not_verifiable`, `photo_required`. Сервер при submit проверяет все обязательные пункты, их единицы и доказательства; одна успешная Pydantic-десериализация этого не гарантирует.

### Минимальный пример различия двух прогнозов

Ниже сокращённые проекции; полные валидные сообщения находятся в `examples.json`.

```json
{
  "algorithmic": {"method": "algorithmic", "status": "ok", "recommended_date": "2026-11-01"},
  "ai": {"method": "ai", "status": "ok", "recommended_date": "2026-10-29"},
  "orchestrator": {"status": "selected", "selected_date": "2026-10-29"}
}
```

В полном примере общий snapshot имеет окно 26.10–01.11.2026. При AI-дате 03.11 исходный AI-result сохраняет 03.11, а решение выбирает 01.11 с `AI_AFTER_DEADLINE`. При недоступном AI поле recommended_date равно null, uncertainty.kind=`unknown`, error_code=`MODEL_NOT_READY`; итог fallback содержит алгоритмическую дату. Уменьшение даты не должно выводить работу раньше earliest_date.

## Frontend ↔ backend

Базовый префикс: `/api/v1/maintenance`. Идентификаторы, audit principal, server timestamps и data_origin в ответах устанавливает сервер. Команды не принимают engineer_id/assigned_by/submitted_by как способ сменить пользователя.

| Метод / относительный путь | Запрос | Ответ / доступ |
|---|---|---|
| POST `/session` | email:string, password:string | 200 профиль user_id/name/roles/site_ids, csrf_token, expires_at; HttpOnly session cookie. Неверный вход 401 |
| GET / DELETE `/session` | Cookie; DELETE требует CSRF | 200 профиль / 204 отзыв |
| GET `/equipment` | site_id?, state?, limit 1..100, offset≥0 | 200 `{items:Equipment[],total,limit,offset}`; доступ к Site |
| POST `/equipment` | site_id, equipment_type_id, inventory_code, name; commissioned_on nullable | 201 Equipment; dispatcher/admin |
| GET / PATCH `/equipment/{id}` | PATCH: expected_revision и изменяемые name/state | 200 Equipment; mutation dispatcher/admin, история не переписывается |
| GET / POST `/operations` | POST: поля OperationVersion без server IDs/version/status/source origin; создаёт draft | 200 список / 201 OperationVersion; записи dispatcher/admin, утверждение engineer |
| POST `/operations/{id}/approve` | operation_version_id, expected_version, reason | 200 approved OperationVersion; engineer; новая правка создаёт следующую draft-версию, устаревшая expected_version → 409 |
| POST `/schedule-imports` | multipart xlsx, выбранный год для preview | 201 `{import_id,status:"draft",source_sha256,operations,diagnostics}`; dispatcher/admin; диагностические поля указывают ячейки, не домыслы |
| POST `/bindings` | equipment_id, operation_version_id, rule_version_id, regulation_version_id, effective_from | 201 binding_id/revision; engineer/dispatcher, только подтверждённая комбинация для планирования |
| POST `/plans/generate` | site_id, period_start/end, binding_ids | 200 Schedule preview; только разрешённый горизонт ≤366 дней, dispatcher |
| POST `/plans/{id}/approve` | expected_revision, reason | 200 Schedule; engineer; неполные правила → 422 |
| GET `/schedule` | site_id, from, to | 200 Schedule[]; локальные даты обязательного вхождения и запланированный интервал задания показываются отдельно |
| POST `/comparisons` | binding_id, horizon_end | 201 `{run_id,snapshot,algorithmic:ForecastResult,ai:ForecastResult,decision:OrchestrationDecision}`; dispatcher/engineer; as_of задаёт сервер |
| GET `/comparisons/{run_id}` | — | 200 тот же terminal результат; незавершённый запуск — 202 `{run_id,status:"running",expires_at}`, повторное чтение после expires_at завершает аварийный запуск |
| POST `/tasks` | occurrence_id, expected_occurrence_revision | 201 Task(draft); dispatcher, UNIQUE occurrence |
| GET `/tasks` / `/tasks/{id}` | state?, mine?, site_id?, пагинация | 200 Task/список; executor видит свои задания, остальные — в разрешённом Site |
| POST `/tasks/{id}/assign` | AssignmentCommand: expected_revision, executor_ids, start_at, end_at, reason | 200 `{task,assignments:Assignment[]}`; dispatcher; проверка всей бригады в одной транзакции |
| POST `/tasks/{id}/start` | expected_revision | 200 `{task,execution:ExecutionReport}`; назначенный executor. Первый draft отчёт содержит пункты not_done |
| PATCH `/executions/{id}` | expected_task_revision, narrative, answers | 200 draft ExecutionReport; назначенный executor до отправки |
| POST `/executions/{id}/photos` | multipart file, checklist_item_id, phase, view_key, captured_at? | 201 PhotoReport; executor своей активной попытки |
| GET `/photos/{id}/content` | Cookie и доступ к Site/Task | 200 безопасные bytes; 404 для недоступного ресурса без раскрытия чужих ID |
| POST `/executions/{id}/submit` | expected_task_revision, performed_at | 200 `{task,execution}`; executor, проверка обязательных пунктов/фото. Факт выполненного времени не из будущего |
| POST `/executions/{id}/ai-review` | expected_task_revision | 201 PhotoReviewResult; engineer/dispatcher, только frozen submitted |
| POST `/tasks/{id}/review` | ReviewCommand: expected_revision, execution_id, verdict, reason, reviewed_ai_result_id, additional_evidence_refs | 201 `{decision:EngineerDecision,task,service_event_id:UUID or null}`; engineer, запрет собственной приёмки |
| POST `/tasks/{id}/cancel` | expected_revision, reason | 200 Task(cancelled); dispatcher, только draft/assigned |
| GET `/equipment/{id}/history` | limit, offset | 200 принятые ServiceEvent и связанные решения; попытки/назначения доступны в истории задания, без потери отклонённых |
| GET `/qualifications`, `/executors/availability` | site_id и диапазон времени | 200 справочник/интервалы/действующие допуски; dispatcher/engineer. Управление начальными данными — seed администратора v1 |

Формы списков единообразны: `{items:[...],total:int,limit:int,offset:int}`. Фильтры не расширяют site scope. Указанные кратко команды получают отдельные входные DTO при реализации API; приведённые response DTO и AssignmentCommand/ReviewCommand уже специфицированы машинно. Состав backend OpenAPI сверяется с этим документом перед подключением UI.

Для POST создания ресурсов, сравнения, назначения, submit и review обязателен `Idempotency-Key` (UUID string). Ключ учитывает principal и маршрут; повтор с тем же payload возвращает прежний результат/ресурс, с иным payload — `409 IDEMPOTENCY_CONFLICT`. Операции с revision требуют сверки независимо от ключа; повтор уже выполненной команды по тому же ключу возвращается до новой проверки revision. Срок хранения ключей для demo — минимум 24 часа и не меньше времени активного выполнения команды.

Все мутации, включая multipart и DELETE session, требуют `X-CSRF-Token`; `X-Request-ID` принимается после ограничения длины/символов либо генерируется сервером и возвращается в ответе. Отдельный request_id HTTP не равен task_id или run_id.

## Backend ↔ алгоритмы / AI / оркестратор

| Граница | Вход | Выход | Отказ |
|---|---|---|---|
| Backend → algorithmic | ForecastSnapshot | ForecastResult(method=algorithmic) | needs_input: нет правила/anchor/истории; failed: вычислительная ошибка |
| Backend → forecast_ai | Тот же ForecastSnapshot | ForecastResult(method=ai) | unavailable: нет модели/достаточных признаков/таймаут; failed: невалидный выход |
| Backend → orchestrator | snapshot + algorithmic ForecastResult + ai ForecastResult | OrchestrationDecision | Чужой snapshot/hash → ошибка контракта; нерешённый норматив → needs_input; просрочка → manual_review |
| Backend → подбор бригады | operation_version, интервал, кандидаты с site scope/квалификациями/доступностью | Ранжированные executor_id и причины | Пустой список с reason; окончательная запись всё равно повторно проверяет ограничения |
| Backend → photo_ai | PhotoReviewRequest; доверенный loader bytes(photo_id) | PhotoReviewResult | Плохие фото uncertain, скрытая операция not_verifiable, нет модели/таймаут unavailable |

Границы — Python-вызовы, не обязательные HTTP endpoints. AI/алгоритмы не получают Session, SQL credentials или возможность менять Task. Все ресурсы загружаются backend по проверенным ID; URL от пользователя не скачивается моделью. Таймаут/авария адаптера превращается в валидный терминальный ForecastResult/PhotoReviewResult с diagnostic code и сохраняется. Параметры бюджета — в архитектуре.

`ForecastSnapshot.content_sha256` вычисляется как SHA-256 UTF-8 JSON снимка **без поля content_sha256**, с сортировкой ключей, separators `,`/`:`, `ensure_ascii=False`, включая порядок списков. Даты/Decimal сначала сериализуются теми же DTO; список принятых событий упорядочен по performed_at и ID. При повторном чтении используется сохранённый снимок, а не актуальные ORM-связи. В result копируется этот hash и обязательные границы; модели не могут подменять норматив своим ответом.

## Backend ↔ PostgreSQL

REST/AI DTO не являются SQL-протоколом. `repository` отображает UUID → UUID, date → DATE, aware datetime → TIMESTAMPTZ, Decimal → NUMERIC, enums → ограниченный набор значений; photo bytes остаются в storage. `content_url` вычисляется для ответа и не сохраняется как физический ключ. Password hash, session hash и storage_key не сериализуются в Equipment/Photo DTO.

| DTO | Сохраняемые сущности | Обязательная проверка сервиса |
|---|---|---|
| Equipment, OperationVersion, RecurrenceRule | Одноимённые сущности и дочерние ChecklistItem/requirements | Версии/источник, принадлежность Site, сохранение raw норм |
| Schedule | CalendarPlan + PlanOccurrence | Полнота правила, unique вхождения, разрешённый период |
| ForecastSnapshot + два ForecastResult + OrchestrationDecision | ForecastRun, Snapshot, Result×2, Decision | Общий input/hash и происхождение, версии, атомарная фиксация результатов |
| Task + Assignment[] | Task и строки назначений | crew_size, права/допуски/время, блокировка работников, expected_revision |
| ExecutionReport + PhotoReport | Отчёт, ответы, метаданные/ключи файлов | Одна попытка/версия/оборудование, upload-компенсация при отказе БД |
| PhotoReviewResult | Структурированные результаты + неизменяемый JSONB output snapshot | Ссылки на исходные photo_id, версию модели и prompt set |
| EngineerDecision | Решение + Task + ServiceEvent + AuditEvent в одной транзакции | submitted, engineer не исполнитель, основание, unique принятого факта |

Ограничения БД проектируются следующей задачей по [модели данных](data_model_draft.md). `Base.metadata.create_all()` не используется. Схема сама не определяет квалификацию работника, допустимость основания или истинность фотографии: это сервисные проверки и решение инженера.

## Ошибки и состояния неполноты

HTTP-ошибка имеет ErrorResponse (сохранён подход старого error envelope):

```json
{
  "schema_version": "maintenance-0.1",
  "error": {
    "code": "DEADLINE_EXCEEDED",
    "message": "Дата задания выходит за обязательный срок обслуживания.",
    "details": [{"field": "scheduled_end", "issue": "must finish before local midnight after 2026-11-01"}],
    "request_id": "demo-request-1"
  }
}
```

| HTTP | Коды | Поведение клиента |
|---|---|---|
| 401 / 403 | UNAUTHORIZED / FORBIDDEN | Вход/недостаточно прав; повтор от другого principal не автоматический |
| 404 | NOT_FOUND | Ресурс отсутствует или недоступен в scope |
| 409 | STALE_REVISION, STALE_SNAPSHOT, IDEMPOTENCY_CONFLICT | Обновить состояние, показать конфликт; не затирать данные отчёта |
| 409 | DEADLINE_EXCEEDED, BEFORE_ALLOWED_WINDOW, INVALID_TRANSITION | Не менять срок/статус, показать основание отказа |
| 409 | INSUFFICIENT_CAPACITY, QUALIFICATION_MISMATCH, ASSIGNMENT_CONFLICT | Нет допустимой бригады/интервала; предложить другой интервал в пределах срока |
| 413 / 415 | PAYLOAD_TOO_LARGE / UNSUPPORTED_MEDIA_TYPE | Исправить файл, фото не считается загруженным |
| 422 | VALIDATION_ERROR, RULE_UNCONFIRMED, DURATION_UNCONFIRMED, EVIDENCE_INCOMPLETE, UNIT_MISMATCH | Указать поля/ячейки; пользователь должен уточнить данные |
| 503 | DB_UNAVAILABLE, STORAGE_UNAVAILABLE | Остановить мутацию, повтор с прежним idempotency key после восстановления |
| 500 | INTERNAL_ERROR | Correlation ID для диагностики, без traceback/секретов в ответе |

Отсутствие AI-модели — **содержательный результат** unavailable в успешном 201 сравнения, а не ошибка HTTP всего планирования. Если БД не сохранила результаты, успешный ответ не возвращается. HTTP 504 допустим только для невозможности завершить сам запрос, а не как замена сохранённому результату отсутствующего AI.

Политические и межресурсные ограничения (deadline, crew_size, права, действительность допуска, версии, полнота чек-листа) не исчерпываются JSON Schema. Их транзакционные проверки обязательны даже для сообщения, прошедшего контрактный валидатор.
