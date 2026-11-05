# PostgreSQL, данные и история

## Дополнение 009: исходные даты и доказательства

Текущая цепочка — 001–009: 41 прикладная таблица и `fixrate_schema_migrations`, всего 42. Принятые 001–008 не изменены. Новая `009_analyst_workflows.sql` добавляет `maintenance_notifications`, исходный день `schedule_entries.source_date` с уникальностью `(site_id, binding_id, source_date)`, фазу `work_readings.phase`, фактический контекст `work_reports.execution_context`, контекст проверки `evidence_files.verification_context`, `work_orders.overdue_since_at` и `exception_context`.

Вновь созданные обязательства сохраняют исходный день отдельно от эффективной даты. Несколько перенесённых на понедельник дней имеют разные устойчивые IDs и последовательности, в том числе через границу месяца. Старые записи с source_date=NULL не переименовываются; их прежние даты и история сохраняются. Повторное создание сравнивает исходный день и повторно использует существующее обязательство.

Протокол измерений хранится в work_readings; сканы актов — в существующем приватном файловом хранилище evidence_files, без бинарных данных в JSON. Моменты выполнения, отправки и приёмки разделены. История приёмки содержит её фактическое основание, AI-результат и проверенные акты; повторное открытие не удаляет прежнюю попытку. Уведомления имеют устойчивый event_key и адресата внутри объекта. Новая схема проверяется отдельно на чистой БД и при обновлении непустой истории; рабочая БД не используется как тестовая.

Назначение: хранить происхождение, регламенты, календарь, занятость и неизменяемые факты выполнения. Код: [SQL 001–008](../../database/migrations), [ORM и репозитории](../../backend/app/db). SQL — источник фактического DDL; reflection не создаёт таблицы.

## Проверка развёртывания и истории QA03

04.11.2026 исправлены тесты развёртывания; применённые SQL 001–008 не менялись. Базовый [test_maintenance_schema.sql](../../tests/sql/test_maintenance_schema.sql) проверяет 35 исходных PK и 29 отрицательных случаев; обработка запрета удаления истории учитывает restrict_violation и foreign_key_violation. [test_runtime_schema.sql](../../tests/sql/test_runtime_schema.sql) проверяет полную схему, 41 прикладной PK без ledger, новые поля/индексы и 26 отрицательных сценариев с точным SQLSTATE. Вместе с fixrate_schema_migrations физически присутствует 42 таблицы.

[test_maintenance_history_upgrade.sql](../../tests/sql/test_maintenance_history_upgrade.sql) сохраняет исходные поля восьми непустых таблиц истории до upgrade и сравнивает их после 005–009; добавление новых колонок допустимо, изменение/потеря прежних значений отвергаются. Проверяется сохранение старого назначения при переназначении. По умолчанию SQL-фикстуры откатываются; qa03_keep_fixtures=true применяется runner только в собственной изолированной базе для проверки заполненного upgrade.

