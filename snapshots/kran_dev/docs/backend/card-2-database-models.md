# Карточка 2: SQLAlchemy-модели и подключение PostgreSQL (backend)

> **Для людей и нейросетей.** Документ описывает, что сделано в карточке 2 backend:
> engine/session SQLAlchemy 2.0, 18 ORM-моделей строго по DDL v3.1 и проверку
> соответствия живой схеме. Схема по-прежнему задаётся только файлами из `db/`.

| Поле | Значение |
|---|---|
| Проект | FixRate AI: AI-агент расчёта стоимости ремонта по фото и тексту |
| Карточка | Backend №2: подключение PostgreSQL, SQLAlchemy 2.0 sync + psycopg3, ORM-модели |
| Дедлайн | 21.10.2026 (Екатеринбург) |
| Статус | Код и проверки готовы; закрывать после самопроверки на своей машине |
| Стек | Python 3.12 (проверено на 3.14), SQLAlchemy 2.0 sync, psycopg3, pgvector, pytest |
| Источник схемы | `db/001_init.sql` + `db/003_normative_source_versions.sql`, без `create_all()` и без Alembic |

---

## 1. Что сделано

| Требование | Как выполнено | Где |
|---|---|---|
| Подключение PostgreSQL | Драйвер `postgresql+psycopg`, ленивый engine | `backend/app/db/session.py` |
| Сессии для FastAPI | Зависимость `get_db()`, закрытие в `finally` | `backend/app/db/session.py` |
| Транзакции в скриптах | `session_scope()`: commit / rollback / close | `backend/app/db/session.py` |
| ORM-модели по DDL | 18 таблиц, 188 колонок | `backend/app/models/` |
| PK/FK/UNIQUE/CHECK/индексы | Повторяют имена и состав DDL | `backend/app/models/` |
| Деньги и объёмы | `Decimal` + `NUMERIC`, ни одного `Float` | модели и тест `test_no_float_columns` |
| Отсутствие своей схемы | Нет `Base.metadata.create_all()`; DDL — единственный источник | `backend/app/db/`, `backend/app/models/` |
| Проверка на живой БД | Интеграционный тест сверяет метаданные с PostgreSQL | `backend/tests/test_models_db.py` |

Модели сгруппированы по смыслу:

```text
app/models/
├── core.py          # users, buildings, defect_types, norm_sources
├── requests.py      # repair_requests, request_photos, request_clarifications
├── ai.py            # ai_runs, ai_results
├── defects.py       # defects, defect_photos, defect_measurements
├── norms.py         # rates, normative_chunks
├── estimates.py     # estimates, estimate_items, estimate_materials
├── audit.py         # audit_events
└── __init__.py      # импорт всех 18 моделей + Base
```

---

## 2. Принятые решения

### 2.1. DDL — единственный источник схемы

`db/001_init.sql` — начальный снимок схемы v3.1; `db/003_normative_source_versions.sql` — последовательное расширение нормативного каталога. Backend не создаёт таблицы,
не выполняет `Base.metadata.create_all()` и не держит собственных миграций.
Любое следующее изменение структуры — новая SQL-миграция архитектора БД (`004_*.sql` и далее).

ORM-модели нужны для типизированного доступа, запросов и сериализации, а не для
управления схемой. Поэтому имена ограничений и индексов в моделях совпадают с DDL:
это позволяет интеграционному тесту сравнивать метаданные с реальной БД и сразу
видеть расхождения.

### 2.2. Ленивый engine и понятная ошибка конфигурации

`get_engine()` создаёт engine только при первом обращении. Импорт приложения и
unit-тесты не требуют PostgreSQL. Если `DATABASE_URL` пуст, выбрасывается
`RuntimeError` с инструкцией скопировать `.env.example` в `.env`; приложение не
подставляет фиктивный адрес и не пытается молча работать без БД.

Параметры engine: `pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`.
Сессии: `autoflush=False`, `expire_on_commit=False`; коммит и откат выполняет
сервисный слой, а `get_db()` только закрывает сессию.

