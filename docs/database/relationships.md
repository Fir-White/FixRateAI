# FixRate AI — связи ER-модели ТО/ППР

**Документ:** `docs/database/relationships.md`  
**Исходная диаграмма:** [`erd.drawio`](erd.drawio) · **Каталог атрибутов и ограничений:** [`specification.md`](specification.md)  
**Версия архитектурного проекта:** `0.9-architecture-draft` · **Дата:** 27.10.2026  
**Масштаб:** **35 таблиц, 72 внешних ключа** · PostgreSQL 16 (проектная схема)

> **Статус:** документ описывает **логическую модель**, которая присутствует в редактируемом файле `.drawio`, и предполагаемые ограничения реализации. Он **не доказывает**, что соответствующие `FOREIGN KEY`, `CHECK`, триггеры и миграции уже применены к БД. Фактическую реализацию необходимо сверить с DDL, ORM и API текущей ветки репозитория.

## 1. Как читать модель

В модели существуют три уровня: **определение операции** (`operation_templates`), **действующее правило** (`maintenance_rules` с редакцией регламента, периодичностью и нормо-часами), **конкретная работа** (`schedule_entries` → `work_orders` → `work_reports` → `acceptance_reviews`). Прогнозы обоих методов и решение оркестратора хранятся отдельно, чтобы не подменять историю одним итоговым значением.

**Кардинальность:** у каждой строки дочерней таблицы с обязательным FK есть **ровно один** родитель; если FK допускает `NULL`, ссылка может отсутствовать. Со стороны родителя обычно допустимо **0..N** дочерних строк. Исключения «не более одной дочерней строки» фиксируются `UNIQUE` (например, один плановый наряд на `schedule_entry_id`). Многим-ко-многим соответствуют отдельные таблицы-связки.

**Составной FK** вида `(site_id, system_id, equipment_id)` намеренно включает контекст: UUID оборудования без `site_id` и `system_id` не позволил бы БД проверить принадлежность к нужному объекту и системе. Само по себе наличие одинакового `site_id` ещё не заменяет проверку бизнес-ролей и временных интервалов.

### 1.1. Обозначения

| Обозначение | Значение |
|---|---|
| `PK` | Первичный ключ строки |
| `FK` | Внешний ключ: дочерняя запись ссылается на существующего родителя |
| `UNIQUE` | Запрет повторения указанной комбинации значений |
| `CHECK` | Локальная проверка диапазона или согласованности значений строки |
| `1:N` | Один родитель может иметь много дочерних записей |
| `M:N` | Многие ко многим; реализуется промежуточной таблицей |
| `NULL` | Связь необязательна в проектной модели |
| `P0 / P1` | Приоритет ввода в прототип, а не факт готовности кода |

## 2. Карта доменов и таблиц

### 01. Объекты, оборудование и доступ — 11 таблиц

| Таблица | Зачем нужна | Приоритет |
|---|---|:---:|
| `sites` | Физические объекты эксплуатации, единица разграничения доступа и нормативных графиков. | P0 |
| `users` | Учётные записи людей; глобальный пользователь может иметь разные роли на объектах. | P0 |
| `site_memberships` | Роль и активность пользователя на конкретном объекте; основа RBAC и назначения. | P0 |
| `engineering_systems` | Инженерная система объекта: теплоснабжение, ХВС, ГВС, ЖБО и т. д. | P0 |
| `equipment_types` | Классификатор типов оборудования и комплектующих. | P0 |
| `equipment` | Узлы и конкретные единицы оборудования с паспортом и иерархией. | P0 |
| `skills` | Справочник допусков и компетенций персонала. | P0 |
| `user_skills` | Подтверждённые квалификации сотрудника для конкретного объекта. | P0 |
| `availability_slots` | Доступность сотрудников и занятость для выбора исполнителей. | P1 |
| `crews` | Именованные бригады сотрудников для выполнения многопользовательских работ. | P1 |
| `crew_members` | История состава бригады; связь сотрудника и бригады во времени. | P1 |

### 02. Регламенты и правила ТО — 7 таблиц

| Таблица | Зачем нужна | Приоритет |
|---|---|:---:|
| `maintenance_types` | Классы ТО: ТО1, ТО2 и расширяемые типы. | P0 |
| `operation_templates` | Шаблон строки регламента, например «1.1 Контроль параметров ...». | P0 |
| `regulation_documents` | Реквизиты исходного документа заказчика или нормативного регламента. | P0 |
| `regulation_editions` | Неизменяемые редакции регламентов с периодами действия. | P0 |
| `maintenance_rules` | Версионированное правило: какой шаблон работ и как часто выполнять. | P0 |
| `rule_equipment` | Привязка любого количества единиц оборудования к одной строке ТО. | P0 |
| `rule_required_skills` | Перечень обязательных компетенций для назначения сотрудников на регламент. | P1 |

### 03. Календарное планирование и инциденты — 3 таблицы