[scripts/verify_schema.ps1](../../scripts/verify_schema.ps1) и [scripts/verify.py](../../scripts/verify.py) проверяют независимую чистую 001–009, заполненный upgrade и повтор мигратора/seed. Существующая БД проекта не удаляется и не используется. Отдельные mutation-контроли подтвердили, что изменение forecast snapshot и снятие CHECK действительно ломают проверки; восстановленный вариант проходит. [Протокол QA03](verification.md#04112026-исправление-qa03-и-полный-успешный-прогон-dev), [команда изолированной проверки](runtime.md#изолированная-проверка-sql-без-запуска-рабочего-приложения), [общая сводка изменений](verification.md#04112026-сводка-изменений-в-dev).

## Словарь текущей системы

## Объект, оборудование и обслуживание

| Сущность | Физическое хранение | Смысл |
|---|---|---|
| Объект | `sites` | Область доступа и часовой пояс IANA |
| Инженерная система | `engineering_systems` | Контур внутри объекта |
| Тип / экземпляр оборудования | `equipment_types`, `equipment` | Инвентарный код уникален внутри объекта; у экземпляра есть ревизия |
| Операция | `operation_templates` | Устойчивый идентификатор вида работы |
| Редакция и правило | `regulation_documents`, `regulation_editions`, `maintenance_rules` | Версия инструкции, периодичности, нормы, длительности и требований |
| Привязка | `rule_equipment` | Правило конкретного оборудования с периодом действия и ревизией |
| Календарный план / обязательство | `schedule_plans`, `schedule_entries` | Нормативный день, выбранная дата, снимок правила и устойчивый ID |
| Задание | `work_orders`, `work_order_equipment` | Одно выполнение операции на оборудовании, отдельное от календарного расчёта |
| Прогноз / решение | `forecast_runs`, `orchestration_decisions` | Два исходных результата на одном снимке и объяснение выбора |

Версия операции в каноническом снимке определяется ID `maintenance_rules`;
текст инструкции и IDs чек-листа фиксируются в `schedule_parameters` конкретной версии.
Изменение настройки создаёт новое правило. Сохранённые задания и отчёты не переписываются.

## Сотрудники и время

`users` — учётная запись. `site_memberships` — роль, доступ и период работы в объекте.
Регистрация создаёт `employment_applications`; доступ появляется после выдачи роли
администратором. Роли: `executive`, `chief_engineer`, `engineer`, `executor`, `dispatcher`, `admin`.
`executive` и `chief_engineer` не сводятся к admin/engineer; только прежний `technician`
адаптируется в executor. Совместимый dispatcher сохраняет оперативные права.

`crews` и `crew_members` задают постоянные бригады и даты участия. Работник может
назначаться отдельно. Бригада не создаёт доступность и не бронирует время сама по себе.
`employee_shift_rules` задаёт регулярные смены. `availability_slots` — отдельные
рабочие интервалы или отсутствия; недоступность вычитается из доступности.
Ночная смена заканчивается на следующих сутках. Интервалы ограничиваются датами
работы сотрудника. Неоднозначное/несуществующее местное время при переходе DST
не угадывается; такой интервал блокируется с диагностикой.

`skills/user_skills` — допуски, проверка и срок действия. `work_assignments` —
фактически подтверждённые назначения с точным временем и снимком допусков.
Подбор учитывает занятость человека в других объектах без раскрытия чужих заданий.
Изменение смен/доступа/допусков, нарушающее действующее назначение, отклоняется.

## Единый календарь и единицы

Даты — `YYYY-MM-DD` в часовом поясе объекта. Точные моменты — ISO 8601 с UTC-offset,
в SQL — `timestamptz`. Интервалы полуоткрытые `[start,end)`: соседние смены/задания
могут стыковаться. Нормативная дата включает целые местные сутки; её техническая
верхняя граница — полночь следующего дня, но карточка показывает исходную дату.

`CalendarPattern`: дни, недели, месяцы, календарные кварталы, годы, число раз за год
или список дат. Дни недели ISO: 1=понедельник, 7=воскресенье. Чётность определяется
номером ISO-недели, а не номером недели внутри месяца. Интервал в две недели
от опорного понедельника и фильтр чётности ISO — разные явно выбираемые режимы.
Кварталы: январь–март, апрель–июнь, июль–сентябрь, октябрь–декабрь.

`raw_norm_value` — исходное десятичное значение. `person_hour` означает суммарные
человеко-часы; `elapsed_hour` — часы одновременной работы состава. Длительность
`planning_duration_minutes` задаётся отдельно. Значение 60 не превращается
автоматически в 60 минут или 30 часов бригады. Для расчёта даты достаточно
календарного правила; для назначения необходимы длительность и полный состав.

## Статусы и подтверждения

SQL задания: `draft/clarification/assigned/in_progress/in_review/rework/completed/cancelled`.
UI: `draft/assigned/in_progress/submitted/rework_required/accepted/cancelled`;
`clarification→draft`, `in_review→submitted`, `rework→rework_required`, `completed→accepted`.
Просрочка — отдельный признак, не замена состояния. Приёмка создаёт принятую историю;
отметка в календаре не означает выполнение.

Система предлагает состав с приоритетом по раннему общему времени и дневной загрузке.
Диспетчер может выбрать другой полный состав, проверить его и подтвердить назначение.
При сохранении BE05 снова проверяет время, допуски, доступность и ревизию в транзакции.
Автономного назначения нет. Для отмены не начатого задания нужен отдельный запрос
диспетчера с причиной; история и прежние назначения сохраняются.

## Схема и миграции

Физическая схема — SQL в `database/migrations`, а не картинка ER и не `metadata.create_all()`. Сохраняются 35 исходных доменных таблиц. В 005 добавлены таблица серверных сессий, поля runtime и поддержка канонических ролей. CLI дополнительно создаёт служебный реестр `fixrate_schema_migrations`.

| Группа | Основные таблицы и правила |
|---|---|
| Доступ | `sites`, `users`, `site_memberships`; активность пользователя, членства и объекта проверяется при каждом запросе |
| Оборудование | `engineering_systems`, `equipment_types`, `equipment`, навыки/бригады/доступность; составные FK удерживают объект и систему |
| Регламенты | `operation_templates`, `regulation_documents`, `regulation_editions`, `maintenance_rules`, `rule_equipment`, `checklist_templates`; идентификатор привязки и revision из 002 |
| Календарь | `schedule_plans`, `schedule_entries`; независимая нормативная дата, версии и уникальность вхождений из 003 |
| Исполнение | `work_orders`, `work_assignments`, `work_order_equipment`, `work_reports`, `checklist_results`, `work_readings`, `evidence_files`, `acceptance_reviews` |
| ML и аудит | `predictor_versions`, `forecast_runs`, `orchestration_decisions`, `ai_quality_checks`, `audit_events` |

001 создаёт исходную схему, 002 добавляет плановые контракты и аудит, 003 — уникальность непривязанных вхождений, 004 — точность нормы `NUMERIC(13,3)` и согласование правила наряда с вхождением. Составной FK 004 остаётся `NOT VALID` для старых данных: он защищает новые записи, но существующие строки необходимо отдельно проверить перед `VALIDATE CONSTRAINT`. Интеграция не меняет это условие незаметно.

005 добавляет положительную `revision` оборудования и заданий, `work_reports.checklist_snapshot`, привязки фото к пункту/ракурсу/оборудованию, контекст решения инженера, уникальный email без учёта регистра и серверные сессии. Старые `under_repair`, `in_review`, `rework`, `completed` сохраняются физически; UI показывает соответственно `out_of_service`, `submitted`, `rework_required`, `accepted`. `clarification` отображается как черновик; исходное SQL состояние не переписывается.

006 добавляет сохранённый конец интервала задания и интервалы/снимки допусков/основания назначений, заменяет уникальность участника частичной уникальностью текущего состава. Старые значения и история сохраняются, новые поля старых записей остаются NULL. Переназначение закрывает старые строки и создаёт новые UUID. [Транзакция, блокировки и миграция BE05](planning.md).

007 добавляет `planning_runs` и уникальный `source_occurrence_id`: задание, два прогноза, решение и сохранённый идемпотентный ответ записываются атомарно. 008 добавляет период трудоустройства/ревизии, `employee_shift_rules`, `site_join_codes` и `employment_applications`; мигратор сохраняет checksum в собственном реестре. Полный каталог расширений находится ниже.

Нормы заказчика с неизвестной единицей не превращаются в продолжительность. В проекции `scheduledEnd=null`, если конец не сохранён. API чтения не угадывает `data_origin`; без metadata показывает «Источник не указан». Публичный low-level DTO mapper из `kran_dev` по-прежнему отклоняет неоднозначные отображения — этот контракт не ослаблен ради SPA.

CLI миграций использует advisory lock, транзакцию на файл и SHA-256 нормализованного SQL. Успешно применённые версии повторно не запускаются. Проверка checksum блокирует изменение уже применённого SQL. Новые изменения требуют следующего номера миграции.

Для **новой** базы:

```powershell
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m app.manage migrate
```

Для существующей проектной базы с **полностью применёнными 001–004**, после резервной копии и проверки исходной схемы:

```powershell
.\.venv\Scripts\python.exe -m app.manage migrate --adopt-existing
```

Это явное принятие оператором ответственности за предыдущую SQL-цепочку, не автоматический импорт произвольной БД. CLI проверяет основные ORM-признаки 004, затем регистрирует 001–004 и применяет 005–008. До 004 обновляйте в исходном порядке; с другой схемой нужна отдельная миграция. Дубли email, различающиеся только регистром, остановят 005 и должны быть разобраны до повторного запуска. Для базы с реестром применённых 001–006 достаточно обычного `app.manage migrate`, затем перезапуска backend. Обновление локального рабочего стенда выполняется явно, с резервной копией и проверкой сохранности истории.

## Соответствие DTO и таблиц

Срез: `dev`, миграции 001–008. Физическая схема определяется SQL и reflection ORM,
не базовой картинкой ER. [Контракты runtime](backend.md) используют значения словаря выше.

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
как вторую модель данных. [Примеры](../../tests/fixtures/domain/operation_to_equipment_links.json)
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

## Нормативная и фактическая история

Цепочка происхождения: ячейка Excel → версия операции/правила → привязка к оборудованию → вхождение календаря → задание и назначения → попытка и фото → заключение AI → решение инженера → принятый факт → следующий снимок прогноза. Плановая отметка и отправленный отчёт не создают принятую историю. Изменения инструкций создают новые версии. Новая попытка не перезаписывает отклонённую. Сброс счётчика требует отдельного epoch, отсутствие показания не равно нулю.


## Каталог сущностей

Ниже назначение всех 35 базовых таблиц. Формулировки «неизменяемая история»/«append-only» обозначают сервисный жизненный цикл; отдельного запрета UPDATE/DELETE для администратора БД схема не вводит.

| Таблица | Назначение |
|---|---|
| `sites` | Физические объекты эксплуатации, единица разграничения доступа и нормативных графиков. |
| `users` | Учётные записи людей; глобальный пользователь может иметь разные роли на объектах. |
| `site_memberships` | Роль и активность пользователя на конкретном объекте; основа RBAC и назначения. |
| `engineering_systems` | Инженерная система объекта: теплоснабжение, ХВС, ГВС, ЖБО и т. д. |
| `equipment_types` | Классификатор типов оборудования и комплектующих. |
| `equipment` | Узлы и конкретные единицы оборудования с паспортом и иерархией. |
| `skills` | Справочник допусков и компетенций персонала. |
| `user_skills` | Подтверждённые квалификации сотрудника для конкретного объекта. |
| `availability_slots` | Дополнительные доступные интервалы и исключения недоступности. Бронь задания хранится отдельно в work_assignments. |
| `crews` | Именованные бригады сотрудников для выполнения многопользовательских работ. |
| `crew_members` | История состава бригады; связь сотрудника и бригады во времени. |
| `maintenance_types` | Классы ТО: ТО1, ТО2 и расширяемые типы. |
| `operation_templates` | Шаблон строки регламента, например «1.1 Контроль параметров ...». |
| `regulation_documents` | Реквизиты исходного документа заказчика или нормативного регламента. |
| `regulation_editions` | Неизменяемые редакции регламентов с периодами действия. |
| `maintenance_rules` | Версионированное правило: какой шаблон работ и как часто выполнять. |
| `rule_equipment` | Привязка любого количества единиц оборудования к одной строке ТО. |
| `rule_required_skills` | Перечень обязательных компетенций для назначения сотрудников на регламент. |
| `schedule_plans` | Снимок месячного графика для объекта с версионированием утверждений. |
| `schedule_entries` | Одна строка календарного факта планирования, а не отдельная колонка дня месяца. |
| `incident_reports` | Сообщения о выявленных неисправностях с текстом и ссылками на узел. |
| `work_orders` | Наряд-задание на одну регламентную или внеплановую операцию. |
| `work_order_equipment` | Снимок множества обслуживаемых единиц по конкретному наряду. |
| `work_assignments` | Индивидуальное назначение каждого техника на работу; бригада — необязательный контекст. |
| `checklist_templates` | Версионируемый пункт обязательных действий и показаний для операции. |
| `work_reports` | Каждая попытка отправки отчёта исполнителем; предыдущие попытки не затираются. |
| `checklist_results` | Снимок ответов на чек-лист для версии отчёта. |
| `work_readings` | Фактические показания приборов с происхождением и единицами. |
| `evidence_files` | Фотофайлы и другие подтверждения, привязанные к наряду и редакции отчёта. |
| `acceptance_reviews` | Неизменяемые решения инженера по отдельным редакциям отчёта. |
| `predictor_versions` | Реестр версий алгоритмического, ML- и визуального модуля. |
| `forecast_runs` | Общий контракт результатов rule-based и AI-прогнозирования с фиксированным контекстом. |
| `orchestration_decisions` | Агентный выбор допустимого срока после сравнения двух прогнозов и проверки регламента. |
| `ai_quality_checks` | Результат анализа визуально подтверждаемых изменений; не заменяет приёмку инженером. |
| `audit_events` | Append-only журнал изменений состояния, нормативов, назначений и решений. |

После 005–008 существуют также:

| Таблица | Назначение |
|---|---|
| `fixrate_sessions` | Хеши отзываемых session/CSRF token, пользователь/объект и срок сессии; используется явным SQL |
| `planning_runs` | Идемпотентный запуск генерации и сохранённый ответ, unique `(site_id,idempotency_key)` |
| `employee_shift_rules` | Повторяющиеся смены/недоступность, CalendarPattern, local time, период и ревизия |
| `site_join_codes` | Один код регистрации на объект |
| `employment_applications` | Pending/accepted/rejected-заявки, решение администратора и ревизия |
| `fixrate_schema_migrations` | Технический реестр применённых SQL и checksum; создаётся мигратором |

Полная новая установка содержит 42 таблицы с учётом уведомлений, сессий и реестра миграций. ORM отражает базовые таблицы и доступные расширения (`planning_runs`, смены, код, заявки, уведомления); сессии и реестр обслуживаются явным SQL.

## Поля, ключи и ER

[Машинный каталог](../../database/schema/model_catalog.json) сохраняет все 310 полей базовой модели с типами, nullable/default, описаниями, PK/UNIQUE/CHECK/индексами и 72 FK. Для точной схемы текущей версии читать [миграции 001–008](../../database/migrations): каталог и [ER draw.io](../assets/database/erd.drawio)/[SVG](../assets/database/erd.svg) описывают базовую версию 0.9 и не переэкспортировались как актуальная схема 008. [Экспорт SVG](../../scripts/export_erd.py) работает с исходным draw.io.

Основные цепочки: Site → EngineeringSystem → Equipment; OperationTemplate → MaintenanceRule → RuleEquipment; SchedulePlan → ScheduleEntry → WorkOrder; WorkAssignment → WorkReport → ChecklistResult/EvidenceFile → AcceptanceReview. ForecastRun хранит каждый из двух методов, OrchestrationDecision ссылается на оба. AIQualityCheck относится к конкретной попытке отчёта; решение инженера хранится отдельно.

`operation_version_id`/`rule_version_id` runtime DTO соответствуют `maintenance_rule_id`; отдельной таблицы OperationVersion/ServiceEvent нет. Метаданные версии операции и ID чек-листа сохраняются в `schedule_parameters`; наряд и попытка закрепляют свои JSON-снимки. История AcceptedEvent выводится из принятого решения и `work_orders.completed_at`, см. [backend](backend.md).

## Где обеспечивается целостность

- Составные FK удерживают объект/систему/правило/оборудование/отчёт в одном контексте; optional FK с MATCH SIMPLE при NULL не доказывает заполненность всей бизнес-связи. Контекст дополнительно проверяет сервис.
- План хранит строки DATE, а не колонки дней. Базовые unique keys вхождений различают binding и unbound; 007 добавляет unique source_occurrence, а `work_orders(site_id,schedule_entry_id)` препятствует второму заданию на то же сохранённое вхождение. Разные версии/месячные ревизии сверяет генератор.
- 004 сохраняет прежний диапазон нормы и три десятичных знака, добавляет составной `fk_work_orders_entry_rule NOT VALID`: новые записи проверяются, старые нарушения не удаляются. Перед VALIDATE нужен отдельный разбор прежних строк.
- 006 закрывает прежние назначения, не удаляя ID/время/основание/снимки допусков. Частичный unique запрещает повтор действующего участника одного задания. Межзаданные и межобъектные пересечения работников предотвращает общая сервисная блокировка, а не SQL exclusion constraint.
- 002 пишет before/after audit для операций, правил, привязок, планов и вхождений. Явные сервисные события назначения/выполнения/приёмки добавляются в той же транзакции. Аудит не запрещает администратору БД прямую запись и сам по себе не делает таблицу immutable.
- Ревизии, разрешённые переходы, статус принятия, срок допуска, полная бригада, frozen checklist и запрет self-review проверяются сервисом. DB CHECK не заменяет эти межстрочные проверки.
- Norm unit и точная длительность задаются отдельно. `person_hour` уже означает суммарные человеко-часы; `elapsed_hour` умножается на crew_size только для расчёта трудоёмкости. Длительность брони не выводится делением исходного числа на людей.

## Демонстрационные данные

После миграций `001`–`004` из корня репозитория:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/seeds/001_customer_schedule_demo.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/seeds/001_customer_schedule_demo.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/sql/005_demo_seed.sql
```

Тест загружает seed дважды и оставляет демонстрационные записи в базе. Используйте отдельную тестовую базу. Проверка выполнена на PostgreSQL 18.6 в однопользовательском режиме; для PostgreSQL 16 отдельно не проверялась. Seed рассчитан на выделенные им идентификаторы и коды `DEMO-*`; повторный запуск не обновляет уже изменённые записи (`ON CONFLICT DO NOTHING`), кроме перехода исходного демо-отчёта из `submitted` в `reviewed` при обновлении ранее загруженного seed. При конфликте с посторонними данными используйте чистую базу: seed не является механизмом синхронизации или восстановления изменённых значений.

Источник: `data/customer/techical_service_schedule.xlsx`, лист `Лист1`, B6:F11. Названия, типы ТО, текст периодичности, число людей и значения колонки «Нормо-часы» сохранены из книги. Документ связан с SHA-256; правила остаются `draft`, `data_origin=customer`, основание нормы `unknown`. Единицы и смысл нормы требуют подтверждения; длительность не выводится. `5/год` и `1/квар` не задают конкретные даты. Дата начала правил и редакции — демонстрационная, не дата заказчика. В книге октябрь без года; seed не выдаёт демонстрационный 2026 год за год заказчика и не создаёт календарные назначения.

Объект, инвентарные единицы, даты ввода, исполнители, инженер, привязки, выполненная работа, показание, замечания, отчёт и приёмка — вымышленные. Объект и сотрудники имеют префикс `DEMO`, оборудование и снимок работы — `synthetic_demo`, показание — `is_estimated`. Завершённый наряд связан с проверенным отчётом и демонстрационной приёмкой инженера. Все исторические записи относятся к отдельному объекту `DEMO — тепловой пункт`; при выборках всегда проверяйте объект и происхождение работы. `demo-photo.png` — синтетическая заглушка с надписью DEMO, не фотография объекта. `storage_key` указывает на файл в репозитории; текущий API выдаёт этот конкретный demo-файл через тот же авторизованный путь чтения. Внешнего объектного хранилища пока нет.

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


## Запросы для диагностики связей

Это read-only примеры по базовому слою DDL, не команды изменения истории.

Это **иллюстративные SQL-запросы по логической модели**: их исполняемость зависит от совпадения фактической DDL с TL02. `:site_id`, `:year`, `:month`, `:work_order_id` — параметры вашего SQL-клиента/ORM, а не синтаксис `psql` без подстановки.

### Правила по операциям заказчика

```sql
SELECT ot.code, ot.title, mt.code AS maintenance_type,
       mr.period_unit, mr.period_count, mr.occurrences_per_period,
       mr.required_people, mr.norm_hours, mr.norm_hours_basis,
       re.edition_code
FROM operation_templates AS ot
JOIN maintenance_types AS mt ON mt.maintenance_type_id = ot.maintenance_type_id
JOIN maintenance_rules AS mr
  ON mr.site_id = ot.site_id
 AND mr.system_id = ot.system_id
 AND mr.operation_template_id = ot.operation_template_id
JOIN regulation_editions AS re
  ON re.site_id = mr.site_id
 AND re.regulation_edition_id = mr.regulation_edition_id
WHERE ot.site_id = :site_id AND ot.system_id = :system_id
ORDER BY ot.code, mr.rule_version DESC;
```

### Месячный график без фиксированных колонок дней

```sql
SELECT se.planned_date, ot.code, ot.title, se.status,
       se.regulatory_deadline_on, sp.revision
FROM schedule_entries AS se
JOIN schedule_plans AS sp
  ON sp.site_id = se.site_id AND sp.schedule_plan_id = se.schedule_plan_id
JOIN maintenance_rules AS mr
  ON mr.site_id = se.site_id AND mr.system_id = se.system_id
 AND mr.maintenance_rule_id = se.maintenance_rule_id
JOIN operation_templates AS ot
  ON ot.site_id = mr.site_id AND ot.operation_template_id = mr.operation_template_id
WHERE se.site_id = :site_id AND sp.period_year = :year
  AND sp.period_month = :month
ORDER BY se.planned_date, ot.code, se.sequence_no;
```

### Прогнозы, на которые опиралось решение оркестратора

```sql
SELECT od.orchestration_decision_id, od.selected_method, od.selected_at,
       od.regulatory_deadline_at, od.reason,
       fr.proposal_at AS rule_proposal, fa.proposal_at AS ai_proposal,
       fr.input_snapshot AS rule_input, fa.input_snapshot AS ai_input
FROM orchestration_decisions AS od
LEFT JOIN forecast_runs AS fr
  ON fr.site_id = od.site_id AND fr.system_id = od.system_id
 AND fr.maintenance_rule_id = od.maintenance_rule_id
 AND fr.forecast_run_id = od.rule_forecast_id
LEFT JOIN forecast_runs AS fa
  ON fa.site_id = od.site_id AND fa.system_id = od.system_id
 AND fa.maintenance_rule_id = od.maintenance_rule_id
 AND fa.forecast_run_id = od.ai_forecast_id
WHERE od.site_id = :site_id
ORDER BY od.created_at DESC;
```

### Фотоотчёт и история приёмки одного наряда

```sql
SELECT wr.revision_no, wr.status AS report_status,
       ef.stage, ef.storage_key, ar.decision, ar.reviewed_at
FROM work_reports AS wr
LEFT JOIN evidence_files AS ef
  ON ef.site_id = wr.site_id AND ef.work_order_id = wr.work_order_id
 AND ef.work_report_id = wr.work_report_id
LEFT JOIN acceptance_reviews AS ar
  ON ar.site_id = wr.site_id AND ar.work_order_id = wr.work_order_id
 AND ar.work_report_id = wr.work_report_id
WHERE wr.site_id = :site_id AND wr.work_order_id = :work_order_id
ORDER BY wr.revision_no, ef.stage;
```

## Исходные требования и ещё не подключённые данные

Исторические аналитические `roles.md`/`scope.md` были внешними входами, а не файлами действующего runtime. Их исходные четыре роли и неоднозначный Out of Scope не означают автоматического согласования новых функций. Текущие роли и API описаны в [backend](backend.md), подтверждённые сведения Excel и вопросы заказчику — в [архитектуре](../ARCHITECTURE.md).

Модель допускает `work_readings` с числовым значением, единицей, временем и автором, incident reports и нормативные документы/редакции. Это доступная структура хранения: текущая SPA не вводит телеметрию/показания, snapshot прогноза не получает runtime reading. При будущем подключении показаний сервис должен проверять принадлежность оборудования наряду, пункта чек-листа операции и автора текущему контексту; наличие FK само по себе не доказывает полноту этих проверок.

Отмена регламентного наряда не означает выполнения обязательства. Просрочка вычисляется отдельно от статуса; восстановительное планирование и SLA обязательных календарных вхождений требуют отдельной политики. Принятую работу не открывают повторно обычным CRUD: новая потребность требует нового наряда/согласованной процедуры, сохраняя прежнюю приёмку. Формальное утверждение плана и запрет административного редактирования истории — отдельные задачи, а не свойства ER-рисунка.
