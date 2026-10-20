# FixRate AI · Database schema

## Требования

- PostgreSQL **16**.
- Расширение **pgvector** установлено на сервере; пользователь миграции может выполнить `CREATE EXTENSION vector`.
- Новая **пустая** база данных с доступом на создание таблиц и функций.
- Исходная модель: ERD v3, 18 таблиц, 32 внешних ключа. Изменения из v3.1 не требуют немедленной корректировки имён таблиц или API-контрактов.

## Применение

Из корня репозитория поднять локальный PostgreSQL и применить схему:

> Если порт `5432` уже занят локальным PostgreSQL, задайте `POSTGRES_PORT=5433`
> (Windows PowerShell: `$env:POSTGRES_PORT=5433`) и используйте `-p 5433` в командах `psql`.

```bash
docker compose up -d

# Linux / macOS
export PGPASSWORD=ChangeMe-local-only
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/002_seed_demo.sql

# Windows (PowerShell)
$env:PGPASSWORD="ChangeMe-local-only"
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/002_seed_demo.sql
```

`001_init.sql` выполняется транзакционно (`BEGIN` / `COMMIT`). **Не повторять** на базе, где таблицы уже созданы. Для изменения работающей схемы создавайте отдельную миграцию; `001_init.sql` не является инструментом обновления продакшен-БД.

`002_seed_demo.sql` идемпотентен: его можно запускать повторно. Он добавляет три типа дефектов, один DEMO-источник с тремя расценками, демо-пользователей и демо-здание. Демо-цены не являются ФЕР/ТЕР и не должны попадать в подтверждённые нормативные источники.

## Проверка

После успешного применения на отдельной тестовой базе:

```bash
createdb -h localhost -p 5432 -U fixrate fixrate_test
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_test -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_test -f db/tests/001_smoke.sql
```

В smoke-тесте ожидается сообщение `PASS`, после чего `ROLLBACK` удалит только созданные самим тестом записи. Он проверяет 18 таблиц, 32 FK, timestamp заявки, ручные позиции, запреты на изменение утверждённой сметы и её состава, прямой INSERT утверждённой сметы, добавление позиции в финальную версию и контроль итоговой суммы при утверждении.

### SQL-сценарии матрицы (50)

50 SQL-сценариев из `docs/database/test_scenarios.md` вынесены в исполняемый harness. Каждый сценарий запускается в отдельной транзакции и завершается `ROLLBACK`, поэтому база не изменяется. Нужна чистая БД с применённым `001_init.sql`.

**Вариант 1 — PostgreSQL на хосте (psql в PATH):**

```bash
createdb -h localhost -p 5432 -U fixrate fixrate_scenarios
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_scenarios -f db/001_init.sql

PGHOST=localhost PGPORT=5432 PGUSER=fixrate PGDATABASE=fixrate_scenarios \
  python db/tests/run_sql_scenarios.py
```

**Вариант 2 — psql внутри Docker-контейнера:**

```bash
docker exec fixrate_pg_test createdb -U fixrate fixrate_scenarios
docker cp db/001_init.sql fixrate_pg_test:/tmp/001_init.sql
docker exec fixrate_pg_test psql -X -v ON_ERROR_STOP=1 -U fixrate \
  -d fixrate_scenarios -f /tmp/001_init.sql

FIXRATE_PG_CONTAINER=fixrate_pg_test python db/tests/run_sql_scenarios.py
```

В PowerShell переменные окружения задаются отдельно, например:

```powershell
$env:FIXRATE_PG_CONTAINER="fixrate_pg_test"
py -3.14 db/tests/run_sql_scenarios.py
```

Ожидаемый итог — `SUMMARY: 50/50 PASS`. Фактический протокол: [`tests/002_scenarios_result.md`](tests/002_scenarios_result.md). Определения сценариев: [`tests/scenario_defs.py`](tests/scenario_defs.py); runner: [`tests/run_sql_scenarios.py`](tests/run_sql_scenarios.py). Файл `tests/scenario_results.json` генерируется и исключён из git.

### Фактическая проверка

| Дата | Окружение | Результат |
|---|---|---|
| 20.10.2026 | PostgreSQL 16 + pgvector 0.8.7, чистый контейнер | `001_init.sql` применён без ошибок: 18 таблиц, 181 колонка, 32 FK, 64 CHECK, 6 триггеров; `001_smoke.sql` → `PASS: 18 tables, 32 FK, ...`; `002_seed_demo.sql` применён дважды без дубликатов; дополнительные SQL-проверки составных FK, частичных UNIQUE, русского `tsvector` и запрета UPDATE аудита → PASS |
| 20.10.2026 | PostgreSQL 16 + pgvector 0.8.7, БД `fixrate_scenarios` | 50 SQL-сценариев матрицы → `SUMMARY: 50/50 PASS`; каждый тест выполнен в отдельной транзакции с `ROLLBACK` |

Для просмотра модели:

```sql
SELECT count(*) FROM information_schema.tables
WHERE table_schema='public' AND table_type='BASE TABLE';

SELECT count(*) FROM pg_constraint
WHERE contype='f' AND connamespace='public'::regnamespace;
```

## Правила работы с версиями смет

- Новую версию создавайте отдельной строкой `estimates` с новым `version`.
- Последующие изменения допустимы лишь у **последней** версии со статусом `draft` или `needs_review`.
- `approved`, `rejected`, `superseded` и более ранние версии неизменяемы, включая строки `estimate_items` и `estimate_materials`.
- Удаление самой сметы запрещено при любом статусе; удаление позиций и материалов допустимо только у последней версии `draft`/`needs_review`.
- Старая утверждённая версия **остаётся `approved`**, даже если появилась следующая версия. Текущую версию выбирайте по нужной бизнес-логике (например, максимальная утверждённая версия).
- Для утверждения нужны заполненные `reviewed_by`/`reviewed_at`, хотя бы одна позиция, все позиции со статусом `valid` и точная сумма `total_cost` по позициям.
- Для ручных позиций без нормативного `rate_id` указывайте `source_snapshot` с `{"origin":"manual"}` и источник/основание цены. У любой позиции со статусом `valid` должно выполняться `total_cost = base_cost + COALESCE(additional_materials_cost,0)`.
- Создание номера версии внутри одной заявки должно сериализоваться на уровне сервиса, например блокировкой `repair_requests` через `SELECT ... FOR UPDATE`.

## Что проверяет приложение

Авторизацию и роли пользователей, корректность нормативной методики и коэффициентов, конвертацию единиц, детерминированный расчёт позиции `quantity × price × coefficient / rate_unit_multiplier`, исключение двойного учёта материалов, наличие обязательных вводных данных заявки, статусы и журнал бизнес-событий.

`tsvector` в PostgreSQL не равно BM25; векторный индекс HNSW/IVFFlat создаётся отдельной миграцией после выбора модели эмбеддингов и размерности `vector`.

## Дальнейший шаг

1. SQLAlchemy-модели backend — реализованы в карточке 2 строго по `001_init.sql`, без `create_all()`; см. [`../docs/backend/card-2-database-models.md`](../docs/backend/card-2-database-models.md).
2. Интеграционные проверки S1–S8; 13 сценариев `SQL+APP` и 34 сценария `APP`/`APP+INFRA` из `docs/database/test_scenarios.md` после появления backend/API/ML.
3. Отдельная миграция для HNSW/IVFFlat после выбора embedding-модели и размерности `vector`.
4. При изменении схемы добавляйте новую миграцию `003_*.sql`; `001_init.sql` остаётся снимком начальной схемы.

История изменений DDL: [`CHANGELOG.md`](CHANGELOG.md).
