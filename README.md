# FixRate_AI

## Архитектура базы данных

В проекте FixRate AI используется PostgreSQL с расширением
pgvector для хранения реляционных данных и векторного поиска.

База данных включает 18 таблиц, охватывающих заявки,
дефекты, AI-анализ, нормативные справочники и сметы.

### ER-диаграмма (Crow’s Foot)

Ядро схемы — 8 ключевых таблиц, только ключи и связи. Диаграмма описана
в формате Mermaid, поэтому рендерится в README как вектор и не превращается
в нечитаемую картинку:

```mermaid
erDiagram
    users {
        UUID user_id PK
    }
    buildings {
        UUID building_id PK
    }
    repair_requests {
        UUID request_id PK
        UUID building_id FK
        UUID created_by FK
    }
    defects {
        UUID defect_id PK
        UUID request_id FK
        UUID defect_type_id FK
        UUID source_ai_result_id FK
        UUID confirmed_by FK
    }
    ai_runs {
        UUID run_id PK
        UUID request_id FK
    }
    ai_results {
        UUID ai_result_id PK
        UUID run_id FK
        UUID request_id FK
    }
    estimates {
        UUID estimate_id PK
        UUID request_id FK
        UUID based_on_run_id FK
        UUID reviewed_by FK
    }
    estimate_items {
        UUID item_id PK
        UUID estimate_id FK
        UUID request_id FK
        UUID defect_id FK
        UUID rate_id FK
    }
    buildings ||--o{ repair_requests : "building_id"
    users ||--o{ repair_requests : "created_by"
    repair_requests ||--o{ ai_runs : "request_id"
    ai_runs ||--o{ ai_results : "run_id, request_id"
    repair_requests ||--o{ defects : "request_id"
    ai_results |o--o{ defects : "source_ai_result_id, request_id"
    users |o--o{ defects : "confirmed_by"
    repair_requests ||--o{ estimates : "request_id"
    ai_runs |o--o{ estimates : "based_on_run_id, request_id"
    users |o--o{ estimates : "reviewed_by"
    estimates ||--o{ estimate_items : "estimate_id, request_id"
    defects |o--o{ estimate_items : "defect_id, request_id"
```

- `||` со стороны родителя — ровно одна родительская запись (FK обязателен);
- `|o` со стороны родителя — родитель необязателен (nullable FK);
- `o{` со стороны потомка — 0..N дочерних записей. Подписи на связях — поля FK дочерней таблицы,
`PK, FK` — составной ключ со ссылкой на родителя.

Остальные 10 таблиц и все атрибуты — в доменных диаграммах:
[docs/database/erd.md](docs/database/erd.md). Полная схема одним холстом —
[erd.svg](docs/database/erd.svg).

**Документация:**

- [ER-диаграмма: доменные схемы](docs/database/erd.md)
- [Открыть ER-диаграмму в SVG](docs/database/erd.svg)
- [Редактировать диаграмму в draw.io](docs/database/erd.drawio)
- [Спецификация базы данных](docs/database/specification.md)
- [Сценарии тестирования](docs/database/test_scenarios.md)