| Таблица | Зачем нужна | Приоритет |
|---|---|:---:|
| `schedule_plans` | Снимок месячного графика для объекта с версионированием утверждений. | P0 |
| `schedule_entries` | Одна строка календарного факта планирования, а не отдельная колонка дня месяца. | P0 |
| `incident_reports` | Сообщения о выявленных неисправностях с текстом и ссылками на узел. | P1 |

### 04. Назначения, выполнение и приёмка — 9 таблиц

| Таблица | Зачем нужна | Приоритет |
|---|---|:---:|
| `work_orders` | Наряд-задание на одну регламентную или внеплановую операцию. | P0 |
| `work_order_equipment` | Снимок множества обслуживаемых единиц по конкретному наряду. | P0 |
| `work_assignments` | Индивидуальное назначение каждого техника на работу; бригада — необязательный контекст. | P0 |
| `checklist_templates` | Версионируемый пункт обязательных действий и показаний для операции. | P0 |
| `work_reports` | Каждая попытка отправки отчёта исполнителем; предыдущие попытки не затираются. | P0 |
| `checklist_results` | Снимок ответов на чек-лист для версии отчёта. | P0 |
| `work_readings` | Фактические показания приборов с происхождением и единицами. | P0 |
| `evidence_files` | Фотофайлы и другие подтверждения, привязанные к наряду и редакции отчёта. | P0 |
| `acceptance_reviews` | Неизменяемые решения инженера по отдельным редакциям отчёта. | P0 |

### 05. Прогнозирование, оркестрация и AI-контроль — 4 таблицы

| Таблица | Зачем нужна | Приоритет |
|---|---|:---:|
| `predictor_versions` | Реестр версий алгоритмического, ML- и визуального модуля. | P0 |
| `forecast_runs` | Общий контракт результатов rule-based и AI-прогнозирования с фиксированным контекстом. | P0 |
| `orchestration_decisions` | Агентный выбор допустимого срока после сравнения двух прогнозов и проверки регламента. | P0 |
| `ai_quality_checks` | Результат анализа визуально подтверждаемых изменений; не заменяет приёмку инженером. | P0 |

### 06. Журнал событий — 1 таблица

| Таблица | Зачем нужна | Приоритет |
|---|---|:---:|
| `audit_events` | Append-only журнал изменений состояния, нормативов, назначений и решений. | P0 |

## 3. Полный каталог связей — все 72 FK

В таблицах ниже приведены **точные наборы колонок** каталога TL02. Фактическая таблица `UNIQUE` на родительских наборах обязана существовать в DDL, иначе PostgreSQL не позволит объявить соответствующий составной FK. В столбце «Кардинальность» показано число **дочерних строк на одного родителя**; помета «опц. FK» означает, что дочерняя строка может не иметь родительской ссылки. В PostgreSQL составные ссылки с необязательным компонентом требуют аккуратной настройки `MATCH`/`CHECK`, см. раздел 5.

### 01. Объекты, оборудование и доступ

| № | Дочерняя таблица и поля | Родительская таблица и ключ | Смысл | Кардинальность |
|---:|---|---|---|---|
| 1 | `site_memberships` (`site_id`) | `sites` (`site_id`) | Принадлежность роли конкретному объекту. | 1 → 0..N |
| 2 | `site_memberships` (`user_id`) | `users` (`user_id`) | Глобальная учётная запись участника объекта. | 1 → 0..N |
| 3 | `engineering_systems` (`site_id`) | `sites` (`site_id`) | Инженерная система находится на конкретном объекте. | 1 → 0..N |
| 4 | `equipment` (`site_id`, `system_id`) | `engineering_systems` (`site_id`, `system_id`) | Оборудование принадлежит системе того же объекта; составной ключ запрещает чужую систему. | 1 → 0..N |
| 5 | `equipment` (`site_id`, `parent_equipment_id`) | `equipment` (`site_id`, `equipment_id`) | Родительский узел принадлежит тому же объекту; совпадение системы и отсутствие циклов проверяются отдельно. | 1 → 0..N (опц. FK) |
| 6 | `equipment` (`equipment_type_id`) | `equipment_types` (`equipment_type_id`) | Необязательная классификация устройства. | 1 → 0..N (опц. FK) |
| 7 | `user_skills` (`site_id`, `user_id`) | `site_memberships` (`site_id`, `user_id`) | Квалификация принадлежит человеку с доступом к этому объекту. | 1 → 0..N |
| 8 | `user_skills` (`skill_id`) | `skills` (`skill_id`) | Квалификация соответствует справочнику навыков. | 1 → 0..N |
| 9 | `availability_slots` (`site_id`, `user_id`) | `site_memberships` (`site_id`, `user_id`) | Интервал доступности задан участнику данного объекта. | 1 → 0..N |
| 10 | `crews` (`site_id`) | `sites` (`site_id`) | Бригада действует в пределах объекта. | 1 → 0..N |
| 11 | `crew_members` (`site_id`, `crew_id`) | `crews` (`site_id`, `crew_id`) | Член относится к бригаде того же объекта. | 1 → 0..N |
| 12 | `crew_members` (`site_id`, `user_id`) | `site_memberships` (`site_id`, `user_id`) | Участник бригады имеет членство на том же объекте. | 1 → 0..N |

