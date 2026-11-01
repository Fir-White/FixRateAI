> Базовая модель SQL 001–004. Текущие дополнения 005–008, рабочие статусы и поля описаны в [DTO/SQL mapping](../architecture/dto_db_mapping.md) и [процессе настройки](../WORKFORCE_PLANNING.md); ER-изображение показывает базовые 35 таблиц.

# FixRate AI — спецификация модели данных ТО/ППР

> Этот документ — исходная спецификация TL02, сохранённая как исторический срез. Для фактических типов и ограничений используйте [миграции](../../database/README.md), для изменений и предложений — [проект TL03](tl03_target.md). В частности, миграция 002 изменила `maintenance_rules.norm_hours` на nullable NUMERIC(12,3), а 004 расширяет снимок нормы наряда и добавляет составной FK с `NOT VALID`.

**Документ:** TL02 · ER-модель оборудования, регламентов, графиков, заданий и AI-контроля  
**Проектная версия:** `0.9-architecture-draft` · **Дата:** 27.10.2026  
**Целевая СУБД:** PostgreSQL 16 · **Дедлайн прототипа:** 07.11.2026  
**Статус:** архитектурный проект, **не** применённая DDL-миграция; не заменяет проверку и согласование с backend.

> **Граница подтверждения.** Доступны файлы заказчика `График для ии.xlsx`, аналитика `scope.md`, `roles.md`. Публичная ветка `master` репозитория [firewhite/FixRate_AI](https://gitverse.ru/firewhite/FixRate_AI) по состоянию на просмотренную страницу содержит **предыдущую сметную концепцию**; файлы новой архитектурной ветки в этом сеансе не удалось прочитать. Поэтому ниже **проектная схема TL02**, построенная на доступных документах. Перед фиксацией новых SQL-миграций нужно сверить названия и типы с фактическими `docs/architecture/*` и API-контрактами новой ветки.

## 1. Основания и интерпретация требований

**Из файла заказчика подтверждены:** объектная иерархия «система теплоснабжения — тепловой пункт — операция», шесть строк операций, виды ТО1/ТО2, значения периодичности, требуемая численность персонала и нормо-часы, месячная календарная сетка, необходимость добавлять новые работы и оборудование под строкой. Excel не указывает год, не задаёт даты для `1/квар` и `5/год`, не поясняет метод исчисления 60 нормо-часов при двух сотрудниках и не содержит размеченную историю отказов для AI.

**Из `roles.md` подтверждены:** четыре роли (Главный руководитель, Главный инженер, Инженер, Техник), назначение исполнителей, отчётность и приёмка, отдельные состояния работы и флаг просрочки. Из `scope.md` — запрет переноса обязательного ТО за пределы регламента и хранение трудоёмкости/численности.

**Проектные расширения по задаче TL02 и утверждённой концепции команды:** две независимые записи прогноза (rule-based и AI), выбор оркестратора с происхождением/версиями, версии правил и планов, снимки исходных параметров, визуальный контроль фотографий «до/после», журнал аудита, объектная изоляция. Эти структуры описывают требуемый контракт и **не доказывают** наличие реализованных алгоритмов.

**Неоднозначность аналитических документов:** раздел `3.2 Out of Scope` файла `scope.md` перечисляет также обработку AI, защиту сроков и Excel-экспорт, которые фигурируют в сквозном сценарии `roles.md` и в требованиях команды. До официальной правки scope рассматриваем календарь, роли, задания и контроль обязательных сроков как P0; хранение AI-прогнозов и результатов фотоанализа как P0 по постановке TL02; классификацию заявок через CV/NLP/RAG и Excel-импорт как P1 либо отдельное согласование. Это **не автоматическое изменение требований заказчика**.

### 1.1. Шесть подтверждённых строк исходного графика

| Код | Наименование операции | Вид | Частота в файле | Людей | Нормо-часы |
|---|---|---|---|---:|---:|
| `1.1` | Контроль параметров показаний приборов (давление, температура) | ТО1 | `1/день` | 1 | 1 |
| `1.2` | Протоколирование показаний счетчиков (согласно инструкции) | ТО1 | `1/день` | 1 | 1 |
| `1.3` | Проверка функционирования управляющего модуля | ТО1 | `1/день` | 1 | 1 |
| `1.4` | Чистка всех узлов и агрегатов системы | ТО2 | `5/год` | 2 | 60 |
| `1.5` | Проверка приборов измерения температуры и давления на повреждения и точность показаний | ТО2 | `1/квар` | 1 | 48 |
| `1.6` | Выпустить воздух из системы отопления/теплоснабжения | ТО2 | `1/квар` | 1 | 30 |

Для октября файл размечает по всем 31 календарным дням только строки 1.1–1.3. **Не следует считать пустые календарные клетки строк 1.4–1.6 пропусками состоявшихся работ.** Наличие даты в календаре, статус фактического выполнения и дата принятия — три разные характеристики.

**Точное соответствие колонкам заказчика:**

| Excel | Исходный реквизит | Модель данных |
|---|---|---|
| A | «№» / код операции `1.1`–`1.6` | `operation_templates.code` |
| B | «Наименование операции» | `operation_templates.title` |
| C | «Вид ТО» | `maintenance_types.code` через `operation_templates.maintenance_type_id` |
| D | «Периодичность» | версия `maintenance_rules.period_unit`, `period_count`, `occurrences_per_period`, `scheduling_mode`; исходная строка в `schedule_parameters`/snapshot |
| E | «кол-во человек» | `maintenance_rules.required_people` |
| F | «Нормо-часы» | `maintenance_rules.norm_hours`; отдельно `norm_hours_basis='unknown'` до уточнения |
| G:AK | дни месяца `1..31`, отметки ТО1 | строки `schedule_entries.planned_date` + связанные `maintenance_rules`; календарь рисует frontend |
| Примечание 1 | добавление новых строк | новая запись `operation_templates` и версия `maintenance_rules` |
| Примечание 2 | оборудование под строкой | `equipment` + привязка `rule_equipment` |

Схема хранит **факт исходного маркера** `ТО1` в составе `schedule_entries.rule_snapshot`, а не трактует его как подтверждение фактического выполнения.

### 1.2. Принятые проектные решения

1. PostgreSQL хранит плановые работы строками `schedule_entries(planned_date, planned_at, regulatory_deadline_on, regulatory_deadline_at)`; дни `1..31` — динамические столбцы UI по месяцу, а не столбцы таблиц.
2. `operation_templates` — строка вида работ; `maintenance_rules` — её **версия с конкретной периодичностью и трудозатратами**; `rule_equipment` — M:N привязка к устройствам; `schedule_entries` — экземпляры календаря; `work_orders` — исполняемые наряды.
3. `maintenance_rules.norm_hours` точно хранит значение Excel; отдельное `norm_hours_basis` не допускает скрытого умножения на количество работников. Для неподтверждённой семантики устанавливается `unknown`.
4. Справочник оборудования включает комплексы и вложенные единицы в одной иерархии. «Тепловой пункт» может быть родительским комплексом, под ним — отдельные приборы.
5. Версии редакций регламентов, правил, графиков и поданных отчётов не перезаписываются после утверждения; более поздняя версия ссылается на предыдущую. Наряд получает JSONB-снимок регламента и количества работников.
6. RBAC привязывает пользователя к **объекту**, не только к глобальной учётной записи. Внешние ключи с общим `site_id` защищают от перемешивания объектов.
7. Два прогнозирующих метода выдают стандартизированные результаты в `forecast_runs` с одинаковым набором обязательных полей и ссылкой на версию метода. `orchestration_decisions` хранит оба прогноза, причину выбора и крайний срок.
8. AI может ошибиться при предложении даты, но **записать выбранную запрещённую дату в решение/утверждённый график нельзя**: `selected_at <= regulatory_deadline_at`, `planned_date <= regulatory_deadline_on` (и при наличии времени — `planned_at <= regulatory_deadline_at`). Несоблюдение правил календарных окон/роль заявителя дополнительно проверяет доменный сервис.
9. `ai_quality_checks` — рекомендация, а не подтверждение технической исправности. Окончательное решение фиксирует `acceptance_reviews` с ролью Инженера или Главного инженера.
10. Фотофайлы хранятся вне PostgreSQL; в БД — метаданные, хеш, ссылка на хранилище, назначение фотографии и связь с отчётом.

## 2. Структура модели

**Объём проектной модели:** 35 таблиц, 310 полей, 72 описанная связь FK. Числа относятся к **каталогу ER**, а не к готовой БД. Признаки P0 / P1 — приоритет реализации прототипа, не утверждение о завершении кода.

| Домен | Таблицы | Кол-во |
|---|---|---:|
| 01 · Объекты и доступ | `sites`, `users`, `site_memberships`, `engineering_systems`, `equipment_types`, `equipment`, `skills`, `user_skills`, `availability_slots`, `crews`, `crew_members` | 11 |
| 02 · Регламенты и периодичность | `maintenance_types`, `operation_templates`, `regulation_documents`, `regulation_editions`, `maintenance_rules`, `rule_equipment`, `rule_required_skills` | 7 |
| 03 · Планирование и заявки | `schedule_plans`, `schedule_entries`, `incident_reports` | 3 |
| 04 · Исполнение и приёмка | `work_orders`, `work_order_equipment`, `work_assignments`, `checklist_templates`, `work_reports`, `checklist_results`, `work_readings`, `evidence_files`, `acceptance_reviews` | 9 |
| 05 · Прогнозы и качество | `predictor_versions`, `forecast_runs`, `orchestration_decisions`, `ai_quality_checks` | 4 |
| 06 · История | `audit_events` | 1 |

В SVG показана схема связей основных сущностей; редактируемый draw.io содержит страницы по доменам, а также страницу всех внешних ключей. Типы и ограничения перечислены здесь целиком. Стандартные схемы полного жизненного цикла и аудита лежат в тех же 35 сущностях; не нужно создавать отдельную дублирующую БД под AI.

## 3. Детальная спецификация сущностей

### 01 · Объекты и доступ

#### `sites` · P0

Физические объекты эксплуатации, единица разграничения доступа и нормативных графиков.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `site_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор объекта |
| `name` | `TEXT` | Нет | — | Наименование объекта |
| `address` | `TEXT` | Да | — | Адрес |
| `timezone` | `TEXT` | Нет | `Asia/Yekaterinburg` | Часовой пояс IANA для локальных дедлайнов |
| `is_active` | `BOOLEAN` | Нет | `true` | Признак доступности объекта |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Дата создания записи |

**PK:** `site_id`.  **CHECK (проект):** `length(trim(name)) > 0`; `length(trim(timezone)) > 0`.  **Индексы (проект):** `(is_active, name)`.  
**Внешние ключи:** нет.

#### `users` · P0

Учётные записи людей; глобальный пользователь может иметь разные роли на объектах.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `user_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор пользователя |
| `full_name` | `TEXT` | Нет | — | ФИО/отображаемое имя |
| `email` | `TEXT` | Нет | — | Адрес электронной почты |
| `password_hash` | `TEXT` | Да | — | Хеш пароля, если выбрана локальная аутентификация |
| `is_active` | `BOOLEAN` | Нет | `true` | Деактивация без удаления истории |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время регистрации |

**PK:** `user_id`.  **CHECK (проект):** `length(trim(full_name)) > 0`; `position('@' in email) > 1`.  **Индексы (проект):** `UNIQUE lower(email)`.  
**Внешние ключи:** нет.

#### `site_memberships` · P0

Роль и активность пользователя на конкретном объекте; основа RBAC и назначения.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `site_id` | `UUID` | Нет | — | Объект, к которому открыт доступ |
| `user_id` | `UUID` | Нет | — | Пользователь |
| `role` | `TEXT` | Нет | — | executive / chief_engineer / engineer / technician |
| `is_active` | `BOOLEAN` | Нет | `true` | Право действовать на объекте |
| `joined_at` | `TIMESTAMPTZ` | Нет | `now()` | Дата назначения роли |

**PK:** `site_id, user_id`.  **CHECK (проект):** `role IN ('executive','chief_engineer','engineer','technician')`.  **Индексы (проект):** `(user_id, is_active)`.  
**Внешние ключи:**
- `(site_id)` → `sites(site_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(user_id)` → `users(user_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `engineering_systems` · P0

Инженерная система объекта: теплоснабжение, ХВС, ГВС, ЖБО и т. д.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `system_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор системы |
| `site_id` | `UUID` | Нет | — | Родительский объект |
| `code` | `TEXT` | Нет | — | Локальный код системы |
| `name` | `TEXT` | Нет | — | Название системы |
| `notes` | `TEXT` | Да | — | Описание и комментарии |
| `is_active` | `BOOLEAN` | Нет | `true` | Признак действующей системы |

**PK:** `system_id`.  **UNIQUE / уникальные ключи:** `(site_id,system_id)`; `(site_id,code)`.  **CHECK (проект):** `length(trim(name)) > 0`.  **Индексы (проект):** `(site_id,name)`.  
**Внешние ключи:**
- `(site_id)` → `sites(site_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `equipment_types` · P0

Классификатор типов оборудования и комплектующих.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `equipment_type_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор типа |
| `code` | `TEXT` | Нет | — | Код типа оборудования |
| `name` | `TEXT` | Нет | — | Название типа |
| `default_attributes` | `JSONB` | Нет | `{}` | Структура типовых паспортных атрибутов |

**PK:** `equipment_type_id`.  **UNIQUE / уникальные ключи:** `(code)`.  **CHECK (проект):** `jsonb_typeof(default_attributes) = 'object'`.  
**Внешние ключи:** нет.

#### `equipment` · P0

Узлы и конкретные единицы оборудования с паспортом и иерархией.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `equipment_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор оборудования |
| `site_id` | `UUID` | Нет | — | Объект эксплуатации |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `parent_equipment_id` | `UUID` | Да | — | Родительский комплекс, например тепловой пункт |
| `equipment_type_id` | `UUID` | Да | — | Тип оборудования из классификатора |
| `asset_code` | `TEXT` | Нет | — | Инвентарный код в пределах объекта |
| `name` | `TEXT` | Нет | — | Наименование (Манометр / Теплосчётчик и т. п.) |
| `serial_number` | `TEXT` | Да | — | Заводской номер |
| `commissioned_on` | `DATE` | Да | — | Дата ввода в эксплуатацию |
| `location` | `TEXT` | Да | — | Помещение/узел |
| `properties` | `JSONB` | Нет | `{}` | Паспортные и эксплуатационные признаки |
| `status` | `TEXT` | Нет | `active` | active / under_repair / retired |

**PK:** `equipment_id`.  **UNIQUE / уникальные ключи:** `(site_id,equipment_id)`; `(site_id,system_id,equipment_id)`; `(site_id,asset_code)`.  **CHECK (проект):** `status IN ('active','under_repair','retired')`; `jsonb_typeof(properties) = 'object'`; `parent_equipment_id IS DISTINCT FROM equipment_id`.  **Индексы (проект):** `(site_id,system_id,status)`; `(site_id,parent_equipment_id)`.  
**Внешние ключи:**
- `(site_id, system_id)` → `engineering_systems(site_id, system_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, parent_equipment_id)` → `equipment(site_id, equipment_id)` (опциональная связь); ON DELETE RESTRICT; Циклы и принадлежность к той же системе контролировать дополнительно.
- `(equipment_type_id)` → `equipment_types(equipment_type_id)` (опциональная связь); ON DELETE RESTRICT

#### `skills` · P0

Справочник допусков и компетенций персонала.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `skill_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор компетенции |
| `code` | `TEXT` | Нет | — | Код квалификации |
| `name` | `TEXT` | Нет | — | Наименование квалификации |
| `validity_required` | `BOOLEAN` | Нет | `false` | Требуется ли срок действия допуска |

**PK:** `skill_id`.  **UNIQUE / уникальные ключи:** `(code)`.  
**Внешние ключи:** нет.

#### `user_skills` · P0

Подтверждённые квалификации сотрудника для конкретного объекта.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `site_id` | `UUID` | Нет | — | Объект, где учитывается квалификация |
| `user_id` | `UUID` | Нет | — | Специалист |
| `skill_id` | `UUID` | Нет | — | Квалификация/допуск |
| `verified_at` | `TIMESTAMPTZ` | Да | — | Дата проверки квалификации |
| `valid_until` | `DATE` | Да | — | Дата окончания действия |

**PK:** `site_id, user_id, skill_id`.  **CHECK (проект):** `valid_until IS NULL OR verified_at IS NOT NULL`.  
**Внешние ключи:**
- `(site_id, user_id)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(skill_id)` → `skills(skill_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `availability_slots` · P1

Доступность сотрудников и занятость для выбора исполнителей.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `availability_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор интервала |
| `site_id` | `UUID` | Нет | — | Объект |
| `user_id` | `UUID` | Нет | — | Сотрудник |
| `starts_at` | `TIMESTAMPTZ` | Нет | — | Начало интервала |
| `ends_at` | `TIMESTAMPTZ` | Нет | — | Окончание интервала |
| `status` | `TEXT` | Нет | `available` | available / unavailable |
| `reason` | `TEXT` | Да | — | Причина отсутствия |

**PK:** `availability_id`.  **CHECK (проект):** `ends_at > starts_at`; `status IN ('available','unavailable')`.  **Индексы (проект):** `(site_id,user_id,starts_at,ends_at)`.  
**Внешние ключи:**
- `(site_id, user_id)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `crews` · P1

Именованные бригады сотрудников для выполнения многопользовательских работ.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `crew_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор бригады |
| `site_id` | `UUID` | Нет | — | Объект |
| `name` | `TEXT` | Нет | — | Название бригады |
| `is_active` | `BOOLEAN` | Нет | `true` | Активна ли бригада |

**PK:** `crew_id`.  **UNIQUE / уникальные ключи:** `(site_id,crew_id)`; `(site_id,name)`.  
**Внешние ключи:**
- `(site_id)` → `sites(site_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `crew_members` · P1

История состава бригады; связь сотрудника и бригады во времени.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `crew_member_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор участия |
| `site_id` | `UUID` | Нет | — | Объект |
| `crew_id` | `UUID` | Нет | — | Бригада |
| `user_id` | `UUID` | Нет | — | Сотрудник |
| `valid_from` | `DATE` | Нет | — | Дата начала участия |
| `valid_to` | `DATE` | Да | — | Дата завершения участия |

**PK:** `crew_member_id`.  **CHECK (проект):** `valid_to IS NULL OR valid_to >= valid_from`.  **Индексы (проект):** `(site_id,crew_id,valid_to)`; `UNIQUE (site_id,crew_id,user_id) WHERE valid_to IS NULL`.  
**Внешние ключи:**
- `(site_id, crew_id)` → `crews(site_id, crew_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, user_id)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT

### 02 · Регламенты и периодичность

#### `maintenance_types` · P0

Классы ТО: ТО1, ТО2 и расширяемые типы.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `maintenance_type_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор вида ТО |
| `code` | `TEXT` | Нет | — | Код: TO1 / TO2 / PPR и т. п. |
| `name` | `TEXT` | Нет | — | Отображаемое название |
| `description` | `TEXT` | Да | — | Описание вида работ |

**PK:** `maintenance_type_id`.  **UNIQUE / уникальные ключи:** `(code)`.  
**Внешние ключи:** нет.

#### `operation_templates` · P0

Шаблон строки регламента, например «1.1 Контроль параметров ...».

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `operation_template_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор шаблона |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `code` | `TEXT` | Нет | — | Код строки заказчика 1.1–1.6 |
| `title` | `TEXT` | Нет | — | Название операции ТО |
| `description` | `TEXT` | Да | — | Технологическая инструкция |
| `maintenance_type_id` | `UUID` | Нет | — | Вид ТО1/ТО2 |
| `is_active` | `BOOLEAN` | Нет | `true` | Признак доступной операции |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время добавления |

**PK:** `operation_template_id`.  **UNIQUE / уникальные ключи:** `(site_id,operation_template_id)`; `(site_id,system_id,operation_template_id)`; `(site_id,system_id,code)`.  **CHECK (проект):** `length(trim(code)) > 0`; `length(trim(title)) > 0`.  **Индексы (проект):** `(site_id,system_id,maintenance_type_id)`.  
**Внешние ключи:**
- `(site_id, system_id)` → `engineering_systems(site_id, system_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(maintenance_type_id)` → `maintenance_types(maintenance_type_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `regulation_documents` · P0

Реквизиты исходного документа заказчика или нормативного регламента.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `regulation_document_id` | `UUID` | Нет | `gen_random_uuid()` | Документ регламента |
| `site_id` | `UUID` | Нет | — | Объект, которому принадлежит экземпляр |
| `title` | `TEXT` | Нет | — | Название файла / регламента |
| `source_kind` | `TEXT` | Нет | `customer` | customer / manufacturer / internal / demo |
| `source_uri` | `TEXT` | Да | — | Ссылка, путь или реквизиты |
| `external_reference` | `TEXT` | Да | — | Номер утверждения / шифр документа |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Когда добавлен документ |

**PK:** `regulation_document_id`.  **UNIQUE / уникальные ключи:** `(site_id,regulation_document_id)`.  **CHECK (проект):** `source_kind IN ('customer','manufacturer','internal','demo')`.  
**Внешние ключи:**
- `(site_id)` → `sites(site_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `regulation_editions` · P0

Неизменяемые редакции регламентов с периодами действия.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `regulation_edition_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор редакции |
| `site_id` | `UUID` | Нет | — | Объект |
| `regulation_document_id` | `UUID` | Нет | — | Исходный документ |
| `edition_code` | `TEXT` | Нет | — | Номер/дата редакции |
| `effective_from` | `DATE` | Нет | — | Начало периода применимости |
| `effective_to` | `DATE` | Да | — | Конец периода применимости |
| `source_sha256` | `CHAR(64)` | Да | — | Хеш исходного файла для доказуемости |
| `is_approved` | `BOOLEAN` | Нет | `false` | Утверждена ли редакция |
| `approved_by` | `UUID` | Да | — | Кто утвердил редакцию |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время регистрации |

**PK:** `regulation_edition_id`.  **UNIQUE / уникальные ключи:** `(site_id,regulation_edition_id)`; `(site_id,regulation_document_id,edition_code)`.  **CHECK (проект):** `effective_to IS NULL OR effective_to >= effective_from`; `source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'`.  **Индексы (проект):** `(site_id,effective_from,effective_to)`.  
**Внешние ключи:**
- `(site_id, regulation_document_id)` → `regulation_documents(site_id, regulation_document_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, approved_by)` → `site_memberships(site_id, user_id)` (опциональная связь); ON DELETE RESTRICT

#### `maintenance_rules` · P0

Версионированное правило: какой шаблон работ и как часто выполнять.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `maintenance_rule_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор версии правила |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Система для контроля принадлежности операции |
| `operation_template_id` | `UUID` | Нет | — | Шаблон операции |
| `regulation_edition_id` | `UUID` | Нет | — | Редакция источника |
| `supersedes_rule_id` | `UUID` | Да | — | Предыдущая версия правила |
| `rule_version` | `INTEGER` | Нет | `1` | Порядковая версия правила |
| `period_unit` | `TEXT` | Нет | — | day / quarter / year / month |
| `period_count` | `INTEGER` | Нет | `1` | Количество периодов на цикл |
| `occurrences_per_period` | `INTEGER` | Нет | `1` | Число работ за один цикл |
| `scheduling_mode` | `TEXT` | Нет | — | fixed_interval / calendar_window / explicit_months |
| `schedule_parameters` | `JSONB` | Нет | `{}` | Якорь, месяцы, окна; схема валидируется сервисом |
| `required_people` | `SMALLINT` | Нет | — | Количество работников (как в Excel) |
| `norm_hours` | `NUMERIC(12,2)` | Нет | — | Значение графы «Нормо-часы», без домыслов об умножении |
| `norm_hours_basis` | `TEXT` | Нет | `unknown` | total_person_hours / per_person / unknown |
| `active_from` | `DATE` | Нет | — | Начало действия правила |
| `active_until` | `DATE` | Да | — | Окончание действия правила |
| `publication_status` | `TEXT` | Нет | `draft` | draft / published / archived |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время создания |

**PK:** `maintenance_rule_id`.  **UNIQUE / уникальные ключи:** `(site_id,maintenance_rule_id)`; `(site_id,system_id,maintenance_rule_id)`; `(site_id,operation_template_id,rule_version)`.  **CHECK (проект):** `rule_version > 0`; `period_count > 0`; `occurrences_per_period > 0`; `required_people BETWEEN 1 AND 100`; `norm_hours >= 0`; `period_unit IN ('day','month','quarter','year')`; `scheduling_mode IN ('fixed_interval','calendar_window','explicit_months')`; `norm_hours_basis IN ('total_person_hours','per_person','unknown')`; `publication_status IN ('draft','published','archived')`; `active_until IS NULL OR active_until >= active_from`; `jsonb_typeof(schedule_parameters) = 'object'`.  **Индексы (проект):** `(site_id,system_id,publication_status,active_from)`.  
**Внешние ключи:**
- `(site_id, system_id, operation_template_id)` → `operation_templates(site_id, system_id, operation_template_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, regulation_edition_id)` → `regulation_editions(site_id, regulation_edition_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, supersedes_rule_id)` → `maintenance_rules(site_id, maintenance_rule_id)` (опциональная связь); ON DELETE RESTRICT

#### `rule_equipment` · P0

Привязка любого количества единиц оборудования к одной строке ТО.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `maintenance_rule_id` | `UUID` | Нет | — | Версия регламентной операции |
| `equipment_id` | `UUID` | Нет | — | Конкретное оборудование |
| `valid_from` | `DATE` | Нет | — | Дата включения оборудования в обслуживание |
| `valid_to` | `DATE` | Да | — | Дата прекращения связи |

**PK:** `site_id, maintenance_rule_id, equipment_id, valid_from`.  **CHECK (проект):** `valid_to IS NULL OR valid_to >= valid_from`.  **Индексы (проект):** `(site_id,equipment_id)`; `UNIQUE (site_id,maintenance_rule_id,equipment_id) WHERE valid_to IS NULL`.  
**Внешние ключи:**
- `(site_id, system_id, maintenance_rule_id)` → `maintenance_rules(site_id, system_id, maintenance_rule_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, equipment_id)` → `equipment(site_id, system_id, equipment_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `rule_required_skills` · P1

Перечень обязательных компетенций для назначения сотрудников на регламент.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `site_id` | `UUID` | Нет | — | Объект |
| `maintenance_rule_id` | `UUID` | Нет | — | Правило обслуживания |
| `skill_id` | `UUID` | Нет | — | Квалификация |
| `minimum_holders` | `SMALLINT` | Нет | `1` | Минимум сотрудников с данным допуском |

**PK:** `site_id, maintenance_rule_id, skill_id`.  **CHECK (проект):** `minimum_holders > 0`.  
**Внешние ключи:**
- `(site_id, maintenance_rule_id)` → `maintenance_rules(site_id, maintenance_rule_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(skill_id)` → `skills(skill_id)` (обязательная ссылка); ON DELETE RESTRICT

### 03 · Планирование и заявки

#### `schedule_plans` · P0

Снимок месячного графика для объекта с версионированием утверждений.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `schedule_plan_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор версии графика |
| `site_id` | `UUID` | Нет | — | Объект |
| `period_year` | `INTEGER` | Нет | — | Год графика |
| `period_month` | `SMALLINT` | Нет | — | Месяц графика |
| `revision` | `INTEGER` | Нет | `1` | Номер версии графика |
| `status` | `TEXT` | Нет | `draft` | draft / approved / superseded |
| `created_by` | `UUID` | Нет | — | Автор графика |
| `approved_by` | `UUID` | Да | — | Утверждающий главный инженер |
| `approved_at` | `TIMESTAMPTZ` | Да | — | Время утверждения |
| `source_snapshot` | `JSONB` | Нет | `{}` | Сведения о входных регламентах и допущениях |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время создания |

**PK:** `schedule_plan_id`.  **UNIQUE / уникальные ключи:** `(site_id,schedule_plan_id)`; `(site_id,period_year,period_month,revision)`.  **CHECK (проект):** `period_year BETWEEN 2000 AND 2200`; `period_month BETWEEN 1 AND 12`; `revision > 0`; `status IN ('draft','approved','superseded')`; `jsonb_typeof(source_snapshot) = 'object'`.  **Индексы (проект):** `UNIQUE (site_id,period_year,period_month) WHERE status = 'approved'`.  
**Внешние ключи:**
- `(site_id)` → `sites(site_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, created_by)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, approved_by)` → `site_memberships(site_id, user_id)` (опциональная связь); ON DELETE RESTRICT

#### `schedule_entries` · P0

Одна строка календарного факта планирования, а не отдельная колонка дня месяца.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `schedule_entry_id` | `UUID` | Нет | `gen_random_uuid()` | Календарное назначение |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `schedule_plan_id` | `UUID` | Нет | — | Версия графика |
| `maintenance_rule_id` | `UUID` | Нет | — | Версия регламентной операции |
| `orchestration_decision_id` | `UUID` | Да | — | Решение, изменившее плановый слот |
| `sequence_no` | `SMALLINT` | Нет | `1` | Номер повтора внутри даты |
| `planned_date` | `DATE` | Нет | — | Календарный день ТО; одна строка на выбранную дату |
| `planned_at` | `TIMESTAMPTZ` | Да | — | Плановое время, если известно; NULL для графика только по датам |
| `regulatory_deadline_on` | `DATE` | Нет | — | Календарная предельная дата в часовом поясе объекта |
| `regulatory_deadline_at` | `TIMESTAMPTZ` | Нет | — | Обязательный предельный момент ТО (UTC-aware) |
| `status` | `TEXT` | Нет | `planned` | planned / cancelled / superseded |
| `rule_snapshot` | `JSONB` | Нет | `{}` | Условия правила на момент генерации |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время создания |

**PK:** `schedule_entry_id`.  **UNIQUE / уникальные ключи:** `(site_id,schedule_entry_id)`; `(site_id,system_id,schedule_entry_id)`; `(site_id,schedule_plan_id,maintenance_rule_id,planned_date,sequence_no)`.  **CHECK (проект):** `sequence_no > 0`; `planned_date <= regulatory_deadline_on`; `planned_at IS NULL OR planned_at <= regulatory_deadline_at`; `status IN ('planned','cancelled','superseded')`; `jsonb_typeof(rule_snapshot) = 'object'`.  **Индексы (проект):** `(site_id,planned_date,status)`; `(site_id,maintenance_rule_id,planned_date)`.  
**Внешние ключи:**
- `(site_id, schedule_plan_id)` → `schedule_plans(site_id, schedule_plan_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, maintenance_rule_id)` → `maintenance_rules(site_id, system_id, maintenance_rule_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, maintenance_rule_id, orchestration_decision_id)` → `orchestration_decisions(site_id, system_id, maintenance_rule_id, orchestration_decision_id)` (опциональная связь); ON DELETE RESTRICT

#### `incident_reports` · P1

Сообщения о выявленных неисправностях с текстом и ссылками на узел.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `incident_report_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор сообщения |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `equipment_id` | `UUID` | Да | — | Уточнённое оборудование |
| `reported_by` | `UUID` | Нет | — | Инициатор |
| `description` | `TEXT` | Нет | — | Текст наблюдения/симптомов |
| `status` | `TEXT` | Нет | `new` | new / triaged / closed |
| `ai_result_snapshot` | `JSONB` | Да | — | Предложение классификатора, если выполнялось |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время сообщения |

**PK:** `incident_report_id`.  **UNIQUE / уникальные ключи:** `(site_id,incident_report_id)`; `(site_id,system_id,incident_report_id)`.  **CHECK (проект):** `length(trim(description)) > 0`; `status IN ('new','triaged','closed')`.  
**Внешние ключи:**
- `(site_id, system_id)` → `engineering_systems(site_id, system_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, equipment_id)` → `equipment(site_id, system_id, equipment_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, reported_by)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT

### 04 · Исполнение и приёмка

#### `work_orders` · P0

Наряд-задание на одну регламентную или внеплановую операцию.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `work_order_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор задания |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `maintenance_rule_id` | `UUID` | Да | — | Версия правила для регламентной работы |
| `schedule_entry_id` | `UUID` | Да | — | Плановый экземпляр ТО, если есть |
| `incident_report_id` | `UUID` | Да | — | Исходное сообщение, если создано по неисправности |
| `origin` | `TEXT` | Нет | `scheduled` | scheduled / incident / manual |
| `status` | `TEXT` | Нет | `draft` | draft / clarification / assigned / in_progress / in_review / rework / completed / cancelled |
| `priority` | `TEXT` | Нет | `normal` | normal / high / critical |
| `operation_snapshot` | `JSONB` | Нет | `{}` | Код, название, версия и условия операции на момент выдачи |
| `required_people_snapshot` | `SMALLINT` | Нет | — | Численность бригады на момент выдачи |
| `norm_hours_snapshot` | `NUMERIC(12,2)` | Нет | — | Нормо-часы из правила, с оговоркой basis |
| `norm_hours_basis_snapshot` | `TEXT` | Нет | `unknown` | total_person_hours / per_person / unknown |
| `planned_start_at` | `TIMESTAMPTZ` | Да | — | Рекомендованное начало работ |
| `regulatory_deadline_at` | `TIMESTAMPTZ` | Да | — | Обязательный дедлайн; NULL для свободной заявки без регламента |
| `orchestration_decision_id` | `UUID` | Да | — | Зафиксированное решение о сроке для наряда |
| `created_by` | `UUID` | Да | — | Создавший пользователь, NULL для системного задания |
| `started_at` | `TIMESTAMPTZ` | Да | — | Фактическое начало работ |
| `completed_at` | `TIMESTAMPTZ` | Да | — | Время утверждённого завершения |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время создания |

**PK:** `work_order_id`.  **UNIQUE / уникальные ключи:** `(site_id,work_order_id)`; `(site_id,system_id,work_order_id)`; `(site_id,schedule_entry_id)`.  **CHECK (проект):** `origin IN ('scheduled','incident','manual')`; `status IN ('draft','clarification','assigned','in_progress','in_review','rework','completed','cancelled')`; `priority IN ('normal','high','critical')`; `required_people_snapshot > 0`; `norm_hours_snapshot >= 0`; `orchestration_decision_id IS NULL OR maintenance_rule_id IS NOT NULL`; `norm_hours_basis_snapshot IN ('total_person_hours','per_person','unknown')`; `jsonb_typeof(operation_snapshot) = 'object'`; `(planned_start_at IS NULL OR regulatory_deadline_at IS NULL OR planned_start_at <= regulatory_deadline_at)`; `(origin <> 'scheduled' OR (schedule_entry_id IS NOT NULL AND maintenance_rule_id IS NOT NULL))`; `(origin <> 'incident' OR incident_report_id IS NOT NULL)`.  **Индексы (проект):** `(site_id,status,regulatory_deadline_at)`; `(site_id,system_id,created_at)`.  
**Внешние ключи:**
- `(site_id, system_id)` → `engineering_systems(site_id, system_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, maintenance_rule_id)` → `maintenance_rules(site_id, system_id, maintenance_rule_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, system_id, schedule_entry_id)` → `schedule_entries(site_id, system_id, schedule_entry_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, system_id, incident_report_id)` → `incident_reports(site_id, system_id, incident_report_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, created_by)` → `site_memberships(site_id, user_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, system_id, maintenance_rule_id, orchestration_decision_id)` → `orchestration_decisions(site_id, system_id, maintenance_rule_id, orchestration_decision_id)` (опциональная связь); ON DELETE RESTRICT

#### `work_order_equipment` · P0

Снимок множества обслуживаемых единиц по конкретному наряду.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `equipment_id` | `UUID` | Нет | — | Единица оборудования |
| `asset_snapshot` | `JSONB` | Нет | `{}` | Паспортные признаки на момент выдачи наряда |

**PK:** `site_id, work_order_id, equipment_id`.  **CHECK (проект):** `jsonb_typeof(asset_snapshot) = 'object'`.  
**Внешние ключи:**
- `(site_id, system_id, work_order_id)` → `work_orders(site_id, system_id, work_order_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, equipment_id)` → `equipment(site_id, system_id, equipment_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `work_assignments` · P0

Индивидуальное назначение каждого техника на работу; бригада — необязательный контекст.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `work_assignment_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор назначения |
| `site_id` | `UUID` | Нет | — | Объект |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `user_id` | `UUID` | Нет | — | Назначенный техник |
| `crew_id` | `UUID` | Да | — | Бригада, из которой назначен участник |
| `assigned_by` | `UUID` | Нет | — | Инженер/главный инженер |
| `assigned_at` | `TIMESTAMPTZ` | Нет | `now()` | Дата назначения |
| `status` | `TEXT` | Нет | `assigned` | assigned / declined / active / finished / cancelled |
| `actual_person_hours` | `NUMERIC(12,2)` | Да | — | Фактически затраченные человеко-часы |

**PK:** `work_assignment_id`.  **UNIQUE / уникальные ключи:** `(site_id,work_order_id,user_id)`.  **CHECK (проект):** `status IN ('assigned','declined','active','finished','cancelled')`; `actual_person_hours IS NULL OR actual_person_hours >= 0`.  **Индексы (проект):** `(site_id,user_id,status,assigned_at)`.  
**Внешние ключи:**
- `(site_id, work_order_id)` → `work_orders(site_id, work_order_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, user_id)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, assigned_by)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, crew_id)` → `crews(site_id, crew_id)` (опциональная связь); ON DELETE RESTRICT

#### `checklist_templates` · P0

Версионируемый пункт обязательных действий и показаний для операции.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `checklist_template_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор версии пункта |
| `site_id` | `UUID` | Нет | — | Объект |
| `operation_template_id` | `UUID` | Нет | — | Шаблон обслуживания |
| `item_code` | `TEXT` | Нет | — | Локальный код пункта |
| `template_version` | `INTEGER` | Нет | `1` | Версия пунктов при пересмотре |
| `prompt` | `TEXT` | Нет | — | Формулировка проверки |
| `input_kind` | `TEXT` | Нет | — | checkbox / number / text / photo |
| `unit_code` | `TEXT` | Да | — | Единица для числового показателя |
| `is_required` | `BOOLEAN` | Нет | `true` | Обязательный пункт |
| `position` | `SMALLINT` | Нет | `1` | Порядок показа |

**PK:** `checklist_template_id`.  **UNIQUE / уникальные ключи:** `(site_id,checklist_template_id)`; `(site_id,operation_template_id,item_code,template_version)`.  **CHECK (проект):** `template_version > 0`; `position > 0`; `input_kind IN ('checkbox','number','text','photo')`.  
**Внешние ключи:**
- `(site_id, operation_template_id)` → `operation_templates(site_id, operation_template_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `work_reports` · P0

Каждая попытка отправки отчёта исполнителем; предыдущие попытки не затираются.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `work_report_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор отчёта |
| `site_id` | `UUID` | Нет | — | Объект |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `revision_no` | `INTEGER` | Нет | `1` | Номер повторной отправки |
| `submitted_by` | `UUID` | Нет | — | Исполнитель |
| `comment` | `TEXT` | Да | — | Комментарии исполнителя |
| `status` | `TEXT` | Нет | `draft` | draft / submitted / reviewed |
| `submitted_at` | `TIMESTAMPTZ` | Да | — | Дата отправки на проверку |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Создание отчёта |

**PK:** `work_report_id`.  **UNIQUE / уникальные ключи:** `(site_id,work_order_id,work_report_id)`; `(site_id,work_order_id,revision_no)`.  **CHECK (проект):** `revision_no > 0`; `status IN ('draft','submitted','reviewed')`.  
**Внешние ключи:**
- `(site_id, work_order_id)` → `work_orders(site_id, work_order_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, submitted_by)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `checklist_results` · P0

Снимок ответов на чек-лист для версии отчёта.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `checklist_result_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор ответа |
| `site_id` | `UUID` | Нет | — | Объект |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `work_report_id` | `UUID` | Нет | — | Редакция отчёта |
| `checklist_template_id` | `UUID` | Да | — | Пункт шаблона, если ещё существует |
| `question_snapshot` | `TEXT` | Нет | — | Формулировка пункта на момент исполнения |
| `response_value` | `JSONB` | Нет | `{}` | Булево, текст или число с типом |
| `recorded_at` | `TIMESTAMPTZ` | Нет | `now()` | Время фиксации |

**PK:** `checklist_result_id`.  **UNIQUE / уникальные ключи:** `(work_report_id,checklist_template_id)`.  **CHECK (проект):** `jsonb_typeof(response_value) = 'object'`.  
**Внешние ключи:**
- `(site_id, work_order_id, work_report_id)` → `work_reports(site_id, work_order_id, work_report_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, checklist_template_id)` → `checklist_templates(site_id, checklist_template_id)` (опциональная связь); ON DELETE RESTRICT

#### `work_readings` · P0

Фактические показания приборов с происхождением и единицами.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `work_reading_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор измерения |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `work_report_id` | `UUID` | Нет | — | Отчёт |
| `equipment_id` | `UUID` | Да | — | Манометр, счётчик и др. прибор |
| `parameter_code` | `TEXT` | Нет | — | pressure / temperature / meter_value и т. п. |
| `numeric_value` | `NUMERIC(18,6)` | Нет | — | Показание прибора |
| `unit_code` | `TEXT` | Нет | — | Единица: bar / celsius / m3 и т. д. |
| `measured_at` | `TIMESTAMPTZ` | Нет | — | Когда измерили |
| `is_estimated` | `BOOLEAN` | Нет | `false` | Оценочное ли значение |

**PK:** `work_reading_id`.  **CHECK (проект):** `length(trim(unit_code)) > 0`.  **Индексы (проект):** `(site_id,equipment_id,measured_at)`; `(site_id,work_order_id)`.  
**Внешние ключи:**
- `(site_id, system_id, work_order_id)` → `work_orders(site_id, system_id, work_order_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, work_order_id, work_report_id)` → `work_reports(site_id, work_order_id, work_report_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, equipment_id)` → `equipment(site_id, system_id, equipment_id)` (опциональная связь); ON DELETE RESTRICT

#### `evidence_files` · P0

Фотофайлы и другие подтверждения, привязанные к наряду и редакции отчёта.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `evidence_file_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор файла |
| `site_id` | `UUID` | Нет | — | Объект |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `work_report_id` | `UUID` | Да | — | Редакция отчёта |
| `uploaded_by` | `UUID` | Нет | — | Автор загрузки |
| `stage` | `TEXT` | Нет | — | before / after / issue / other |
| `storage_key` | `TEXT` | Нет | — | Путь/ключ объекта в файловом хранилище |
| `mime_type` | `TEXT` | Нет | — | MIME тип |
| `file_size` | `BIGINT` | Нет | — | Размер в байтах |
| `sha256` | `CHAR(64)` | Нет | — | Контрольная сумма файла |
| `captured_at` | `TIMESTAMPTZ` | Да | — | Когда фото сделано |
| `uploaded_at` | `TIMESTAMPTZ` | Нет | `now()` | Когда загружено |

**PK:** `evidence_file_id`.  **UNIQUE / уникальные ключи:** `(site_id,work_order_id,evidence_file_id)`; `(storage_key)`.  **CHECK (проект):** `stage IN ('before','after','issue','other')`; `mime_type IN ('image/jpeg','image/png','image/webp','image/heic','application/pdf')`; `file_size > 0`; `sha256 ~ '^[0-9a-f]{64}$'`.  **Индексы (проект):** `(site_id,work_order_id,stage)`.  
**Внешние ключи:**
- `(site_id, work_order_id)` → `work_orders(site_id, work_order_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, work_order_id, work_report_id)` → `work_reports(site_id, work_order_id, work_report_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, uploaded_by)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `acceptance_reviews` · P0

Неизменяемые решения инженера по отдельным редакциям отчёта.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `acceptance_review_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор решения |
| `site_id` | `UUID` | Нет | — | Объект |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `work_report_id` | `UUID` | Нет | — | Проверяемая редакция отчёта |
| `reviewer_user_id` | `UUID` | Нет | — | Инженер или главный инженер |
| `decision` | `TEXT` | Нет | — | accepted / rework / rejected |
| `comment` | `TEXT` | Да | — | Мотивированное решение |
| `reviewed_at` | `TIMESTAMPTZ` | Нет | `now()` | Время решения |

**PK:** `acceptance_review_id`.  **UNIQUE / уникальные ключи:** `(site_id,work_report_id)`.  **CHECK (проект):** `decision IN ('accepted','rework','rejected')`.  **Индексы (проект):** `(site_id,work_order_id,reviewed_at)`.  
**Внешние ключи:**
- `(site_id, work_order_id, work_report_id)` → `work_reports(site_id, work_order_id, work_report_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, reviewer_user_id)` → `site_memberships(site_id, user_id)` (обязательная ссылка); ON DELETE RESTRICT

### 05 · Прогнозы и качество

#### `predictor_versions` · P0

Реестр версий алгоритмического, ML- и визуального модуля.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `predictor_version_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор реализации |
| `kind` | `TEXT` | Нет | — | rule / ai / vision / orchestrator |
| `name` | `TEXT` | Нет | — | Наименование метода |
| `version` | `TEXT` | Нет | — | Версия модели, правил или промпта |
| `artifact_ref` | `TEXT` | Да | — | Git SHA, URI модели или пакет правил |
| `config_snapshot` | `JSONB` | Нет | `{}` | Гиперпараметры, флаги, политика |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Регистрация версии |

**PK:** `predictor_version_id`.  **UNIQUE / уникальные ключи:** `(kind,name,version)`.  **CHECK (проект):** `kind IN ('rule','ai','vision','orchestrator')`; `jsonb_typeof(config_snapshot) = 'object'`.  
**Внешние ключи:** нет.

#### `forecast_runs` · P0

Общий контракт результатов rule-based и AI-прогнозирования с фиксированным контекстом.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `forecast_run_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор прогноза |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `maintenance_rule_id` | `UUID` | Нет | — | Правило, сроки которого оцениваются |
| `equipment_id` | `UUID` | Да | — | Единица оборудования; NULL для уровня операции |
| `predictor_version_id` | `UUID` | Нет | — | Версия метода |
| `method` | `TEXT` | Нет | — | rule / ai |
| `status` | `TEXT` | Нет | — | ok / unavailable / insufficient_data / failed |
| `input_snapshot` | `JSONB` | Нет | `{}` | Фактические входные признаки, регламент и дата среза |
| `proposal_at` | `TIMESTAMPTZ` | Да | — | Предложенный срок, если прогноз получен |
| `regulatory_deadline_at` | `TIMESTAMPTZ` | Нет | — | Предельный срок по нормативному правилу |
| `confidence` | `NUMERIC(5,4)` | Да | — | Оценка уверенности (если метод поддерживает) |
| `risk_score` | `NUMERIC(5,4)` | Да | — | Скоринг риска (если рассчитан) |
| `rationale` | `TEXT` | Да | — | Объяснение решения метода |
| `output_snapshot` | `JSONB` | Нет | `{}` | Расширенный машиночитаемый результат |
| `produced_at` | `TIMESTAMPTZ` | Нет | `now()` | Время прогнозирования |

**PK:** `forecast_run_id`.  **UNIQUE / уникальные ключи:** `(site_id,system_id,maintenance_rule_id,forecast_run_id)`.  **CHECK (проект):** `method IN ('rule','ai')`; `status IN ('ok','unavailable','insufficient_data','failed')`; `confidence IS NULL OR confidence BETWEEN 0 AND 1`; `risk_score IS NULL OR risk_score BETWEEN 0 AND 1`; `(status = 'ok' AND proposal_at IS NOT NULL) OR (status <> 'ok' AND proposal_at IS NULL)`; `jsonb_typeof(input_snapshot) = 'object'`; `jsonb_typeof(output_snapshot) = 'object'`.  **Индексы (проект):** `(site_id,maintenance_rule_id,produced_at DESC)`; `(site_id,equipment_id,produced_at DESC)`.  
**Внешние ключи:**
- `(site_id, system_id, maintenance_rule_id)` → `maintenance_rules(site_id, system_id, maintenance_rule_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, equipment_id)` → `equipment(site_id, system_id, equipment_id)` (опциональная связь); ON DELETE RESTRICT
- `(predictor_version_id)` → `predictor_versions(predictor_version_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `orchestration_decisions` · P0

Агентный выбор допустимого срока после сравнения двух прогнозов и проверки регламента.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `orchestration_decision_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор решения |
| `site_id` | `UUID` | Нет | — | Объект |
| `system_id` | `UUID` | Нет | — | Инженерная система |
| `maintenance_rule_id` | `UUID` | Нет | — | Правило ТО |
| `rule_forecast_id` | `UUID` | Да | — | Результат алгоритмического метода |
| `ai_forecast_id` | `UUID` | Да | — | Результат ML-метода |
| `orchestrator_version_id` | `UUID` | Нет | — | Версия алгоритма выбора / агента |
| `selected_method` | `TEXT` | Нет | — | rule / ai / conservative_fallback / manual_review |
| `selected_at` | `TIMESTAMPTZ` | Да | — | Предложенный итоговый срок; NULL при ручном уточнении |
| `regulatory_deadline_at` | `TIMESTAMPTZ` | Нет | — | Проверяемый обязательный дедлайн |
| `requires_human_approval` | `BOOLEAN` | Нет | `true` | Нужна ли проверка ответственного |
| `reason` | `TEXT` | Нет | — | Обоснование решения и причины отклонения иных вариантов |
| `comparison_snapshot` | `JSONB` | Нет | `{}` | Два прогноза, версии, отклонения и политика |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время решения |

**PK:** `orchestration_decision_id`.  **UNIQUE / уникальные ключи:** `(site_id,system_id,maintenance_rule_id,orchestration_decision_id)`.  **CHECK (проект):** `selected_method IN ('rule','ai','conservative_fallback','manual_review')`; `(selected_method = 'manual_review' AND selected_at IS NULL) OR (selected_method <> 'manual_review' AND selected_at IS NOT NULL)`; `selected_at IS NULL OR selected_at <= regulatory_deadline_at`; `jsonb_typeof(comparison_snapshot) = 'object'`; `length(trim(reason)) > 0`.  **Индексы (проект):** `(site_id,maintenance_rule_id,created_at DESC)`.  
**Внешние ключи:**
- `(site_id, system_id, maintenance_rule_id)` → `maintenance_rules(site_id, system_id, maintenance_rule_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, system_id, maintenance_rule_id, rule_forecast_id)` → `forecast_runs(site_id, system_id, maintenance_rule_id, forecast_run_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, system_id, maintenance_rule_id, ai_forecast_id)` → `forecast_runs(site_id, system_id, maintenance_rule_id, forecast_run_id)` (опциональная связь); ON DELETE RESTRICT
- `(orchestrator_version_id)` → `predictor_versions(predictor_version_id)` (обязательная ссылка); ON DELETE RESTRICT

#### `ai_quality_checks` · P0

Результат анализа визуально подтверждаемых изменений; не заменяет приёмку инженером.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `ai_quality_check_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор проверки |
| `site_id` | `UUID` | Нет | — | Объект |
| `work_order_id` | `UUID` | Нет | — | Задание |
| `work_report_id` | `UUID` | Да | — | Редакция отчёта, на которой запускали модель |
| `before_file_id` | `UUID` | Да | — | Фото до, если предоставлено |
| `after_file_id` | `UUID` | Да | — | Фото после, если предоставлено |
| `predictor_version_id` | `UUID` | Нет | — | Версия vision-модели |
| `status` | `TEXT` | Нет | — | ok / inconclusive / failed |
| `visible_change` | `TEXT` | Да | — | Описание видимых изменений |
| `assessment` | `TEXT` | Нет | — | consistent / concern / inconclusive |
| `confidence` | `NUMERIC(5,4)` | Да | — | Уверенность при наличии |
| `findings` | `JSONB` | Нет | `{}` | Наблюдения, доказательства, ограничения |
| `created_at` | `TIMESTAMPTZ` | Нет | `now()` | Время анализа |

**PK:** `ai_quality_check_id`.  **CHECK (проект):** `status IN ('ok','inconclusive','failed')`; `assessment IN ('consistent','concern','inconclusive')`; `confidence IS NULL OR confidence BETWEEN 0 AND 1`; `jsonb_typeof(findings) = 'object'`.  **Индексы (проект):** `(site_id,work_order_id,created_at DESC)`.  
**Внешние ключи:**
- `(site_id, work_order_id)` → `work_orders(site_id, work_order_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, work_order_id, work_report_id)` → `work_reports(site_id, work_order_id, work_report_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, work_order_id, before_file_id)` → `evidence_files(site_id, work_order_id, evidence_file_id)` (опциональная связь); ON DELETE RESTRICT
- `(site_id, work_order_id, after_file_id)` → `evidence_files(site_id, work_order_id, evidence_file_id)` (опциональная связь); ON DELETE RESTRICT
- `(predictor_version_id)` → `predictor_versions(predictor_version_id)` (обязательная ссылка); ON DELETE RESTRICT

### 06 · История

#### `audit_events` · P0

Append-only журнал изменений состояния, нормативов, назначений и решений.

| Поле | PostgreSQL | Null | Default | Назначение |
|---|---|:---:|---|---|
| `audit_event_id` | `UUID` | Нет | `gen_random_uuid()` | Идентификатор события |
| `site_id` | `UUID` | Нет | — | Объект |
| `actor_type` | `TEXT` | Нет | — | user / system / ai |
| `actor_user_id` | `UUID` | Да | — | Исполнитель-человек, если он есть |
| `entity_type` | `TEXT` | Нет | — | Тип изменённого ресурса |
| `entity_id` | `UUID` | Нет | — | Идентификатор ресурса |
| `action` | `TEXT` | Нет | — | Тип изменения / перехода |
| `before_snapshot` | `JSONB` | Да | — | Данные до изменения с удалёнными секретами |
| `after_snapshot` | `JSONB` | Да | — | Данные после изменения с удалёнными секретами |
| `occurred_at` | `TIMESTAMPTZ` | Нет | `now()` | Дата события |

**PK:** `audit_event_id`.  **CHECK (проект):** `actor_type IN ('user','system','ai')`; `(actor_type = 'user' AND actor_user_id IS NOT NULL) OR (actor_type <> 'user')`.  **Индексы (проект):** `(site_id,entity_type,entity_id,occurred_at)`; `(site_id,occurred_at DESC)`.  
**Внешние ключи:**
- `(site_id)` → `sites(site_id)` (обязательная ссылка); ON DELETE RESTRICT
- `(site_id, actor_user_id)` → `site_memberships(site_id, user_id)` (опциональная связь); ON DELETE RESTRICT

## 4. Ограничения, требующие транзакции, сервисного кода или триггера

Табличные `CHECK` и `FOREIGN KEY` **не могут** доказать все межстрочные и временные условия. Ниже перечислены обязательные инварианты для реализации DDL/API — их нельзя считать уже реализованными только из-за наличия диаграммы.

| Инвариант | Где контролировать | Проверка |
|---|---|---|
| Один объект у оборудования, операции, наряда, отчёта, фото, прогноза | Составные FK с `site_id` и при необходимости `system_id` | Попытка привязать фото/прогноз/оборудование другого объекта отклоняется |
| Родительское оборудование из той же инженерной системы, без циклов | `equipment` + recursive check / trigger | Циклический `parent_equipment_id` отклоняется |
| Оборудование под строкой ТО принадлежит нужной системе | FK `(site_id,system_id,...)` в `rule_equipment` | Межсистемная связка невозможна |
| Число действующих назначенных исполнителей = `required_people_snapshot` при старте | Транзакционный сервис назначений + блокировка наряда | Одного техника для 2-местной операции недостаточно |
| Назначение через `crew_id` действительно принадлежит выбранной бригаде | Сервис назначений + `crew_members` с периодом членства | Чужой сотрудник не указывается членом бригады |
| Квалификация соответствует правилу и действующим допускам | Сервис назначений с учётом `rule_required_skills`/`user_skills` | Техник без допуска не назначается |
| Нет пересекающихся нагрузок в рабочем интервале | Сервис с блокировками, учёт `availability_slots` и занятости | Один техник не получает одновременные конфликтующие задания |
| Даты `5/год` и `1/квар` определены политикой и точкой отсчёта | Валидация `schedule_parameters` и генератор | Не выводить самовольные даты из одной строки Excel |
| Граница дня учитывает timezone объекта | Сервис дат / timezone IANA из `sites` | ТО1 до конца суток в локальном времени объекта |
| `planned_date`, `planned_at`, `regulatory_deadline_on`, `regulatory_deadline_at` согласованы | Доменный сервис/триггер с часовым поясом `sites.timezone` | Время/дата не противоречат друг другу |
| Редакции и утверждённые графики неизменяемы | Триггеры/права и создание новой версии | `UPDATE` истории отклоняется, данные старого отчёта сохраняются |
| Статусы наряда проходят допустимые переходы | FSM backend + атомарные транзакции + audit | `technician` не закрывает задачу без `acceptance_review` |
| Флаг `overdue` вычисляется из статуса и обязательной даты | View/query/планировщик, а не отдельный конечный статус | Просрочка не стирает основное состояние наряда |
| Фото «до» и «после» относятся к одной задаче и правильному этапу | Составные FK + trigger по `evidence_files.stage` | Нельзя выбрать фото из соседнего задания; этап не перепутан |
| `work_readings.equipment_id` входит в набор устройств наряда | Сервис ввода показаний / проверка `work_order_equipment` | Показания от чужого устройства не приписываются наряду |
| Пункт чек-листа подходит к операции наряда | Сервис отчёта / шаблон и `operation_snapshot` | Ответ на пункт другой операции отклоняется |
| Оборудование AI-прогноза связано с правилом обслуживания на дату среза | Доменная проверка `rule_equipment` с интервалом | Прогноз по устройству другого правила недопустим |
| `rule_forecast_id` ссылается на method=rule, `ai_forecast_id` на method=ai | Trigger/service дополнительно к составным FK | Нельзя поменять методы местами или использовать разные срезы |
| Ссылки двух прогнозов указывают на одно правило, объект и совместимый срез входа | Составные FK + доменная проверка совместимости snapshot | Оркестратор не сравнивает чужие прогнозы |
| Версия предиктора соответствует типу запуска | Trigger/service `predictor_versions.kind` | `vision` не используется как `rule`-планировщик |
| Выбранный слот не позднее регламентного дедлайна | CHECK для `orchestration_decisions` и `schedule_entries`, сервис пересчёта | Запрещённая рекомендация остаётся диагностикой, а не планом |
| Ручной перенос срока не стирает факт просрочки | Неизменяемый `regulatory_deadline_at` + audit | Срок не изменяют задним числом для улучшения SLA |
| Отчёты, измерения, оценки и приёмки неизменяемы после принятия | Новая редакция отчёта + audit, права на UPDATE/DELETE | Повторная отправка сохраняет старую редакцию и решение |
| Содержимое аудита не редактируется | Append-only доступ, триггер RESTRICT UPDATE/DELETE | Историю нельзя подменить через обычный CRUD |
| Отмена/закрытие не удаляет исторические данные | Soft status + `ON DELETE RESTRICT` | FK остаются и после архивирования оборудования |

**Ключевой нюанс:** при использовании внешних ключей `MATCH SIMPLE` для необязательной составной ссылки необходимо, чтобы обязательный `site_id` (и при необходимости `system_id`) заполнялся всегда, а опциональным был только последний идентификатор; проверку запрещённых «частично-NULL» значений выполнять явно.

### 4.1. Согласованные переходы `work_orders.status`

`draft/clarification → assigned → in_progress → in_review → completed`.  
`in_review → rework → in_progress → in_review` — цикл доработки с **новой редакцией `work_reports`**.  
`draft/assigned → cancelled` — отмена при наличии полномочий.  
`completed` — терминальный статус; повторное открытие допускается только через отдельное решение и новый наряд / формальную операцию аудита после согласования с заказчиком.

Признак `overdue` выводится как `(now() > regulatory_deadline_at AND status NOT IN ('completed','cancelled'))`, с учётом того, что отмена регламентного наряда сама по себе не означает исполнения ТО; показатели SLA должны определяться отдельно по обязательным календарным записям.

### 4.2. Разделение плановых, фактических и нормативных данных

`maintenance_rules` задаёт **что и как часто**. `schedule_entries` фиксирует **на какую дату запланировано** (`planned_date DATE`), а `planned_at` — момент начала при известном времени, а `regulatory_deadline_on` — предельный локальный календарный день. `work_orders` — **что выдано исполнителям**. `work_reports` и `work_readings` — **что фактически представлено**. `acceptance_reviews` — **кто и с каким решением принял**. Запрос «график на месяц» собирается по `schedule_entries` с JOIN к правилам и нарядам; календарный UI раскладывает даты по колонкам самостоятельно.

### 4.3. Нормо-часы и численность — **не определены однозначно заказчиком**

В источнике у п. 1.4 указаны `2` человека и `60` нормо-часов. Неизвестно, **60 — уже суммарные человеко-часы либо 60 часов на каждого**. `maintenance_rules.norm_hours = 60`, `required_people = 2`, `norm_hours_basis = 'unknown'` сохраняют оригинал, не вычисляя скрыто `120`. Итоговую нагрузку системы следует рассчитывать только при установленной семантике (`total_person_hours` либо `per_person`). То же правило относится к отчётам и аналитике SLA.

### 4.4. Формат двух прогнозов и объяснимость

Оба метода пишут в `forecast_runs` одинаковую структуру: `maintenance_rule_id`, `equipment_id?`, `method`, `input_snapshot`, `predictor_version_id`, `proposal_at?`, `regulatory_deadline_at`, `status`, `confidence?`, `rationale` и `output_snapshot`. Для rule-based уверенность может отсутствовать. ML-кандидат позже дедлайна помечается как недопустимый и **не может** стать `orchestration_decisions.selected_at`.

Оркестратор не должен заявлять «AI точнее» по двум числам. Выбор рабочего слота основан на ограничениях, доступных ресурсах, достоверности данных и версии policy; измеримая **точность прогноза** требует эталонной истории состояния/отказов, которой в заказческом Excel нет.

### 4.5. Контроль по фотографиям

`evidence_files(stage='before'|'after')` хранит пары в одном наряде. `ai_quality_checks.assessment` принимает `consistent`, `concern`, `inconclusive`; одно фото или невизуальная операция не дают основания утверждать качество выполнения. Решение инженера хранится отдельно в `acceptance_reviews` и не заменяется AI-оценкой. Для операций снятия давления/температуры наиболее значимы `work_readings` и протокол, а не визуальная разница между двумя фото.

## 5. Матрица покрытия критериев TL02

| Критерий задачи | Таблицы / поля | Приёмочная демонстрация |
|---|---|---|
| Все 6 операций исходного Excel | `operation_templates`, `maintenance_types`, `maintenance_rules` | 6 шаблонов, 6 правил с исходными кодами, параметрами и единицами |
| График на любой месяц | `schedule_plans`, `schedule_entries` | Планы разных месяцев, строки дат в БД, 28/29/30/31 столбцов строит UI |
| Новые строки работ | `operation_templates`, `maintenance_rules` | Добавить 1.7 без миграции БД |
| Несколько единиц оборудования под строкой | `rule_equipment`, `equipment` | Привязать манометр и теплосчётчик к нужным строкам |
| История источников и регламентов | `regulation_documents`, `regulation_editions`, `maintenance_rules` | Изменить редакцию без изменения предыдущей |
| Исполнители и бригады | `site_memberships`, `skills`, `crews`, `work_assignments` | На работу с 2 чел. назначить двух техников |
| План / факт / фото / приёмка | `work_orders`, `work_reports`, `work_readings`, `evidence_files`, `acceptance_reviews` | Отчёт с фото, показаниями и решением инженера |
| Два независимых прогноза | `predictor_versions`, `forecast_runs` | По одному `method = rule` и `method = ai` на то же правило |
| Решение оркестратора | `orchestration_decisions` | Ссылки на оба запуска, причины выбора, обязательная дата |
| Фотоанализ качества | `ai_quality_checks`, `evidence_files` | Вывод `inconclusive` при плохих/неполных фото |
| Нет смешения объектов | Составные `site_id`/`system_id` FK | Негативный тест FK не позволяет привязать чужое оборудование или фото |
| Трассировка и воспроизводимость | `audit_events`, `*_snapshot`, версии | Восстановить исходные входы, регламент, метод и решение |

## 6. Минимальные проверочные сценарии для реализации DDL/API

1. Сохранить 6 строк из XLSX, проверить названия, виды, периодичность, людей и часы **без нормализации в выдуманные даты**.
2. Построить октябрь с 31 датой и тремя ежедневными операциями; получить по 31 плановой записи на каждую (`93` появления ТО1), не смешивая их со статусом выполнения.
3. Построить февраль с 28/29 днями в зависимости от года, не добавляя новые поля в БД.
4. Для `5/год` без явного `schedule_parameters` получить состояние `requires_policy`, а не произвольные пять дат.
5. Добавить новую операцию `1.7` и две единицы оборудования под неё без миграции.
6. Обновить нормативную редакцию и подтвердить неизменность старого `work_orders.operation_snapshot`.
7. Создать наряд с `required_people_snapshot = 2` и убедиться, что одной активной индивидуальной записи `work_assignments` недостаточно для запуска.
8. Запретить связывание правила объекта A с оборудованием объекта B (FK), а также фото другого задания с AI-проверкой.
9. Создать по одному прогнозу каждым методом, сохранить `input_snapshot` и `predictor_version_id`, сравнить решения.
10. Попытаться записать в оркестратор и планировку срок позже `regulatory_deadline_at`: отклонить с CHECK.
11. Пропущенный AI-прогноз обработать fallback-решением без выдуманного результата.
12. Сформировать две редакции отчёта по возвращённому заданию и сохранить оба решения приёмки.
13. Запретить закрытие наряда от имени Техника в обход Инженера и отметки приёмки.
14. Сохранить числовые показания манометра с единицей, временем и исполнителем; не заменять факт значением из AI.
15. При анализе визуально непроверяемой операции выдать `inconclusive`, не переводя наряд автоматически в `completed`.

**Важно:** это сценарии для следующего этапа (DDL/ORM/API). **Фактическое выполнение SQL-тестов не заявляется**: эта задача создаёт логическую ER-модель, а не устанавливает базу.

## 7. Передача в дальнейшие задачи

- **DB / Backend:** на базе каталога `model_catalog.json` подготовить миграции, ORM, сервисы транзакционного контроля, SQL-тесты составных FK и запрета нарушений дедлайна. Сохранять историю миграций, не переписывать старые применённые файлы.
- **Scheduler / Orchestrator:** использовать CalendarPattern и операторские версии для `1/квар` и `5/год`; согласовать снимок двух методов и policy_version; решение оркестратора должно быть воспроизводимым.
- **Frontend:** отображать матрицу `(операция × календарная дата)` динамически; часы и персонал не вычислять из неподтверждённого смысла `norm_hours`.
- **ML:** согласовать стандартизированный JSON-выход `forecast_runs` и `ai_quality_checks`; не выдавать инференс за эталонную диагностику.
- **QA:** использовать матрицу 15 сценариев выше и негативные тесты межобъектных связей.
- **Аналитик / заказчик:** прояснить семантику нормо-часов, периоды `1/квар` и `5/год`, статус необязательных CV/NLP/RAG в обновлённом scope и политику переоткрытия принятых работ.

### Артефакты и согласование

- `erd.drawio` — редактируемая многолистовая ER-диаграмма; все FK вынесены также на отдельный лист.
- `erd.svg` — масштабируемый обзор модели с таблицами, PK и ключевыми связями.
- `model_catalog.json` — машинно-читаемый источник таблиц, полей, типов и 72 FK для последующей генерации DDL и тестов.

**Условие готовности TL02:** диаграмма, спецификация и список инвариантов согласованы командой; вопрос о реально существующих SQL-миграциях относится к отдельной задаче, а не к этому документу.