### 2.3. Decimal, а не float

Все денежные и объёмные поля объявлены через `Numeric` с точностью из DDL:
`NUMERIC(18,4)`, `NUMERIC(18,2)`, `NUMERIC(16,6)`, `NUMERIC(14,6)` и т.д.
SQLAlchemy возвращает для них `Decimal`. В моделях нет `Float`; это проверяет
`tests/test_models.py`.

### 2.4. Составные внешние ключи и версионирование

Составные FK сохранены как в DDL, например:

- `ai_results (run_id, request_id) → ai_runs (run_id, request_id)`;
- `defects (source_ai_result_id, request_id) → ai_results`;
- `estimate_items (estimate_id, request_id) → estimates`;
- `estimate_items (defect_id, request_id) → defects`;
- `request_clarifications (supersedes_clarification_id, request_id) → request_clarifications`.

Это не даёт связать объект с чужим `request_id` на уровне БД. Все 33 FK имеют
`ON DELETE RESTRICT`, как в DDL.

### 2.5. `metadata` и генерируемый `search_vector`

В `normative_chunks` есть колонка `metadata`. В Python атрибут с именем
`metadata` занят `DeclarativeBase`, поэтому в модели он называется
`metadata_json`, а физическое имя колонки остаётся `"metadata"`.

Поле `search_vector` описано через `Computed("to_tsvector('russian', content)", persisted=True)`.
Это генерируемая колонка PostgreSQL; backend её не пишет.

### 2.6. Вектор без размерности

`normative_chunks.embedding` — `pgvector.sqlalchemy.Vector()` без фиксированной
размерности. HNSW/IVFFlat-индекс не добавлялся: сначала нужно выбрать
embedding-модель и единую размерность. Это отдельная миграция, а не часть карточки 2.

### 2.7. Связи ORM

В карточке 2 намеренно нет `relationship()`: таблицы связаны внешними ключами,
а репозитории будут делать явные `JOIN`. Это не маскирует составные FK и не
создаёт скрытых N+1-запросов. Если для API понадобятся удобные графы объектов,
их можно добавить в карточке 3 без изменения схемы.

### 2.8. Триггеры остаются в БД

Шесть триггеров DDL (`trg_requests_updated_at`, `trg_guard_estimate`,
`trg_check_estimate_approval`, `trg_guard_estimate_item`,
`trg_guard_estimate_material`, `trg_audit_append_only`) не дублируются в Python.
Они продолжают защищать историю смет, статус `approved` и неизменяемость аудита
на уровне PostgreSQL.

---

## 3. Проверка

### 3.1. Unit-тесты без БД

```bash
cd backend
pytest -q
```

Результат: **24 passed, 10 skipped**. Десять интеграционных тестов пропускаются,
потому что `DATABASE_URL` не задан.

Что проверяют unit-тесты:

- зарегистрированы ровно 18 таблиц;
- 188 колонок;
- ни одной `Float`-колонки;
- 14 денежных/объёмных полей имеют `Numeric(asdecimal=True)` и Python-тип `Decimal`;
- 33 FK, все с `ON DELETE RESTRICT`;
- 75 CHECK и 14 UNIQUE-ограничений;
- 17 UUID-первичных ключей с `gen_random_uuid()` и ключевые server defaults;
- `search_vector` — генерируемая колонка;
- engine без `DATABASE_URL` падает с понятной ошибкой.

### 3.2. Интеграционная проверка против PostgreSQL

Создана отдельная БД `fixrate_backend_test` на PostgreSQL 16 + pgvector 0.8.7,
в неё применены `db/001_init.sql` и `db/003_normative_source_versions.sql` (без DEMO-сида). Затем:

```bash
DATABASE_URL='postgresql+psycopg://fixrate:ChangeMe-local-only@localhost:5433/fixrate_backend_test' \
  pytest -q tests/test_models_db.py
```

Результат: **10 passed**. Полный прогон `pytest -q` с этой БД: **34 passed**.