### 02. Регламенты и правила ТО

| № | Дочерняя таблица и поля | Родительская таблица и ключ | Смысл | Кардинальность |
|---:|---|---|---|---|
| 13 | `operation_templates` (`site_id`, `system_id`) | `engineering_systems` (`site_id`, `system_id`) | Операция определена для инженерной системы этого объекта. | 1 → 0..N |
| 14 | `operation_templates` (`maintenance_type_id`) | `maintenance_types` (`maintenance_type_id`) | Тип регламентного обслуживания для шаблона операции. | 1 → 0..N |
| 15 | `regulation_documents` (`site_id`) | `sites` (`site_id`) | Регламентный документ зарегистрирован на объекте. | 1 → 0..N |
| 16 | `regulation_editions` (`site_id`, `regulation_document_id`) | `regulation_documents` (`site_id`, `regulation_document_id`) | Редакция относится к документу того же объекта. | 1 → 0..N |
| 17 | `regulation_editions` (`site_id`, `approved_by`) | `site_memberships` (`site_id`, `user_id`) | Одобряющий редакцию пользователь имеет членство на объекте. | 1 → 0..N (опц. FK) |
| 18 | `maintenance_rules` (`site_id`, `system_id`, `operation_template_id`) | `operation_templates` (`site_id`, `system_id`, `operation_template_id`) | Версия правила относится к операции из той же системы и объекта. | 1 → 0..N |
| 19 | `maintenance_rules` (`site_id`, `regulation_edition_id`) | `regulation_editions` (`site_id`, `regulation_edition_id`) | Правило ссылается на конкретную редакцию регламента того же объекта. | 1 → 0..N |
| 20 | `maintenance_rules` (`site_id`, `supersedes_rule_id`) | `maintenance_rules` (`site_id`, `maintenance_rule_id`) | Исторический предшественник текущего правила в пределах объекта. | 1 → 0..N (опц. FK) |
| 21 | `rule_equipment` (`site_id`, `system_id`, `maintenance_rule_id`) | `maintenance_rules` (`site_id`, `system_id`, `maintenance_rule_id`) | Привязка оборудования выполнена к правилу этого объекта и системы. | 1 → 0..N |
| 22 | `rule_equipment` (`site_id`, `system_id`, `equipment_id`) | `equipment` (`site_id`, `system_id`, `equipment_id`) | Привязанное устройство принадлежит тому же объекту и системе, что и правило. | 1 → 0..N |
| 23 | `rule_required_skills` (`site_id`, `maintenance_rule_id`) | `maintenance_rules` (`site_id`, `maintenance_rule_id`) | Требуемый допуск относится к правилу данного объекта. | 1 → 0..N |
| 24 | `rule_required_skills` (`skill_id`) | `skills` (`skill_id`) | Название допуска берётся из единого справочника навыков. | 1 → 0..N |

### 03. Календарное планирование и инциденты

| № | Дочерняя таблица и поля | Родительская таблица и ключ | Смысл | Кардинальность |
|---:|---|---|---|---|
| 25 | `schedule_plans` (`site_id`) | `sites` (`site_id`) | Месячный план относится к объекту. | 1 → 0..N |
| 26 | `schedule_plans` (`site_id`, `created_by`) | `site_memberships` (`site_id`, `user_id`) | Создатель графика имеет доступ к этому объекту. | 1 → 0..N |
| 27 | `schedule_plans` (`site_id`, `approved_by`) | `site_memberships` (`site_id`, `user_id`) | Утверждающий график имеет доступ к объекту. | 1 → 0..N (опц. FK) |
| 28 | `schedule_entries` (`site_id`, `schedule_plan_id`) | `schedule_plans` (`site_id`, `schedule_plan_id`) | Календарная запись относится к месячному плану своего объекта. | 1 → 0..N |
| 29 | `schedule_entries` (`site_id`, `system_id`, `maintenance_rule_id`) | `maintenance_rules` (`site_id`, `system_id`, `maintenance_rule_id`) | Для календарной записи используется правило того же объекта и системы. | 1 → 0..N |
| 30 | `schedule_entries` (`site_id`, `system_id`, `maintenance_rule_id`, `orchestration_decision_id`) | `orchestration_decisions` (`site_id`, `system_id`, `maintenance_rule_id`, `orchestration_decision_id`) | Необязательное решение оркестратора относится к тому же правилу, объекту и системе. | 1 → 0..N (опц. FK) |
| 31 | `incident_reports` (`site_id`, `system_id`) | `engineering_systems` (`site_id`, `system_id`) | Инцидент зарегистрирован внутри инженерной системы объекта. | 1 → 0..N |
| 32 | `incident_reports` (`site_id`, `system_id`, `equipment_id`) | `equipment` (`site_id`, `system_id`, `equipment_id`) | Необязательное устройство инцидента должно быть из той же системы и объекта. | 1 → 0..N (опц. FK) |
| 33 | `incident_reports` (`site_id`, `reported_by`) | `site_memberships` (`site_id`, `user_id`) | Автор сообщения имеет доступ к объекту. | 1 → 0..N |

