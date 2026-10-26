# FixRate AI — спецификация ER-модели PostgreSQL / pgvector

**Версия спецификации:** 1.2 (DDL v3.1 + миграция 003)<br>
**Дата:** 22.10.2026<br>
**Статус:** миграции применены на тестовой PostgreSQL 16 + pgvector; smoke, тест нормативных версий и 50/50 SQL-сценариев пройдены, бизнес/API/ML-проверки остаются отдельным этапом<br>
**Исходники:** `db/001_init.sql` (начальная DDL v3.1), `db/003_normative_source_versions.sql` (актуальная последовательная миграция), `docs/database/erd.md`<br>
**СУБД:** PostgreSQL 16 + pgvector (расширение должно быть установлено на сервере)<br>
**Модель:** 18 таблиц, 188 атрибутов, 33 ограничения FK.<br>
**Визуальная схема:** [актуальная ER-диаграмма в Mermaid по доменам](erd.md); единый холст `erd.svg` пока отражает состояние до миграции 003.

> **Область проверки:** цепочка `001 → 002 → 003` применена на чистой PostgreSQL 16.15 + pgvector 0.8.7; smoke, отдельный тест редакций/исторической цены и 50 SQL-сценариев матрицы пройдены. Соответствие 18 SQLAlchemy-моделей живой схеме проверено 10 интеграционными тестами. Бизнес-API и ML-интеграция по-прежнему не заявляются готовыми.