Тест сверяет модель и живой `information_schema`/`pg_catalog`:

| Проверка | Результат |
|---|---|
| Набор таблиц | 18 из 18 |
| Колонки, типы, nullable | 188 из 188 |
| Первичные ключи | все совпадают |
| Внешние ключи, состав и `ON DELETE RESTRICT` | 33 из 33 |
| UNIQUE-ограничения | 14 из 14 |
| Индексы, включая partial и GIN | совпадают по именам и выражениям |
| CHECK-ограничения | 64 из 64 |
| `search_vector` | `GENERATED ALWAYS ... STORED` |
| Подключение через `app.db.session` | `SELECT 1` проходит |
| `session_scope()` и `get_db()` | выдают рабочую сессию и закрываются |

### 3.3. Чего в проверке нет

- 13 сценариев `SQL+APP` и 34 сценария `APP`/`APP+INFRA` из
  `docs/database/test_scenarios.md` требуют API, файлового хранилища или ML;
  они остаются на следующие карточки. 50 SQL-only сценариев уже пройдены (50/50 PASS).
- HNSW/IVFFlat-индекс не проверяется: он ещё не создан.
- Полный сквозной сценарий «заявка → фото → смета» появится в карточках 3–6.

---

## 4. Как запустить

Из корня репозитория:

```bash
docker compose up -d
# при занятом 5432: POSTGRES_PORT=5433 docker compose up -d

psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/002_seed_demo.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/003_normative_source_versions.sql
```

В `backend/.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://fixrate:ChangeMe-local-only@localhost:5432/fixrate
```

Если используется порт `5433`, замените его в строке. Пароль — локальная заглушка
из `docker-compose.yml`, не производственный секрет.

```bash
cd backend
pytest -q
uvicorn app.main:app --reload
```

---

## 5. Что дальше

1. Карточка 3: API заявок, JWT, роли `operator/estimator/admin`, репозитории
   поверх готовых моделей и `get_db()`.
2. Карточка 4: сквозной MVP на заглушках CV/NLP/RAG, запись результата в БД.
3. Карточка 5: загрузка фото, `storage_key`, связь с дефектами.
4. После выбора embedding-модели — отдельная миграция HNSW/IVFFlat.
5. После появления API/ML — прогон оставшихся 47 сценариев матрицы.

---

## 6. Правила для следующих карточек

1. Не вызывать `Base.metadata.create_all()` и не менять DDL «на глаз».
2. Новые поля/таблицы — только новой миграцией в `db/`.
3. Деньги и объёмы — только `Decimal`/`NUMERIC`.
4. Не хватает данных для расчёта — `needs_clarification`, а не выдуманное число.
5. Роуты с БД — обычные `def`, не `async def`.
6. Не логировать пароли, JWT, `.env` и тела файлов.
7. DEMO-расценки не выдавать за проверенные ФЕР/ТЕР.

---

## 7. Шаблон для комментария в YouGile

> Карточка 2 (backend): PostgreSQL + SQLAlchemy 2.0 sync + psycopg3 готова.
> - Engine/session: `backend/app/db/session.py`; `DATABASE_URL` берётся из `.env`.
> - 18 ORM-моделей в `backend/app/models/` по `db/001_init.sql` + `db/003_normative_source_versions.sql`:
>   188 колонок, 33 FK с `ON DELETE RESTRICT`, 75 CHECK, 14 UNIQUE, индексы.
> - `Base.metadata.create_all()` не используется; схема — только SQL-миграции.
> - Деньги/объёмы — `Decimal`/`NUMERIC`; DEMO не считается проверенным нормативом.
> - Unit: `pytest -q` → 24 passed, 10 skipped (без БД).
> - Интеграционно на PostgreSQL 16 + pgvector 0.8.7: 10 passed; полный прогон — 34 passed.
> - 50 SQL-only сценариев матрицы остаются 50/50 PASS; 47 требуют API/ML и идут дальше.