### 04. Назначения, выполнение и приёмка

| № | Дочерняя таблица и поля | Родительская таблица и ключ | Смысл | Кардинальность |
|---:|---|---|---|---|
| 34 | `work_orders` (`site_id`, `system_id`) | `engineering_systems` (`site_id`, `system_id`) | Наряд-задание относится к инженерной системе своего объекта. | 1 → 0..N |
| 35 | `work_orders` (`site_id`, `system_id`, `maintenance_rule_id`) | `maintenance_rules` (`site_id`, `system_id`, `maintenance_rule_id`) | Необязательное регламентное правило соответствует той же системе и объекту. | 1 → 0..N (опц. FK) |
| 36 | `work_orders` (`site_id`, `system_id`, `schedule_entry_id`) | `schedule_entries` (`site_id`, `system_id`, `schedule_entry_id`) | Необязательная запись графика принадлежит той же системе и объекту. | 1 → 0..1 (опц. FK) |
| 37 | `work_orders` (`site_id`, `system_id`, `incident_report_id`) | `incident_reports` (`site_id`, `system_id`, `incident_report_id`) | Необязательное исходное сообщение об инциденте того же объекта и системы. | 1 → 0..N (опц. FK) |
| 38 | `work_orders` (`site_id`, `created_by`) | `site_memberships` (`site_id`, `user_id`) | Необязательный автор наряда имеет доступ к данному объекту. | 1 → 0..N (опц. FK) |
| 39 | `work_orders` (`site_id`, `system_id`, `maintenance_rule_id`, `orchestration_decision_id`) | `orchestration_decisions` (`site_id`, `system_id`, `maintenance_rule_id`, `orchestration_decision_id`) | Решение оркестратора наряда относится к тому же правилу, системе и объекту. | 1 → 0..N (опц. FK) |
| 40 | `work_order_equipment` (`site_id`, `system_id`, `work_order_id`) | `work_orders` (`site_id`, `system_id`, `work_order_id`) | Прикреплённая к наряду единица оборудования принадлежит этому наряду. | 1 → 0..N |
| 41 | `work_order_equipment` (`site_id`, `system_id`, `equipment_id`) | `equipment` (`site_id`, `system_id`, `equipment_id`) | Прикреплённое устройство принадлежит той же системе и объекту, что и наряд. | 1 → 0..N |
| 42 | `work_assignments` (`site_id`, `work_order_id`) | `work_orders` (`site_id`, `work_order_id`) | Назначение относится к наряду того же объекта. | 1 → 0..N |
| 43 | `work_assignments` (`site_id`, `user_id`) | `site_memberships` (`site_id`, `user_id`) | Назначенный сотрудник имеет доступ к объекту. | 1 → 0..N |
| 44 | `work_assignments` (`site_id`, `assigned_by`) | `site_memberships` (`site_id`, `user_id`) | Сотрудник, оформивший назначение, имеет доступ к объекту. | 1 → 0..N |
| 45 | `work_assignments` (`site_id`, `crew_id`) | `crews` (`site_id`, `crew_id`) | Необязательная бригада должна относиться к тому же объекту. | 1 → 0..N (опц. FK) |
| 46 | `checklist_templates` (`site_id`, `operation_template_id`) | `operation_templates` (`site_id`, `operation_template_id`) | Пункт чек-листа принадлежит шаблону операции в пределах объекта. | 1 → 0..N |
| 47 | `work_reports` (`site_id`, `work_order_id`) | `work_orders` (`site_id`, `work_order_id`) | Редакция отчёта относится к наряду данного объекта. | 1 → 0..N |
| 48 | `work_reports` (`site_id`, `submitted_by`) | `site_memberships` (`site_id`, `user_id`) | Автор отчёта имеет членство на объекте. | 1 → 0..N |
| 49 | `checklist_results` (`site_id`, `work_order_id`, `work_report_id`) | `work_reports` (`site_id`, `work_order_id`, `work_report_id`) | Ответ в чек-листе привязан к конкретной версии отчёта того же наряда. | 1 → 0..N |
| 50 | `checklist_results` (`site_id`, `checklist_template_id`) | `checklist_templates` (`site_id`, `checklist_template_id`) | Необязательный вопрос чек-листа выбран из шаблонов объекта. | 1 → 0..N (опц. FK) |
| 51 | `work_readings` (`site_id`, `system_id`, `work_order_id`) | `work_orders` (`site_id`, `system_id`, `work_order_id`) | Показание относится к наряду конкретной системы и объекта. | 1 → 0..N |
| 52 | `work_readings` (`site_id`, `work_order_id`, `work_report_id`) | `work_reports` (`site_id`, `work_order_id`, `work_report_id`) | Показание относится к версии отчёта того же наряда. | 1 → 0..N |
| 53 | `work_readings` (`site_id`, `system_id`, `equipment_id`) | `equipment` (`site_id`, `system_id`, `equipment_id`) | Необязательный прибор показания принадлежит той же системе и объекту. | 1 → 0..N (опц. FK) |
| 54 | `evidence_files` (`site_id`, `work_order_id`) | `work_orders` (`site_id`, `work_order_id`) | Файл-доказательство относится к наряду объекта. | 1 → 0..N |
| 55 | `evidence_files` (`site_id`, `work_order_id`, `work_report_id`) | `work_reports` (`site_id`, `work_order_id`, `work_report_id`) | Необязательная версия отчёта для файла — от того же наряда. | 1 → 0..N (опц. FK) |
| 56 | `evidence_files` (`site_id`, `uploaded_by`) | `site_memberships` (`site_id`, `user_id`) | Загрузивший файл сотрудник имеет доступ к объекту. | 1 → 0..N |
| 57 | `acceptance_reviews` (`site_id`, `work_order_id`, `work_report_id`) | `work_reports` (`site_id`, `work_order_id`, `work_report_id`) | Результат приёмки относится к конкретной версии отчёта наряда. | 1 → 0..1 |
| 58 | `acceptance_reviews` (`site_id`, `reviewer_user_id`) | `site_memberships` (`site_id`, `user_id`) | Проверяющий имеет членство на объекте. | 1 → 0..N |