## Содержание
- [Назначение и границы](#назначение-и-границы)
- [Архитектурный процесс](#архитектурный-процесс)
- [Сущности и атрибуты](#сущности-и-атрибуты)
- [Связи и кардинальности](#связи-и-кардинальности)
- [Ограничения и индексы](#ограничения-и-индексы)
- [20 согласованных решений](#20-согласованных-решений)
- [Сквозные сценарии](#сквозные-сценарии)
- [Пределы автоматической гарантии](#пределы-автоматической-гарантии)
- [План проверки и приёмки](#план-проверки-и-приёмки)

## Назначение и границы
База данных обеспечивает хранение заявок на ремонт жилых/эксплуатируемых зданий, связанных фото и дефектов, измерений и подтверждений, запусков CV/NLP/RAG, нормативов и прайсов, индексируемых текстовых фрагментов, версионных смет и их проверок человеком. Цель — воспроизводимый черновик ведомости объёмов работ (ВОР) с подтверждаемыми исходными данными и источниками цен.

**Не входит в текущую модель:** управление подрядчиками/складом/закупками/платежами; утверждённая нормативная методика на все виды ремонта; полная CRM/ERP; синхронизация всех внешних систем; гарантия точного измерения площади по одному фото; утверждение стоимости генеративной моделью. Таблицы пользователей — базовые роли, а не готовая система RBAC или SSO.

## Архитектурный процесс

1. Оператор выбирает здание и создаёт `repair_requests`, прикладывает 0..N файлов `request_photos` (но фото или текст по бизнес-правилу обязателен).
2. Создаётся `ai_runs` со снимком входа; результаты CV/NLP/RAG пишутся в `ai_results`.
3. AI предлагает `defects` и значения в `defect_measurements`; достоверность и происхождение параметров фиксируются независимо. Фотографии привязываются к дефекту через M:N `defect_photos`.
4. Если параметров недостаточно, создаются `request_clarifications`, процесс ждёт ввода. При исправлениях сохраняются предыдущие значения.
5. RAG ищет по `normative_chunks` (эмбеддинги pgvector и лексический поиск), связывает найденное с `rates` и `norm_sources`. Поиск предлагает кандидатов; применимость проверяет валидатор/человек.
6. Программный калькулятор создаёт `estimates` и `estimate_items`, при необходимости `estimate_materials`. Все принятые значения, источник, формула и итог сохраняются.
7. Сметчик проверяет и, если нужно, создаёт **новую версию** сметы. Действия фиксируются в `audit_events`, старые версии не переписываются.

**Типы денежных/измерительных величин:** `NUMERIC`, а не `FLOAT`; время — `TIMESTAMPTZ`; идентификаторы — UUID; дополнительный контекст и снимки — JSONB. Файлы фотографий размещаются вне СУБД, в таблице — только ключ и метаданные.

## Сущности и атрибуты

Условные обозначения: **PK** — первичный ключ; **FK** — внешний; **PK+FK** — одновременно; «NULL да» означает, что по текущему DDL поле необязательно. Атрибуты воспроизводят **фактическую SQL-схему**, а не ранние черновые варианты.

### 1. `users` — Пользователи

Учётные записи оператора, сметчика и администратора; сохранение авторства и истории при деактивации.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `user_id` | `UUID` | PK | нет | ID учётной записи |
| `full_name` | `VARCHAR(200)` | — | нет | Отображаемое ФИО |
| `email` | `VARCHAR(255)` | — | нет | Email; уникальность без учёта регистра |
| `password_hash` | `TEXT` | — | да | Хеш пароля, если используется собственная авторизация |
| `role` | `VARCHAR(30)` | — | нет | Роль: operator/estimator/admin |
| `is_active` | `BOOLEAN` | — | нет | Логическая деактивация без физического удаления |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата регистрации |

### 2. `buildings` — Здания

Карточки объектов недвижимости и общие, часто используемые характеристики здания.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `building_id` | `UUID` | PK | нет | ID объекта |
| `address` | `TEXT` | — | нет | Адрес здания |
| `building_type` | `VARCHAR(100)` | — | да | Тип здания |
| `construction_year` | `SMALLINT` | — | да | Год постройки |
| `floors_count` | `SMALLINT` | — | да | Количество этажей |
| `total_area` | `NUMERIC(12,2)` | — | да | Площадь здания, м² |
| `wall_material` | `VARCHAR(100)` | — | да | Основной материал стен |
| `additional_properties` | `JSONB` | — | нет | Дополнительные свойства в JSON-объекте |
| `is_active` | `BOOLEAN` | — | нет | Объект активен/архивирован |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата внесения |

### 3. `repair_requests` — Заявки

Единая заявка на ремонт; состояние обработки и принадлежность объекту и автору.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `request_id` | `UUID` | PK | нет | ID заявки |
| `building_id` | `UUID` | FK | нет | Здание, к которому относится заявка |
| `created_by` | `UUID` | FK | нет | Автор заявки |
| `title` | `VARCHAR(255)` | — | нет | Короткое название обращения |
| `description` | `TEXT` | — | да | Свободный текст заявления |
| `location_description` | `TEXT` | — | да | Расположение дефекта в здании |
| `status` | `VARCHAR(30)` | — | нет | created/processing/needs_clarification/ready_for_review/closed/cancelled/failed |
| `cancellation_reason` | `TEXT` | — | да | Причина отмены |
| `created_at` | `TIMESTAMPTZ` | — | нет | Время создания |
| `updated_at` | `TIMESTAMPTZ` | — | нет | Время изменения; автоматически обновляется триггером `trg_requests_updated_at` |

**Связи FK:** `(building_id)` → `buildings(building_id)`; `(created_by)` → `users(user_id)`.

### 4. `request_photos` — Фотографии

Метаданные фотографий и ссылки на безопасное файловое хранилище.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `photo_id` | `UUID` | PK | нет | ID фотографии |
| `request_id` | `UUID` | FK | нет | Заявка — владелец фото |
| `storage_key` | `TEXT` | — | нет | Уникальный ключ в файловом хранилище |
| `original_filename` | `TEXT` | — | нет | Изначальное название файла |
| `mime_type` | `VARCHAR(100)` | — | нет | Тип содержимого |
| `file_size` | `BIGINT` | — | нет | Размер в байтах (>0) |
| `checksum_sha256` | `CHAR(64)` | — | нет | SHA-256 файла |
| `uploaded_at` | `TIMESTAMPTZ` | — | нет | Время загрузки |

**Связи FK:** `(request_id)` → `repair_requests(request_id)`.

### 5. `defect_types` — Типы повреждений

Справочник допустимых типов повреждений.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `defect_type_id` | `UUID` | PK | нет | ID типа дефекта |
| `code` | `VARCHAR(50)` | — | нет | Уникальный внутренний код |
| `name` | `VARCHAR(200)` | — | нет | Наименование дефекта |
| `description` | `TEXT` | — | да | Пояснение типа |
| `is_active` | `BOOLEAN` | — | нет | Признак актуальности |

### 6. `defects` — Повреждения

Конкретные повреждения заявки с раздельным AI-предложением и подтверждением человеком.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `defect_id` | `UUID` | PK | нет | ID повреждения |
| `request_id` | `UUID` | FK | нет | Заявка с дефектом |
| `defect_type_id` | `UUID` | FK | да | Тип по справочнику; необязательно до классификации |
| `source_ai_result_id` | `UUID` | FK | да | Результат AI, предложивший дефект |
| `description` | `TEXT` | — | да | Описание повреждения |
| `location_description` | `TEXT` | — | да | Локализация в здании |
| `confirmation_status` | `VARCHAR(30)` | — | нет | suggested/confirmed/rejected |
| `confirmed_by` | `UUID` | FK | да | Подтвердивший пользователь |
| `confirmed_at` | `TIMESTAMPTZ` | — | да | Время подтверждения |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата создания |

**Связи FK:** `(request_id)` → `repair_requests(request_id)`; `(defect_type_id)` → `defect_types(defect_type_id)`; `(source_ai_result_id, request_id)` → `ai_results(ai_result_id, request_id)`; `(confirmed_by)` → `users(user_id)`.

### 7. `defect_photos` — Фотографии повреждений (M:N)

Связующая таблица M:N между повреждениями и фотографиями одной заявки.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `defect_id` | `UUID` | PK FK | нет | ID дефекта; часть составного PK |
| `photo_id` | `UUID` | PK FK | нет | ID фото; часть составного PK |
| `request_id` | `UUID` | FK | нет | ID заявки для проверки совпадения обоих объектов |
| `is_primary` | `BOOLEAN` | — | нет | Основное фото: максимум одно для дефекта |
| `created_at` | `TIMESTAMPTZ` | — | нет | Время создания связи |

**Связи FK:** `(defect_id, request_id)` → `defects(defect_id, request_id)`; `(photo_id, request_id)` → `request_photos(photo_id, request_id)`.

### 8. `defect_measurements` — Измерения повреждений

Типизированные измерения дефекта с единицами, происхождением, проверкой и историей правок.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `measurement_id` | `UUID` | PK | нет | ID измерения |
| `defect_id` | `UUID` | FK | нет | Измеряемый дефект |
| `request_id` | `UUID` | FK | нет | Заявка; участвует в проверке принадлежности |
| `parameter_code` | `VARCHAR(60)` | — | нет | Код параметра: area/length/width/depth и др. |
| `value` | `NUMERIC(16,6)` | — | нет | Измеренное числовое значение |
| `unit_code` | `VARCHAR(20)` | — | нет | Единица измерения |
| `source_type` | `VARCHAR(30)` | — | нет | manual/text/photo/document/derived |
| `source_ai_result_id` | `UUID` | FK | да | AI-результат — источник величины, если был |
| `recorded_by` | `UUID` | FK | да | Кто внёс измерение |
| `is_approximate` | `BOOLEAN` | — | нет | Значение приблизительное |
| `verification_status` | `VARCHAR(30)` | — | нет | unverified/confirmed/rejected |
| `supersedes_measurement_id` | `UUID` | FK | да | Заменяемое предыдущее измерение того же дефекта |
| `is_current` | `BOOLEAN` | — | нет | Единственная текущая версия каждого параметра дефекта |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата фиксации |

**Связи FK:** `(defect_id, request_id)` → `defects(defect_id, request_id)`; `(source_ai_result_id, request_id)` → `ai_results(ai_result_id, request_id)`; `(recorded_by)` → `users(user_id)`; `(supersedes_measurement_id, defect_id)` → `defect_measurements(measurement_id, defect_id)`.

**Важно:** частичный индекс гарантирует максимум одну `is_current=true` для `(defect_id, parameter_code)`, но правильное переключение версий, проверку единиц и устранение циклов выполняет приложение/транзакция.

### 9. `ai_runs` — Запуски AI

Один запуск общего AI-пайплайна, входной снимок, статус и техническое состояние.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `run_id` | `UUID` | PK | нет | ID полного AI-запуска |
| `request_id` | `UUID` | FK | нет | Заявка, обработанная пайплайном |
| `status` | `VARCHAR(30)` | — | нет | pending/running/completed/failed/needs_clarification |
| `pipeline_version` | `VARCHAR(50)` | — | нет | Версия оркестратора/пайплайна |
| `input_snapshot` | `JSONB` | — | нет | Снимок входных параметров и идентификаторов фото |
| `error_message` | `TEXT` | — | да | Диагностическая ошибка |
| `started_at` | `TIMESTAMPTZ` | — | нет | Начало обработки |
| `completed_at` | `TIMESTAMPTZ` | — | да | Время завершения |

**Связи FK:** `(request_id)` → `repair_requests(request_id)`.

### 10. `ai_results` — Результаты модулей AI

Промежуточные результаты CV, NLP и RAG, модель/версия, вход/выход, время обработки.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `ai_result_id` | `UUID` | PK | нет | ID результата конкретного ML-модуля |
| `run_id` | `UUID` | FK | нет | Полный запуск пайплайна |
| `request_id` | `UUID` | FK | нет | Дублирование ID заявки для составной FK-проверки |
| `module_type` | `VARCHAR(20)` | — | нет | cv/nlp/rag |
| `model_name` | `VARCHAR(150)` | — | да | Идентификатор модели |
| `model_version` | `VARCHAR(100)` | — | да | Версия модели |
| `input_reference` | `JSONB` | — | нет | Сведения об источниках входа |
| `result_data` | `JSONB` | — | нет | Структурированный JSON результата |
| `status` | `VARCHAR(30)` | — | нет | running/completed/failed/uncertain |
| `processing_time_ms` | `INTEGER` | — | да | Задержка обработки, мс |
| `created_at` | `TIMESTAMPTZ` | — | нет | Время записи результата |

**Связи FK:** `(run_id, request_id)` → `ai_runs(run_id, request_id)`.

### 11. `norm_sources` — Источники нормативов и прайсов

Проверяемые нормативные документы и коммерческие/демо-прайсы с редакцией и регионом.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `source_id` | `UUID` | PK | нет | ID конкретного источника/редакции |
| `source_series_id` | `UUID` | UK | нет | Стабильный ID семейства редакций одного документа/прайса |
| `supersedes_source_id` | `UUID` | FK | да | Предыдущая редакция того же семейства |
| `source_type` | `VARCHAR(30)` | — | нет | FER / FERR / TER / TERR / COMMERCIAL / DEMO |
| `title` | `TEXT` | — | нет | Название нормативного документа или прайса |
| `edition` | `VARCHAR(100)` | — | да | Редакция |
| `region` | `VARCHAR(100)` | — | да | Регион применимости |
| `provider_name` | `TEXT` | — | да | Организация/поставщик коммерческого прайса |
| `publication_date` | `DATE` | — | да | Дата публикации |
| `effective_date` | `DATE` | — | да | Дата вступления в силу |
| `valid_to` | `DATE` | — | да | Конец периода применимости, если известен |
| `default_currency` | `CHAR(3)` | — | да | Валюта коммерческого источника |
| `source_url` | `TEXT` | — | да | Ссылка на источник |
| `document_reference` | `TEXT` | — | да | Библиографические или нормативные реквизиты |
| `is_verified` | `BOOLEAN` | — | нет | Служебный признак проверки источника |
| `is_current` | `BOOLEAN` | — | нет | Явно рекомендуемая редакция (одна на серию) |
| `created_at` | `TIMESTAMPTZ` | — | нет | Когда добавлен |

**Версионирование:** новая редакция создаётся отдельной строкой с тем же `source_series_id`; `supersedes_source_id` указывает предыдущую редакцию. Частичный UNIQUE допускает только одну `is_current=true` в серии. Периоды всё равно проверяются на дату расчёта: пересекающиеся периоды без явного правила выбора считаются неоднозначностью, а не поводом выбрать строку автоматически.

### 12. `rates` — Расценки

Структурированные записи расценок, масштаб нормативной единицы и состав стоимости.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `rate_id` | `UUID` | PK | нет | ID строки расценки |
| `source_id` | `UUID` | FK | нет | Нормативный документ/прайс |
| `rate_code` | `VARCHAR(100)` | — | да* | Код работы; для новых строк после миграции 003 обязателен непустой код |
| `work_name` | `TEXT` | — | нет | Название работы |
| `description` | `TEXT` | — | да | Описание состава работы |
| `unit_code` | `VARCHAR(20)` | — | нет | Базовая единица измерения |
| `rate_unit_multiplier` | `NUMERIC(14,4)` | — | нет | Нормативный масштаб, например цена за 100 м² |
| `base_price` | `NUMERIC(18,4)` | — | да | Базовая цена или нормативная стоимость |
| `currency` | `CHAR(3)` | — | да | Код валюты |
| `price_basis` | `VARCHAR(30)` | — | нет | commercial/normative_base/demo |
| `cost_scope` | `VARCHAR(30)` | — | нет | work_only/all_inclusive/resource_based |
| `price_date` | `DATE` | — | да | Дата базы/периода цены, если отличается от дат источника |
| `is_active` | `BOOLEAN` | — | нет | Признак доступности для новых подборов |

**Связи FK:** `(source_id)` → `norm_sources(source_id)`. Триггер проверяет соответствие `price_basis` типу источника, подтверждение активной нормативной/коммерческой ставки и валюту коммерческого прайса.

### 13. `normative_chunks` — Фрагменты и эмбеддинги RAG

Текстовые фрагменты норм и их векторы для семантического и лексического поиска.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `chunk_id` | `UUID` | PK | нет | ID индексируемого фрагмента |
| `source_id` | `UUID` | FK | нет | Исходный нормативный документ |
| `rate_id` | `UUID` | FK | да | Конкретная расценка этого же источника, если есть |
| `chunk_index` | `INTEGER` | — | нет | Номер фрагмента внутри источника |
| `content` | `TEXT` | — | нет | Текст для поиска |
| `embedding` | `VECTOR` | — | да | Числовой вектор pgvector |
| `embedding_model` | `VARCHAR(150)` | — | да | Модель эмбеддингов |
| `search_vector` | `TSVECTOR` | — | да | Вычисляемое полнотекстовое представление PostgreSQL |
| `source_locator` | `JSONB` | — | нет | Страница/раздел/координаты в исходном документе |
| `metadata` | `JSONB` | — | нет | Дополнительные метаданные индексации |
| `content_hash` | `CHAR(64)` | — | нет | Хеш текста |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата индексации |

**Связи FK:** `(source_id)` → `norm_sources(source_id)`; `(rate_id, source_id)` → `rates(rate_id, source_id)`.

**Важно:** `search_vector` создаётся средствами PostgreSQL `to_tsvector('russian', content)` и **не является BM25**. `embedding VECTOR` пока не ограничен размерностью: модель, размерность, индексы HNSW/IVFFlat и реализация BM25 согласуются с ML. `rate_id` необязателен для общих фрагментов документа.

### 14. `estimates` — Сметы и версии

Версионированные предварительные сметы, проверка сметчиком и снимок входных параметров.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `estimate_id` | `UUID` | PK | нет | ID версии сметы |
| `request_id` | `UUID` | FK | нет | Заявка — владелец сметы |
| `version` | `INTEGER` | — | нет | Положительный номер версии внутри заявки |
| `based_on_run_id` | `UUID` | FK | да | AI-запуск той же заявки, если использовался |
| `status` | `VARCHAR(30)` | — | нет | draft/needs_review/approved/rejected/superseded |
| `input_snapshot` | `JSONB` | — | нет | Неизменяемый на уровне приложения снимок расчётных входов |
| `total_cost` | `NUMERIC(18,2)` | — | да | Итоговая стоимость, RUB/иная указанная валюта |
| `currency` | `CHAR(3)` | — | нет | Валюта всей сметы |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата создания версии |
| `reviewed_by` | `UUID` | FK | да | Сметчик, проверивший результат |
| `reviewed_at` | `TIMESTAMPTZ` | — | да | Время проверки |
| `review_comment` | `TEXT` | — | да | Комментарий проверяющего |

**Связи FK:** `(request_id)` → `repair_requests(request_id)`; `(based_on_run_id, request_id)` → `ai_runs(run_id, request_id)`; `(reviewed_by)` → `users(user_id)`.

### 15. `estimate_items` — Позиции работ

Позиции объёмов работ с количеством, выбранной расценкой, формулой и суммами.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `item_id` | `UUID` | PK | нет | ID позиции ведомости работ |
| `estimate_id` | `UUID` | FK | нет | Смета/версия, которой принадлежит позиция |
| `request_id` | `UUID` | FK | нет | ID заявки для составных FK |
| `defect_id` | `UUID` | FK | да | Связанный дефект заявки, необязателен для общих работ |
| `rate_id` | `UUID` | FK | да | Структурированная расценка, если выбрана |
| `work_name` | `TEXT` | — | нет | Название операции |
| `quantity` | `NUMERIC(16,6)` | — | да | Объём именно ремонтных работ (не размер дефекта) |
| `unit_code` | `VARCHAR(20)` | — | да | Единица работы |
| `unit_price` | `NUMERIC(18,4)` | — | да | Принятая цена единицы после приведения методикой |
| `coefficient` | `NUMERIC(14,6)` | — | нет | Основной множитель расчёта |
| `base_cost` | `NUMERIC(18,2)` | — | да | Расчётная стоимость позиции без дополнительных материалов |
| `additional_materials_cost` | `NUMERIC(18,2)` | — | да | Дополнительная стоимость материалов |
| `total_cost` | `NUMERIC(18,2)` | — | да | Итог позиции |
| `calculation_details` | `JSONB` | — | нет | Формулы/коэффициенты/пересчёт единиц и промежуточные величины |
| `validation_status` | `VARCHAR(30)` | — | нет | valid/blocked/needs_review |
| `source_snapshot` | `JSONB` | — | да | Снимок происхождения принятой цены |

**Связи FK:** `(estimate_id, request_id)` → `estimates(estimate_id, request_id)`; `(defect_id, request_id)` → `defects(defect_id, request_id)`; `(rate_id)` → `rates(rate_id)`.

**Важно:** `base_cost`, `additional_materials_cost`, `total_cost` хранятся как результаты детерминированного калькулятора. Для строки `valid` триггер проверяет `base_cost = round(quantity × unit_price × coefficient / rate_unit_multiplier, 2)` для каталожной цены и множитель 1 для ручной. Он также сверяет единицу, цену, валюту и канонический `source_snapshot`. Правила преобразования совместимых физических единиц остаются ответственностью backend и должны выполняться до записи строки.

### 16. `estimate_materials` — Материалы

Материалы конкретной позиции и способ учёта их стоимости без двойного прибавления.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `material_id` | `UUID` | PK | нет | ID строки материала |
| `item_id` | `UUID` | FK | нет | Позиция, к которой относится материал |
| `material_name` | `TEXT` | — | нет | Название материала |
| `quantity` | `NUMERIC(16,6)` | — | нет | Количество |
| `unit_code` | `VARCHAR(20)` | — | нет | Единица материала |
| `unit_price` | `NUMERIC(18,4)` | — | да | Принятая единичная цена |
| `total_cost` | `NUMERIC(18,2)` | — | да | Стоимость строки материала |
| `source_id` | `UUID` | FK | да | Справочник/прайс-источник |
| `price_snapshot` | `JSONB` | — | да | Снимок конкретной позиции источника |
| `cost_treatment` | `VARCHAR(30)` | — | нет | included_in_rate/additional/informational |

**Связи FK:** `(item_id)` → `estimate_items(item_id)`; `(source_id)` → `norm_sources(source_id)`.

### 17. `request_clarifications` — Уточнения

Вопросы AI к пользователю/сметчику, ответы, исправления и связь с запуском.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `clarification_id` | `UUID` | PK | нет | ID вопроса/ответа |
| `request_id` | `UUID` | FK | нет | Заявка |
| `run_id` | `UUID` | FK | да | Связанный AI-запуск той же заявки |
| `field_name` | `VARCHAR(100)` | — | нет | Код уточняемого параметра |
| `question` | `TEXT` | — | нет | Вопрос к человеку |
| `answer` | `TEXT` | — | да | Полученный ответ |
| `status` | `VARCHAR(30)` | — | нет | open/answered/cancelled/superseded |
| `answered_by` | `UUID` | FK | да | Пользователь, давший ответ |
| `supersedes_clarification_id` | `UUID` | FK | да | Предыдущий уточняющий ответ той же заявки |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата вопроса |
| `answered_at` | `TIMESTAMPTZ` | — | да | Дата ответа |

**Связи FK:** `(request_id)` → `repair_requests(request_id)`; `(run_id, request_id)` → `ai_runs(run_id, request_id)`; `(answered_by)` → `users(user_id)`; `(supersedes_clarification_id, request_id)` → `request_clarifications(clarification_id, request_id)`.

### 18. `audit_events` — Журнал событий

Журнал инициаторов и действий (человек, система, AI) для расследования изменений.

| Атрибут | PostgreSQL | Ключ | NULL | Назначение |
|---|---|---|:---:|---|
| `event_id` | `UUID` | PK | нет | ID события |
| `actor_type` | `VARCHAR(20)` | — | нет | user/system/ai |
| `user_id` | `UUID` | FK | да | Человек-инициатор для actor_type=user |
| `request_id` | `UUID` | FK | да | Контекстная заявка, если событие к ней относится |
| `entity_type` | `VARCHAR(50)` | — | нет | Тип изменённой сущности |
| `entity_id` | `UUID` | — | нет | ID изменённой сущности; полиморфная ссылка, не FK |
| `action` | `VARCHAR(50)` | — | нет | Название события |
| `changes` | `JSONB` | — | нет | JSON с изменениями (без секретов) |
| `created_at` | `TIMESTAMPTZ` | — | нет | Дата события |

**Связи FK:** `(user_id)` → `users(user_id)`; `(request_id)` → `repair_requests(request_id)`.

## Связи и кардинальности

**Crow’s Foot:** на родительской стороне каждой FK-связи ровно одна существующая запись; на дочерней стороне возможны 0..N записей. Если FK дочернего объекта допускает NULL, для конкретной строки связь с родителем необязательна (`0..1`). Составные FK используют одинаковые `request_id`/`source_id` для жёсткой проверки принадлежности.

| № | Дочерняя сущность / поля | Родительская сущность / уникальные поля | Ссылка обязательна? |
|---:|---|---|---|
| 1 | `repair_requests(building_id)` | `buildings(building_id)` | да |
| 2 | `repair_requests(created_by)` | `users(user_id)` | да |
| 3 | `request_photos(request_id)` | `repair_requests(request_id)` | да |
| 4 | `ai_runs(request_id)` | `repair_requests(request_id)` | да |
| 5 | `ai_results(run_id, request_id)` | `ai_runs(run_id, request_id)` | да |
| 6 | `defects(request_id)` | `repair_requests(request_id)` | да |
| 7 | `defects(defect_type_id)` | `defect_types(defect_type_id)` | нет (nullable) |
| 8 | `defects(source_ai_result_id, request_id)` | `ai_results(ai_result_id, request_id)` | нет (nullable) |
| 9 | `defects(confirmed_by)` | `users(user_id)` | нет (nullable) |
| 10 | `defect_photos(defect_id, request_id)` | `defects(defect_id, request_id)` | да |
| 11 | `defect_photos(photo_id, request_id)` | `request_photos(photo_id, request_id)` | да |
| 12 | `defect_measurements(defect_id, request_id)` | `defects(defect_id, request_id)` | да |
| 13 | `defect_measurements(source_ai_result_id, request_id)` | `ai_results(ai_result_id, request_id)` | нет (nullable) |
| 14 | `defect_measurements(recorded_by)` | `users(user_id)` | нет (nullable) |
| 15 | `defect_measurements(supersedes_measurement_id, defect_id)` | `defect_measurements(measurement_id, defect_id)` | нет (nullable) |
| 16 | `rates(source_id)` | `norm_sources(source_id)` | да |
| 17 | `normative_chunks(source_id)` | `norm_sources(source_id)` | да |
| 18 | `normative_chunks(rate_id, source_id)` | `rates(rate_id, source_id)` | нет (nullable) |
| 19 | `estimates(request_id)` | `repair_requests(request_id)` | да |
| 20 | `estimates(based_on_run_id, request_id)` | `ai_runs(run_id, request_id)` | нет (nullable) |
| 21 | `estimates(reviewed_by)` | `users(user_id)` | нет (nullable) |
| 22 | `estimate_items(estimate_id, request_id)` | `estimates(estimate_id, request_id)` | да |
| 23 | `estimate_items(defect_id, request_id)` | `defects(defect_id, request_id)` | нет (nullable) |
| 24 | `estimate_items(rate_id)` | `rates(rate_id)` | нет (nullable) |
| 25 | `estimate_materials(item_id)` | `estimate_items(item_id)` | да |
| 26 | `estimate_materials(source_id)` | `norm_sources(source_id)` | нет (nullable) |
| 27 | `request_clarifications(request_id)` | `repair_requests(request_id)` | да |
| 28 | `request_clarifications(run_id, request_id)` | `ai_runs(run_id, request_id)` | нет (nullable) |
| 29 | `request_clarifications(answered_by)` | `users(user_id)` | нет (nullable) |
| 30 | `request_clarifications(supersedes_clarification_id, request_id)` | `request_clarifications(clarification_id, request_id)` | нет (nullable) |
| 31 | `audit_events(user_id)` | `users(user_id)` | нет (nullable) |
| 32 | `audit_events(request_id)` | `repair_requests(request_id)` | нет (nullable) |
| 33 | `norm_sources(supersedes_source_id, source_series_id)` | `norm_sources(source_id, source_series_id)` | нет (nullable) |

**Конкретные кардинальности:** `users → repair_requests` 1:N; `buildings → repair_requests` 1:N; `repair_requests → request_photos/defects/ai_runs/estimates/request_clarifications` 1:N; `ai_runs → ai_results` 1:N; `norm_sources → rates/normative_chunks` 1:N; `estimates → estimate_items` 1:N; `estimate_items → estimate_materials` 1:N. `defects ↔ request_photos` — M:N через `defect_photos`. `defect_measurements`, `request_clarifications` и редакции `norm_sources` имеют контролируемые самоссылки.

**Важно по построению диаграммы:** 33 соединителя отображают 33 FK, а не 33 разных типа отношений. Для optional FK связь со стороны дочернего экземпляра может отсутствовать; маркеры Crow’s Foot показывают допустимую множественность ссылок.

## Ограничения и индексы

### Обеспечивается текущим SQL (логическая проверка DDL)

- UUID PK всех таблиц, составной PK `(defect_id, photo_id)` у `defect_photos`.
- Уникальный email без учёта регистра — индекс `uq_users_email_lower`.
- Ограниченные роли, типы источников, типы ML-модулей, статусы, `cost_treatment` и другие перечисления через `CHECK`.
- Неотрицательные `NUMERIC` для измерений, стоимостей и объёмов, положительный коэффициент и множитель тарифной единицы.
- `ON DELETE RESTRICT` для всех доменных FK — удаление связанных записей блокируется.
- Составные FK с `request_id` между photo/defect/measurement/AI run/estimate/estimate item/clarification; составной FK по `source_id` для фрагмента и расценки.
- `UNIQUE(request_id, version)` у версий сметы.
- Одна основная фотография дефекта максимум (`UNIQUE(defect_id) WHERE is_primary`).
- Одно текущее измерение параметра дефекта максимум (`UNIQUE(defect_id, parameter_code) WHERE is_current`).
- Одна рекомендуемая редакция нормативного источника/прайса максимум на `source_series_id`; предыдущая редакция обязана принадлежать той же серии.
- Активные нормативные и коммерческие расценки требуют проверенного источника; `DEMO` нельзя пометить подтверждённым или выдать за нормативную базу.
- `approved` требует `reviewed_by` и `reviewed_at`; триггер утверждения также требует хотя бы одну позицию, статус `valid` у всех позиций, совпадение `estimates.total_cost` с суммой позиций и равенство `additional_materials_cost` сумме только материалов `cost_treatment=additional`.
- Терминальные (`approved`, `rejected`, `superseded`) и неактуальные версии смет, их позиции и материалы защищены триггерами от изменения; удаление строк `estimates` запрещено.
- `valid` для каталожной позиции требует канонический snapshot с источником, серией, редакцией, кодом, единицей, нормативным множителем, ценой, валютой и базой цены; `fixrate_rate_snapshot(rate_id)` формирует этот JSON без вымышленных значений.
- Ручная работа без `rate_id` требует `origin=manual`, описание источника цены, автора ввода, основание, единицу, цену и валюту.
- Триггер проверяет все канонические поля snapshot на согласованность с каталогом и формулу `round(quantity × unit_price × coefficient / rate_unit_multiplier, 2)`; обязательные поля ручного происхождения проверяются без NULL-лазеек.
- Строка дополнительного материала требует цену и источник/снимок цены.
- У `normative_chunks` запрещено пустое содержимое; при наличии embedding обязательно название embedding-модели и наоборот.
- Индексы: заявки по зданию/автору и дате, AI-запуски, результаты, фото, дефекты, измерения, позиции сметы, материалы, уточнения, аудит, GIN-поиск тарифов и фрагментов.

### Примеры реальных ограничений

```sql
-- Уникальность версии сметы в пределах одной заявки
CONSTRAINT uq_estimates_request_version UNIQUE (request_id, version);

-- Дефект и позиция сметы ОБЯЗАНЫ относиться к одной заявке
CONSTRAINT fk_items_defect_same_request
  FOREIGN KEY (defect_id, request_id)
  REFERENCES defects(defect_id, request_id) ON DELETE RESTRICT;

-- Один дефект — максимум одно основное фото
CREATE UNIQUE INDEX uq_defect_single_primary_photo
  ON defect_photos(defect_id) WHERE is_primary;

-- Полнотекстовый поиск PostgreSQL, НЕ BM25
CREATE INDEX idx_chunks_search_vector
  ON normative_chunks USING GIN(search_vector);
```

### Не обеспечивается одними FK/CHECK

- Полное управление правами пользователей (RBAC), авторизация, проверка роли сметчика при утверждении.
- Обязательность «у заявки есть фото **или** непустое описание», потому что фото расположены в другой таблице.
- Валидация реального файла (MIME, содержимое, размер, безопасность, наличие в хранилище).
- Действительная экспертиза нормы/цены, её региона, даты и правомерности использования; поле `is_verified` не заменяет проверку.
- Векторная размерность/единство embedding-модели; настройка HNSW/IVFFlat, BM25, RRF и метрик RAG.
- Полная машина переходов статусов и создание следующей версии сметы в конкурентной транзакции. Неизменность терминальных/предыдущих версий и автообновление `repair_requests.updated_at` уже обеспечены триггерами.
- Правила преобразования совместимых физических единиц и нормативные индексы пересчёта: база проверяет уже приведённую единицу и арифметику, но не выбирает методику конвертации.
- Семантическая классификация материала как `included_in_rate` или `additional`, особенно при `all_inclusive` и `resource_based`. После классификации база не допускает включения `included_in_rate`/`informational` в `additional_materials_cost` при утверждении.
- Проверка того, что новый ответ/измерение действительно отменяет старый и не образует циклы.
- Проверка, что `source_ai_result_id` принадлежит именно CV, а не NLP/RAG; источники параметров, confidence и фиксация ручного подтверждения.
- Проверка, что `audit_events.entity_id` реально существует (полиморфная ссылка не FK).
- Неразглашение ключей, персональных данных и приватных фотографий в журналах и датасетах.

## 20 согласованных решений

Это решения, принятые в ходе последовательной проверки сценариев №1–20. Они не равнозначны уже выполненным интеграционным тестам.

| № | Тема | Принятое решение | Реализация/проверка |
|---|---|---|---|
| D01 | Учётные записи | Деактивация пользователей через `users.is_active=false`, а не каскадное удаление истории. | DDL + приложение |
| D02 | Отмена заявки | `repair_requests.status=cancelled`; история заявок, фото и смет не уничтожается. | DDL + приложение |
| D03 | Здания | Одна запись `buildings` связана с множеством заявок; FK обязателен. | FK |
| D04 | Гибкие свойства здания | Основные поля — типизированные; дополнительные — JSONB-объект `additional_properties`. | DDL + приложение |
| D05 | Много фотографий | Между `defects` и `request_photos` M:N через `defect_photos`; основное фото максимум одно. | PK + FK + UNIQUE |
| D06 | Повторный AI-анализ | Каждый запуск и результат модели сохраняются отдельно, включая версии и входы. | Таблицы + приложение |
| D07 | Исторические цены | Старые редакции `norm_sources` и `rates` не перезаписываются; снимки цен остаются в смете. | Схема + приложение |
| D08 | Версии смет | Каждая корректировка формирует новую версию с уникальным `(request_id, version)`. | UNIQUE + приложение |
| D09 | Материалы | Уже включённые в расценку материалы повторно не суммируются. | Поле + DB-триггер утверждения + приложение |
| D10 | Неоднозначный RAG | Кандидаты и их источники сохраняются в AI JSON; при неоднозначности — подтверждение человека. | Схема + приложение |
| D11 | Размер дефекта ≠ объём работ | Параметры дефекта в `defect_measurements`, объём работ в `estimate_items`. | Отдельные таблицы |
| D12 | Несколько работ на дефект | Один дефект может иметь несколько позиций работ в одной или разных версиях сметы. | FK |
| D13 | Целостность заявки | Составные FK запрещают ссылаться на чужие фото/дефекты/AI-запуски. | Составные FK |
| D14 | Разные жизненные циклы | Статус заявки отделён от статуса сметы и AI-запуска. | CHECK + приложение |
| D15 | Уточнения | Вопросы/ответы в отдельных строках, исправления связываются через `supersedes_*`. | Схема + приложение |
| D16 | Достоверность параметров | Источник, приблизительность и проверка у каждого измерения отдельно; confidence AI недостаточен. | DDL + приложение |
| D17 | Аудит | Версии хранят результаты, `audit_events` — кто и что менял. | Таблица + приложение |
| D18 | Индексы | Составной индекс `(building_id, created_at DESC)` под историю заявок здания. | CREATE INDEX |
| D19 | Удаление здания | `ON DELETE RESTRICT` для заявок, `buildings.is_active=false` для архивирования. | FK + приложение |
| D20 | Сквозная обработка | Одна заявка: много фото, дефектов, AI-запусков, уточнений, версий сметы и прослеживаемых цен. | Модель + интеграция |

**Дополнительные уточнения после 20 вопросов:** отдельные `defect_measurements` вместо одного quantity в defects; `normative_chunks`/pgvector; `rate_unit_multiplier` и provenance цены; `source_snapshot`/`input_snapshot`; `cost_treatment` вместо булевого included; composite-FK для запрета чужих заявок; `actor_type` в аудите; `is_active` у здания.

## Сквозные сценарии

### S1. Полная заявка → предварительная смета → проверка

**Дано:** здание и оператор; текстовая заявка, три фото одного повреждения; выбран пилотный вид работ; подтверждённые входные величины и разрешённые исходные прайсы.  
**Шаги:** `buildings/users` → `repair_requests` → `request_photos` → `ai_runs` → `ai_results` → `defects/defect_photos/defect_measurements` → `normative_chunks/rates` → валидация → `estimates/estimate_items/estimate_materials` → проверка сметчиком → `audit_events`.  
**Ожидаемый результат:** одна заявка, точные связи, объяснимая смета с источниками, возможность повторного чтения, исправления и экспорта.  
**Статус:** описан архитектурно; **end-to-end не запускался**.

### S2. Неизвестен размер: корректное уточнение

**Дано:** фото без масштаба, площадь не указана.  
**Шаги:** CV/NLP возвращают признаки, оркестратор переходит в needs_clarification; `request_clarifications` фиксирует вопрос; пользователь отвечает; `defect_measurements` сохраняет источник, единицу и приблизительность; запуск продолжается или стартует повторно.  
**Ожидаемый результат:** никаких придуманных площадей и сумм; до подтверждения входа смета не выдаётся как корректная.  
**Статус:** ожидаемое приложение.

### S3. Расценка не найдена / несколько расценок

**Дано:** RAG не находит норму или находит несколько сопоставимых кандидатов.  
**Шаги:** сохранить кандидатов/состояние поиска в `ai_results.result_data`; отобразить source_id/rate_id, редакцию, регион и единицы; запросить решение сметчика; не назначать вымышленную цену.  
**Ожидаемый результат:** `blocked/needs_review`, не утвердить фиктивную стоимость.  
**Статус:** ожидаемое приложение.

### S4. Корректировка объёма и сохранение истории

**Дано:** первый расчёт по 2.5 м², затем подтверждены 3 м².  
**Шаги:** первоначальное измерение перестаёт быть текущим, новое ссылается на предыдущее; создаётся `estimates.version+1` и новые `estimate_items`; обе версии сохраняют снимки источников и входных параметров.  
**Ожидаемый результат:** старые суммы доступны, новые рассчитываются из подтверждённых данных.  
**Статус:** ограничение уникальности есть; транзакционная логика в приложении.

### S5. Обновление прайса без изменения исторической сметы

**Дано:** в старой версии позиция использовала цену 1500 ₽/м², в новой редакции 1800 ₽/м².  
**Шаги:** добавить новый norm_sources/rates; не обновлять старые; в старом `estimate_items` остаются unit_price и source_snapshot.  
**Ожидаемый результат:** старая смета не меняется, новая может использовать новую цену.  
**Статус:** структура поддерживает, запрет UPDATE требует сервисного правила.

### S6. Защита от смешения заявок

**Дано:** есть заявка A и заявка B, у каждой свои фото, дефекты, AI-запуски и сметы.  
**Шаги:** попробовать привязать фото B к дефекту A; результат AI B к дефекту A; дефект B к позиции сметы A; AI run B к смете A.  
**Ожидаемый результат:** все операции отклоняются составными внешними ключами SQL.  
**Статус:** проверено наличие FK в DDL; фактические INSERT-тесты необходимы.

### S7. Двойной учёт материалов

**Дано:** выбранная ставка включает работу и материалы.  
**Шаги:** добавить справочный материал в `estimate_materials` с `cost_treatment=included_in_rate`; калькулятор учитывает сумму ставки и не прибавляет включённый материал ещё раз.  
**Ожидаемый результат:** единственное включение затрат, версия сметы показывает обоснование.  
**Статус:** калькулятор классифицирует материал; DB-триггер при утверждении сверяет `additional_materials_cost` только с суммой строк `cost_treatment=additional`.

### S8. Сравнение AI-моделей

**Дано:** одна фотография и одинаковые параметры заявки; два разных CV-подхода.  
**Шаги:** два `ai_runs`, разные `ai_results` с model_name/model_version и snapshot, независимый результат от человека, подсчёт метрик на размеченных данных.  
**Ожидаемый результат:** обе версии доступны для сравнения, качество не объявляется по confidence без ground truth.  
**Статус:** сохранение предусмотрено; оценочные эксперименты ещё не проводились.

**Полная матрица:** [test_scenarios.md](test_scenarios.md) — 97 детализированных тест-кейсов. Они включают все 20 обсуждённых архитектурных вопросов и негативные сценарии DDL/API/RAG/расчётов. 50 SQL-кейсов выполнены (50/50 PASS), 47 ожидают backend/API/ML.

## Пределы автоматической гарантии

1. **DDL применён, но не на промышленной конфигурации.** Цепочка `001 + 003` успешно выполнена на PostgreSQL 16.15 + pgvector 0.8.7, smoke, отдельный тест нормативных версий и 50 SQL-сценариев пройдены. Интеграция ORM с реальной схемой проверена; бизнес-/инфраструктурные сценарии и производительность ещё не проверены.
2. **Техническая прослеживаемость не заменяет экспертизу источника.** Snapshot и триггер гарантируют совпадение сохранённых фактов с выбранной строкой каталога, но `is_verified` выставляется уполномоченным процессом/человеком и не доказывает юридическую применимость документа.
3. **Часть правил приложения не реализована в SQL.** SQL защищает утверждение, неизменность версий и базовую арифметику строк, но полная машина статусов, создание новых версий без гонок, модерация приблизительных измерений, согласование валют и нормативный пересчёт требуют backend-кода.
4. **Права на источники и фотографии необходимо установить.** Наличие реквизитов источника недостаточно для подтверждения лицензии/точности.
5. **Векторная часть зависит от ML.** Выбрать модель, размерность, схему переиндексации и BM25. Без этого нельзя утверждать корректность RAG и ANN-поиска.
6. **Отложенное тестирование.** 50 SQL-строк матрицы уже имеют фактический результат и ссылку на harness. Для оставшихся 47 строк результат не засчитывается, пока QA не приложит фактический результат, конфигурацию и доказательство.

## План проверки и приёмки

| Очерёдность | Действие | Владелец | Подтверждение |
|---:|---|---|---|
| 1 | Установить PostgreSQL 16, pgvector; создать чистую тестовую БД и применить весь DDL | Архитектор БД | Лог запуска, перечень таблиц и ограничений |
| 2 | Выполнить позитивные и негативные INSERT/UPDATE/DELETE из тест-матрицы для всех составных FK | Архитектор БД + QA | Реальные результаты SQL/ошибки FK |
| 3 | Настроить ORM Яны строго по DDL; не создавать параллельные таблицы через `create_all` | Backend | Миграции, интеграционные тесты |
| 4 | Утвердить контракты CV/NLP/RAG, snapshot и статусы | Артём + ML | JSON Schema, образцы ответов и ошибок |
| 5 | Подготовить реальные нормативные источники и тестовые ставки, выбрать pgvector-модель и BM25 | Аналитик + ML | Реестр источников, индекс и проверка поиска |
| 6 | Пройти S1–S8 на работающем приложении, проверить суммы вручную | Backend + QA + сметчик | Протокол прогона и размер выборки |
| 7 | Заблокировать переписывание утверждённых смет, проверить аудит, лицензии и управление доступом | Backend + архитектор БД | Автотесты и правила доступа |
| 8 | Утвердить реалистичный пилот и ограничения для Демо-1 | Тимлид + команда | Зафиксированная версия MVP и инструкция запуска |

**Критерий готовности ER-модели к интеграции:** все последовательные миграции применены в тестовой базе без ошибок; 18 таблиц и 33 FK существуют; составные FK, индексы, snapshot и триггеры нормативного множителя реально работают; обнаруженные отклонения либо устранены, либо занесены в перечень известных ограничений.

---

*Документ синхронизирован с `db/001_init.sql` и `db/003_normative_source_versions.sql`. Миграции применены на тестовой PostgreSQL 16.15 + pgvector 0.8.7; smoke, тест нормативных версий, 50 SQL-сценариев и соответствие ORM пройдены. `erd.svg` и `erd.drawio` пока не содержат полей миграции 003 и не являются источниками истины.*
