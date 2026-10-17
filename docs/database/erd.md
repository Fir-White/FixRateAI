# FixRate AI — ER-диаграмма (Mermaid)

Схема описана текстом в формате [Mermaid](https://gitverse.ru/docs/collaborative/repositories/reference/markup-guide/),
поэтому рендерится прямо в README, на странице GitVerse и в предпросмотре VS Code,
остаётся векторной при любом масштабе и читается в diff’ах.

Состав: 18 таблиц, 32 внешних ключа. Назначение полей — в [specification.md](specification.md),
сценарии проверки — в [test_scenarios.md](test_scenarios.md).

## Как читать

- `||` со стороны родителя — ровно одна родительская запись (FK обязателен);
- `|o` со стороны родителя — родитель необязателен (nullable FK);
- `o{` со стороны потомка — 0..N дочерних записей.

Надпись на связи — поля FK в дочерней таблице. `PK, FK` — составной первичный ключ,
который одновременно ссылается на родителя (жёсткая проверка принадлежности заявке).
У составных FK проверяется вся пара полей, поэтому составных связей меньше, чем полей.

Полная схема одним холстом (все 18 таблиц со всеми атрибутами) — в [erd.svg](erd.svg).

## Домен «Заявки и дефекты»

Объект, автор и заявка, фотографии, дефекты с измерениями, уточнения и журнал событий.

### Объекты, пользователи и заявки

Таблицы: `users`, `buildings`, `repair_requests`, `request_photos`.

```mermaid
erDiagram
    users {
        UUID user_id PK
        VARCHAR full_name
        VARCHAR email
        TEXT password_hash
        VARCHAR role
        BOOLEAN is_active
        TIMESTAMPTZ created_at
    }
    buildings {
        UUID building_id PK
        TEXT address
        VARCHAR building_type
        SMALLINT construction_year
        SMALLINT floors_count
        NUMERIC total_area
        VARCHAR wall_material
        JSONB additional_properties
        BOOLEAN is_active
        TIMESTAMPTZ created_at
    }
    repair_requests {
        UUID request_id PK
        UUID building_id FK
        UUID created_by FK
        VARCHAR title
        TEXT description
        TEXT location_description
        VARCHAR status
        TEXT cancellation_reason
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    request_photos {
        UUID photo_id PK
        UUID request_id FK
        TEXT storage_key
        TEXT original_filename
        VARCHAR mime_type
        BIGINT file_size
        CHAR checksum_sha256
        TIMESTAMPTZ uploaded_at
    }
    buildings ||--o{ repair_requests : "building_id"
    users ||--o{ repair_requests : "created_by"
    repair_requests ||--o{ request_photos : "request_id"
```

### Дефекты, их фото и измерения

Таблицы: `defect_types`, `defects`, `defect_photos`, `defect_measurements`.

Связанные таблицы вне блока: `users`, `ai_results`, `repair_requests`, `request_photos` — показаны только первичные ключи.

```mermaid
erDiagram
    defect_types {
        UUID defect_type_id PK
        VARCHAR code
        VARCHAR name
        TEXT description
        BOOLEAN is_active
    }
    defects {
        UUID defect_id PK
        UUID request_id FK
        UUID defect_type_id FK
        UUID source_ai_result_id FK
        TEXT description
        TEXT location_description
        VARCHAR confirmation_status
        UUID confirmed_by FK
        TIMESTAMPTZ confirmed_at
        TIMESTAMPTZ created_at
    }
    defect_photos {
        UUID defect_id PK, FK
        UUID photo_id PK, FK
        UUID request_id FK
        BOOLEAN is_primary
        TIMESTAMPTZ created_at
    }
    defect_measurements {
        UUID measurement_id PK
        UUID defect_id FK
        UUID request_id FK
        VARCHAR parameter_code
        NUMERIC value
        VARCHAR unit_code
        VARCHAR source_type
        UUID source_ai_result_id FK
        UUID recorded_by FK
        BOOLEAN is_approximate
        VARCHAR verification_status
        UUID supersedes_measurement_id FK
        BOOLEAN is_current
        TIMESTAMPTZ created_at
    }
    users {
        UUID user_id PK
    }
    ai_results {
        UUID ai_result_id PK
    }
    repair_requests {
        UUID request_id PK
    }
    request_photos {
        UUID photo_id PK
    }
    users ||--o{ repair_requests : "created_by"
    repair_requests ||--o{ request_photos : "request_id"
    repair_requests ||--o{ defects : "request_id"
    defect_types |o--o{ defects : "defect_type_id"
    ai_results |o--o{ defects : "source_ai_result_id, request_id"
    users |o--o{ defects : "confirmed_by"
    defects ||--o{ defect_photos : "defect_id, request_id"
    request_photos ||--o{ defect_photos : "photo_id, request_id"
    defects ||--o{ defect_measurements : "defect_id, request_id"
    ai_results |o--o{ defect_measurements : "source_ai_result_id, request_id"
    users |o--o{ defect_measurements : "recorded_by"
    defect_measurements |o--o{ defect_measurements : "supersedes_measurement_id, defect_id"
```

### Уточнения и журнал событий

Таблицы: `request_clarifications`, `audit_events`.

Связанные таблицы вне блока: `users`, `repair_requests`, `ai_runs` — показаны только первичные ключи.

```mermaid
erDiagram
    request_clarifications {
        UUID clarification_id PK
        UUID request_id FK
        UUID run_id FK
        VARCHAR field_name
        TEXT question
        TEXT answer
        VARCHAR status
        UUID answered_by FK
        UUID supersedes_clarification_id FK
        TIMESTAMPTZ created_at
        TIMESTAMPTZ answered_at
    }
    audit_events {
        UUID event_id PK
        VARCHAR actor_type
        UUID user_id FK
        UUID request_id FK
        VARCHAR entity_type
        UUID entity_id
        VARCHAR action
        JSONB changes
        TIMESTAMPTZ created_at
    }
    users {
        UUID user_id PK
    }
    repair_requests {
        UUID request_id PK
    }
    ai_runs {
        UUID run_id PK
    }
    users ||--o{ repair_requests : "created_by"
    repair_requests ||--o{ ai_runs : "request_id"
    repair_requests ||--o{ request_clarifications : "request_id"
    ai_runs |o--o{ request_clarifications : "run_id, request_id"
    users |o--o{ request_clarifications : "answered_by"
    request_clarifications |o--o{ request_clarifications : "supersedes_clarification_id, request_id"
    users |o--o{ audit_events : "user_id"
    repair_requests |o--o{ audit_events : "request_id"
```

## Домен «AI и нормативы»

Запуски CV/NLP/RAG и результаты по модулям, источники нормативов и прайсов, расценки и RAG-фрагменты.

### Модули AI и нормативная база

Таблицы: `ai_runs`, `ai_results`, `norm_sources`, `rates`, `normative_chunks`.

Связанные таблицы вне блока: `repair_requests`, `defects` — показаны только первичные ключи.

```mermaid
erDiagram
    ai_runs {
        UUID run_id PK
        UUID request_id FK
        VARCHAR status
        VARCHAR pipeline_version
        JSONB input_snapshot
        TEXT error_message
        TIMESTAMPTZ started_at
        TIMESTAMPTZ completed_at
    }
    ai_results {
        UUID ai_result_id PK
        UUID run_id FK
        UUID request_id FK
        VARCHAR module_type
        VARCHAR model_name
        VARCHAR model_version
        JSONB input_reference
        JSONB result_data
        VARCHAR status
        INTEGER processing_time_ms
        TIMESTAMPTZ created_at
    }
    norm_sources {
        UUID source_id PK
        VARCHAR source_type
        TEXT title
        VARCHAR edition
        VARCHAR region
        DATE publication_date
        DATE effective_date
        TEXT source_url
        TEXT document_reference
        BOOLEAN is_verified
        TIMESTAMPTZ created_at
    }
    rates {
        UUID rate_id PK
        UUID source_id FK
        VARCHAR rate_code
        TEXT work_name
        TEXT description
        VARCHAR unit_code
        NUMERIC rate_unit_multiplier
        NUMERIC base_price
        CHAR currency
        VARCHAR price_basis
        VARCHAR cost_scope
        BOOLEAN is_active
    }
    normative_chunks {
        UUID chunk_id PK
        UUID source_id FK
        UUID rate_id FK
        INTEGER chunk_index
        TEXT content
        VECTOR embedding
        VARCHAR embedding_model
        TSVECTOR search_vector
        JSONB source_locator
        JSONB metadata
        CHAR content_hash
        TIMESTAMPTZ created_at
    }
    repair_requests {
        UUID request_id PK
    }
    defects {
        UUID defect_id PK
    }
    repair_requests ||--o{ ai_runs : "request_id"
    ai_runs ||--o{ ai_results : "run_id, request_id"
    repair_requests ||--o{ defects : "request_id"
    ai_results |o--o{ defects : "source_ai_result_id, request_id"
    norm_sources ||--o{ rates : "source_id"
    norm_sources ||--o{ normative_chunks : "source_id"
    rates |o--o{ normative_chunks : "rate_id, source_id"
```

## Домен «Сметы и цены»

Версионные сметы, позиции работ и материалы; ссылки на дефекты, расценки и результаты AI.

### Смета, позиции и материалы

Таблицы: `estimates`, `estimate_items`, `estimate_materials`.

Связанные таблицы вне блока: `users`, `repair_requests`, `defects`, `ai_runs`, `rates`, `norm_sources` — показаны только первичные ключи.

```mermaid
erDiagram
    estimates {
        UUID estimate_id PK
        UUID request_id FK
        INTEGER version
        UUID based_on_run_id FK
        VARCHAR status
        JSONB input_snapshot
        NUMERIC total_cost
        CHAR currency
        TIMESTAMPTZ created_at
        UUID reviewed_by FK
        TIMESTAMPTZ reviewed_at
        TEXT review_comment
    }
    estimate_items {
        UUID item_id PK
        UUID estimate_id FK
        UUID request_id FK
        UUID defect_id FK
        UUID rate_id FK
        TEXT work_name
        NUMERIC quantity
        VARCHAR unit_code
        NUMERIC unit_price
        NUMERIC coefficient
        NUMERIC base_cost
        NUMERIC additional_materials_cost
        NUMERIC total_cost
        JSONB calculation_details
        VARCHAR validation_status
        JSONB source_snapshot
    }
    estimate_materials {
        UUID material_id PK
        UUID item_id FK
        TEXT material_name
        NUMERIC quantity
        VARCHAR unit_code
        NUMERIC unit_price
        NUMERIC total_cost
        UUID source_id FK
        JSONB price_snapshot
        VARCHAR cost_treatment
    }
    users {
        UUID user_id PK
    }
    repair_requests {
        UUID request_id PK
    }
    defects {
        UUID defect_id PK
    }
    ai_runs {
        UUID run_id PK
    }
    rates {
        UUID rate_id PK
    }
    norm_sources {
        UUID source_id PK
    }
    users ||--o{ repair_requests : "created_by"
    repair_requests ||--o{ ai_runs : "request_id"
    repair_requests ||--o{ defects : "request_id"
    users |o--o{ defects : "confirmed_by"
    norm_sources ||--o{ rates : "source_id"
    repair_requests ||--o{ estimates : "request_id"
    ai_runs |o--o{ estimates : "based_on_run_id, request_id"
    users |o--o{ estimates : "reviewed_by"
    estimates ||--o{ estimate_items : "estimate_id, request_id"
    defects |o--o{ estimate_items : "defect_id, request_id"
    rates |o--o{ estimate_items : "rate_id"
    estimate_items ||--o{ estimate_materials : "item_id"
    norm_sources |o--o{ estimate_materials : "source_id"
```

## Исходные файлы

- [erd.svg](erd.svg) — прежняя версия из draw.io (один холст 3010×1870 со всеми атрибутами);
- [erd.drawio](erd.drawio) — исходник для редактирования в draw.io;
- [specification.md](specification.md) — описание сущностей, ограничений и индексов;
- [test_scenarios.md](test_scenarios.md) — сценарии проверки модели.