### 05. Прогнозирование, оркестрация и AI-контроль

| № | Дочерняя таблица и поля | Родительская таблица и ключ | Смысл | Кардинальность |
|---:|---|---|---|---|
| 59 | `forecast_runs` (`site_id`, `system_id`, `maintenance_rule_id`) | `maintenance_rules` (`site_id`, `system_id`, `maintenance_rule_id`) | Прогноз относится к правилу того же объекта и системы. | 1 → 0..N |
| 60 | `forecast_runs` (`site_id`, `system_id`, `equipment_id`) | `equipment` (`site_id`, `system_id`, `equipment_id`) | Необязательный объект прогнозирования — оборудование той же системы. | 1 → 0..N (опц. FK) |
| 61 | `forecast_runs` (`predictor_version_id`) | `predictor_versions` (`predictor_version_id`) | Прогноз получен версией алгоритмического или AI-модуля. | 1 → 0..N |
| 62 | `orchestration_decisions` (`site_id`, `system_id`, `maintenance_rule_id`) | `maintenance_rules` (`site_id`, `system_id`, `maintenance_rule_id`) | Решение оркестратора принимается в контексте конкретного правила. | 1 → 0..N |
| 63 | `orchestration_decisions` (`site_id`, `system_id`, `maintenance_rule_id`, `rule_forecast_id`) | `forecast_runs` (`site_id`, `system_id`, `maintenance_rule_id`, `forecast_run_id`) | Алгоритмический прогноз взят из того же правила, объекта и системы. | 1 → 0..N (опц. FK) |
| 64 | `orchestration_decisions` (`site_id`, `system_id`, `maintenance_rule_id`, `ai_forecast_id`) | `forecast_runs` (`site_id`, `system_id`, `maintenance_rule_id`, `forecast_run_id`) | AI-прогноз взят из того же правила, объекта и системы. | 1 → 0..N (опц. FK) |
| 65 | `orchestration_decisions` (`orchestrator_version_id`) | `predictor_versions` (`predictor_version_id`) | Зафиксирована версия оркестратора, принявшего решение. | 1 → 0..N |
| 66 | `ai_quality_checks` (`site_id`, `work_order_id`) | `work_orders` (`site_id`, `work_order_id`) | AI-оценка качества относится к наряду объекта. | 1 → 0..N |
| 67 | `ai_quality_checks` (`site_id`, `work_order_id`, `work_report_id`) | `work_reports` (`site_id`, `work_order_id`, `work_report_id`) | При наличии версии отчёта оценка привязана к этому же наряду. | 1 → 0..N (опц. FK) |
| 68 | `ai_quality_checks` (`site_id`, `work_order_id`, `before_file_id`) | `evidence_files` (`site_id`, `work_order_id`, `evidence_file_id`) | Фото «до» привязано к этому же наряду, а не к чужой работе. | 1 → 0..N (опц. FK) |
| 69 | `ai_quality_checks` (`site_id`, `work_order_id`, `after_file_id`) | `evidence_files` (`site_id`, `work_order_id`, `evidence_file_id`) | Фото «после» привязано к этому же наряду, а не к чужой работе. | 1 → 0..N (опц. FK) |
| 70 | `ai_quality_checks` (`predictor_version_id`) | `predictor_versions` (`predictor_version_id`) | Проверка выполнена конкретной версией визуального модуля. | 1 → 0..N |

### 06. Журнал событий

| № | Дочерняя таблица и поля | Родительская таблица и ключ | Смысл | Кардинальность |
|---:|---|---|---|---|
| 71 | `audit_events` (`site_id`) | `sites` (`site_id`) | Событие аудита зафиксировано в контексте объекта. | 1 → 0..N |
| 72 | `audit_events` (`site_id`, `actor_user_id`) | `site_memberships` (`site_id`, `user_id`) | Необязательный автор-участник события принадлежит объекту. | 1 → 0..N (опц. FK) |

**Правило удаления:** все 72 связи каталога имеют `ON DELETE RESTRICT`. Удаление записей, на которые ссылаются дочерние данные, блокируется, вместо удаления истории. В проекте рекомендуется деактивация записей и новые версии правил там, где это предусмотрено бизнес-логикой.

## 4. Ключевые отношения предметной области

### 4.1. Иерархия объекта и оборудования

```text
sites 1 ── N engineering_systems 1 ── N equipment
                            equipment 1 ── N equipment (parent_equipment_id)
equipment_types 1 ── N equipment
sites 1 ── N site_memberships N ── 1 users
```

`sites` — разграничение объектов. `engineering_systems` группирует приборы, узлы и комплексы. Внутри `equipment` допускается иерархия: тепловой пункт → насос → измерительный прибор. Ссылка `parent_equipment_id` гарантирует общий объект через `(site_id, ...)`, **но одна только она не гарантирует отсутствие циклов и принадлежность родителя той же `system_id`**: это дополнительный инвариант для сервисной проверки или триггера. `equipment_types` — глобальный классификатор.

### 4.2. Нормативная операция и конкретное оборудование

```text
maintenance_types 1 ── N operation_templates 1 ── N maintenance_rules
regulation_documents 1 ── N regulation_editions 1 ── N maintenance_rules
maintenance_rules N ── M equipment   (через rule_equipment)
maintenance_rules N ── M skills      (через rule_required_skills)
```

**Не смешивать сущности:** `operation_templates` отвечает на вопрос «что делать?», `maintenance_rules` — «по какой редакции и когда выполнять?», `rule_equipment` — «для каких приборов действует правило?». При пересмотре периодичности или нормо-часов создаётся новая версия правила с `supersedes_rule_id`, а прежнее остаётся доступным историческим записям.

### 4.3. Плановый график и наряд

```text
sites 1 ── N schedule_plans 1 ── N schedule_entries
maintenance_rules 1 ── N schedule_entries
schedule_entries 1 ── 0..1 work_orders  [UNIQUE(site_id, schedule_entry_id)]
incident_reports 1 ── N work_orders     [для внеплановых обращений]
```

Один `schedule_plans` — редакция графика для `(site_id, period_year, period_month, revision)`. Каждая строка `schedule_entries` представляет **конкретную дату**, а не одну из 31 колонок месяца. Повторное формирование графика должно учитывать уникальность `(site_id, schedule_plan_id, maintenance_rule_id, planned_date, sequence_no)` и не дублировать наряд на одну запись графика.

`work_orders` поддерживает происхождение `scheduled` / `incident` / `manual`: не каждая работа обязана быть связана с календарём, но плановая работа должна иметь `schedule_entry_id` и `maintenance_rule_id`; инцидентная — `incident_report_id` (см. `CHECK` каталога).

### 4.4. Исполнитель, отчёт и приёмка

```text
work_orders 1 ── N work_assignments N ── 1 site_memberships
work_orders 1 ── N work_reports 1 ── N checklist_results
                        │               └── N work_readings
                        ├── N evidence_files (before / after / issue / other)
                        └── 0..1 acceptance_reviews на версию отчёта
work_orders 1 ── N ai_quality_checks   [рекомендация, не приёмка]
```

У одного наряда может быть несколько техников (несколько строк `work_assignments`). `crews` и `crew_members` дают историю бригад; идентификатор бригады необязателен в назначении, **само членство в бригаде на дату назначения требует отдельной проверки интервала**. У одного наряда несколько версий отчёта (`work_reports.revision_no`), поэтому отклонённую попытку нельзя перетирать новой. `acceptance_reviews` с `UNIQUE(site_id, work_report_id)` допускает **не более одного решения приёмки на одну версию отчёта**; после исправления создаётся новый отчёт.

### 4.5. Два прогноза и объяснимый выбор

```text
predictor_versions 1 ── N forecast_runs [method=rule | ai]
maintenance_rules 1 ── N forecast_runs
forecast_runs (rule) ─┐
                      ├── N orchestration_decisions ── N schedule_entries / work_orders
forecast_runs (ai) ───┘
predictor_versions 1 ── N orchestration_decisions [версия оркестратора]
```

Каждый `forecast_runs` фиксирует `predictor_version_id`, `input_snapshot`, результат (`proposal_at`), `regulatory_deadline_at`, уверенность и объяснение. `orchestration_decisions` ссылается на **две независимые попытки** (`rule_forecast_id`, `ai_forecast_id`), а не на одну усреднённую дату. Выбор сохраняет `selected_method`, `selected_at`, `reason` и `comparison_snapshot`. Принудительное ограничение: `selected_at <= regulatory_deadline_at` (при наличии даты).

**Ограничение для реализации:** FK гарантирует общий контекст правила, но не гарантирует, что `rule_forecast_id` указывает именно на `method=rule`, а `ai_forecast_id` именно на `method=ai`, либо что `predictor_versions.kind` согласован с методом. Эти проверки выполняются триггером/сервисом с транзакционной защитой; JSON нельзя считать доказательством правильности модели.

### 4.6. Визуальная оценка — не приёмка

`ai_quality_checks` привязывает пару `before_file_id` / `after_file_id` к **тому же наряду** составными ключами. Запись содержит версию визуального анализатора, признаки видимых изменений и уровень неопределённости. Фото в `evidence_files` имеют `stage`, который должен соответствовать роли файла в AI-проверке. Такой cross-table контроль **не обеспечивается одним FK**. Финальное решение принимает сотрудник через `acceptance_reviews`; скрытые операции обслуживания нельзя считать подтверждёнными по одному снимку.

## 5. Ограничения целостности: что гарантирует схема, а что требует кода

| Требование | Декларативно в БД | Дополнительная проверка |
|---|---|---|
| Привязка объекта и системы | Составные FK `(site_id, system_id, ...)` и `UNIQUE` родителя | Роли участника и актуальность доступа |
| Иерархия оборудования | FK по `(site_id, parent_equipment_id)`, `CHECK parent_equipment_id <> equipment_id` | Нет циклов и совпадает `system_id` родителя и ребёнка |
| Периодичность ТО | CHECK `period_unit`, `period_count > 0`, `occurrences_per_period > 0` | Семантика `5/год`, границы квартала, часовой пояс, праздники |
| Численность и нормо-часы | `required_people > 0`, `norm_hours >= 0` | Толкование `norm_hours_basis=unknown` — расчёт не должен выдумывать единицы |
| Версионность регламентов | Уникальность `(site_id, operation_template_id, rule_version)` | Запрет изменения утверждённых исторических редакций/правил |
| Календарь без 31 колонок | `schedule_entries.planned_date DATE` | Генерация записей по регламенту и идемпотентность планировщика |
| Дата не позднее регламента | `CHECK planned_date <= regulatory_deadline_on`; `selected_at <= regulatory_deadline_at` | Согласованность нескольких deadline-полей, бизнес-исключения только через утверждённый процесс |
| Совпадение прогноза и метода | FK на `predictor_versions` и `forecast_runs` | `kind=method` и правильность пары rule/ai |
| Назначение техников | FK на `site_memberships` и уникальность назначений | Квалификация, доступность, нагрузка, активное членство в бригаде |
| Фотографии принадлежат одному наряду | Составные FK с `work_order_id` | `stage=before/after`, фактическое изображение, размер/валидность содержимого |
| Отчётность и приёмка | Редакции отчётов и FK; `UNIQUE(site_id, work_report_id)` на reviews | Роль проверяющего, запрет самостоятельной приёмки, корректные переходы FSM |
| Аудит и история | FK события на `sites` и участника | Append-only права, триггеры/журнал операций, недопущение хранения секретов |

### 5.1. Особенности составных ключей с `NULL`

В PostgreSQL составной FK с `MATCH SIMPLE` обычно **не проверяет ссылку**, если хотя бы один компонент равен `NULL`. Поэтому для полей `orchestration_decision_id`, `equipment_id`, `work_report_id`, `maintenance_rule_id` и других опциональных ссылок следует проверять согласованность обязательных компонентов (либо отдельными `NOT NULL`, либо `CHECK`), чтобы избежать обхода защиты контекста. Само наличие FK в диаграмме — ещё не достаточная гарантия.

### 5.2. Рекомендуемые уникальности, наиболее важные для жизненного цикла

- **`engineering_systems`:** `(site_id,system_id)`, `(site_id,code)`.
- **`equipment`:** `(site_id,equipment_id)`, `(site_id,system_id,equipment_id)`, `(site_id,asset_code)`.
- **`operation_templates`:** `(site_id,operation_template_id)`, `(site_id,system_id,operation_template_id)`, `(site_id,system_id,code)`.
- **`regulation_editions`:** `(site_id,regulation_edition_id)`, `(site_id,regulation_document_id,edition_code)`.
- **`maintenance_rules`:** `(site_id,maintenance_rule_id)`, `(site_id,system_id,maintenance_rule_id)`, `(site_id,operation_template_id,rule_version)`.
- **`schedule_plans`:** `(site_id,schedule_plan_id)`, `(site_id,period_year,period_month,revision)`.
- **`schedule_entries`:** `(site_id,schedule_entry_id)`, `(site_id,system_id,schedule_entry_id)`, `(site_id,schedule_plan_id,maintenance_rule_id,planned_date,sequence_no)`.
- **`work_orders`:** `(site_id,work_order_id)`, `(site_id,system_id,work_order_id)`, `(site_id,schedule_entry_id)`.
- **`work_assignments`:** `(site_id,work_order_id,user_id)`.
- **`work_reports`:** `(site_id,work_order_id,work_report_id)`, `(site_id,work_order_id,revision_no)`.
- **`checklist_results`:** `(work_report_id,checklist_template_id)`.
- **`acceptance_reviews`:** `(site_id,work_report_id)`.
- **`predictor_versions`:** `(kind,name,version)`.

`UNIQUE` по `schedule_entry_id` и `work_report_id` при `NULL` допускает несколько записей без ссылки. Для бизнес-правила «ровно одна запись» при наличии ссылки подходит частичный уникальный индекс или соответствующий `UNIQUE` + `NOT NULL`, в зависимости от сущности.

## 6. Типовые цепочки данных для прототипа

### 6.1. График заказчика → плановые работы

1. Регистрируется `sites` → `engineering_systems` (теплоснабжение) → `equipment` (тепловой пункт и приборы).
2. Создаются `maintenance_types` (`ТО1`, `ТО2`) и шесть `operation_templates` с кодами `1.1`–`1.6`.
3. Источник Excel сохраняется в `regulation_documents`, редакция — в `regulation_editions` (при согласовании заказчиком).
4. Для каждого шаблона создаётся `maintenance_rules` с `period_unit`, численностью и **неизменённым** значением нормо-часов. Для `5/год` не подменяются неизвестные даты.
5. Через `rule_equipment` выбираются устройства для выполнения работ; график месяца записывается в `schedule_plans` и `schedule_entries`.
6. `work_orders` формирует конкретные наряды без дублирования одного и того же календарного экземпляра.

### 6.2. Прогноз → объяснение → график

1. Два вызова `forecast_runs` сохраняют алгоритмическую и AI-рекомендации и версии методов.
2. `orchestration_decisions` ссылается на обе попытки, выбирает дату и фиксирует объяснение.
3. Записать выбор позже обязательного срока запрещено; если рекомендация AI невалидна или данных не хватает, возможна консервативная дата либо ручная проверка.
4. `schedule_entries` и/или `work_orders` сохраняют ссылку на принятое решение, не стирая исходные прогнозы.

### 6.3. Наряд → техник → фотоотчёт → приёмка

1. `work_assignments` фиксирует техников (или бригаду как контекст) на один `work_orders`.
2. `work_reports(revision_no=1)` содержит первую попытку отчёта; `checklist_results` и `work_readings` фиксируют ответы и показания.
3. `evidence_files` хранит метаданные фото `before`, `after`; сам файл находится вне PostgreSQL.
4. `ai_quality_checks` анализирует выбранные изображения и сохраняет заключение без автоматического закрытия наряда.
5. `acceptance_reviews` создаётся для конкретной редакции отчёта. При `rework` исполнитель подаёт новую редакцию (`revision_no=2`), сохраняя старую.
6. `audit_events` фиксирует смены статусов и решения, чтобы нельзя было потерять историю.

## 7. Примеры запросов для проверки отношений

Это **иллюстративные SQL-запросы по логической модели**: их исполняемость зависит от совпадения фактической DDL с TL02. `:site_id`, `:year`, `:month`, `:work_order_id` — параметры вашего SQL-клиента/ORM, а не синтаксис `psql` без подстановки.

### 7.1. Правила по операциям заказчика

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

### 7.2. Месячный график без фиксированных колонок дней

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

### 7.3. Прогнозы, на которые опиралось решение оркестратора

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

### 7.4. Фотоотчёт и история приёмки одного наряда

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

## 8. Проверки для приёмки ER-модели

- [ ] В каталоге **35 таблиц**, все 72 связи из draw.io описаны в разделе 3.
- [ ] Каждый FK указывает на существующую таблицу, существующие поля и целевой ключ `PK/UNIQUE`.
- [ ] Можно представить шесть операций из Excel с ТО1/ТО2, `1/день`, `1/квар`, `5/год`, численностью и нормо-часами.
- [ ] План месяца хранится строками с `DATE` и допускает 28, 29, 30, 31 день без изменения DDL.
- [ ] Можно добавить новое оборудование под действующую операцию через `rule_equipment`.
- [ ] Наряд связывается с правильным объектом, системой и конкретной версией правила.
- [ ] Нельзя связать оборудование одного объекта с графиком/работой другого посредством составных FK.
- [ ] Можно зафиксировать двух техников на один наряд и историю состава бригады.
- [ ] Две попытки прогнозирования хранят версии методов и входные снимки; решение оркестратора сохраняет обе ссылки.
- [ ] Выбранный итоговый срок не должен превышать регламентный (с учётом локальных дат и часового пояса).
- [ ] Фото «до/после» и заключение AI привязаны к тому же наряду; приёмка отдельна от AI-проверки.
- [ ] Возврат на доработку не затирает предыдущий отчёт и решение проверяющего.
- [ ] Проектные межстрочные проверки перечислены отдельно и не выданы за готовые `CHECK`.
- [ ] Нельзя заявлять модель развёрнутой до реального прогона миграций и SQL-тестов.

## 9. Источники и соответствие требованиям

**Документы заказчика и аналитика:** `График для ии.xlsx`, `scope.md`, `roles.md` (предоставлены в переписке проекта). **Проектные артефакты TL02:** `erd.drawio`, `erd.svg`, `specification.md`, `model_catalog.json`. Детальный словарь всех **310 полей**, типов PostgreSQL, `CHECK`, `UNIQUE`, индексов и источников требований находится в `specification.md`; здесь акцент сделан на **логике всех 72 отношений**.

**Примечание по статусу:** новые файлы необходимо сверить с актуальной веткой новой концепции перед DDL/ORM. Публичная старая ветка со сметной архитектурой не является эталоном сущностей ТО/ППР.
