# FixRate AI · Database schema

## Требования

- PostgreSQL **16**.
- Расширение **pgvector** установлено на сервере; пользователь миграции может выполнить `CREATE EXTENSION vector`.
- Новая **пустая** база данных с доступом на создание таблиц и функций.
- Актуальная модель после миграции `003`: 18 таблиц, 188 колонок и 33 внешних ключа.

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
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/003_normative_source_versions.sql

# Windows (PowerShell)
$env:PGPASSWORD="ChangeMe-local-only"
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/002_seed_demo.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/003_normative_source_versions.sql
```

`001_init.sql` выполняется транзакционно (`BEGIN` / `COMMIT`). **Не повторять** на базе, где таблицы уже созданы. Для изменения работающей схемы создавайте отдельную миграцию; `001_init.sql` не является инструментом обновления продакшен-БД.

`002_seed_demo.sql` идемпотентен: его можно запускать повторно. Он добавляет три типа дефектов, один DEMO-источник с тремя расценками, демо-пользователей и демо-здание. Демо-цены не являются ФЕР/ТЕР и не должны попадать в подтверждённые нормативные источники.

`003_normative_source_versions.sql` — последовательная миграция для уже созданной базы. Она не меняет `001_init.sql`: добавляет серии/редакции источников, периоды и поставщика, канонический снимок расценки, проверку базового измерителя и индексы каталога. Усиленные `CHECK`, которым могли не соответствовать старые строки, созданы как `NOT VALID`, чтобы не блокировать upgrade; PostgreSQL применяет их ко всем новым и изменяемым данным. После аудита/исправления legacy-строк их можно отдельно перевести в `VALIDATE CONSTRAINT`.

## Проверка

После успешного применения на отдельной тестовой базе:

```bash
createdb -h localhost -p 5432 -U fixrate fixrate_test
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_test -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_test -f db/003_normative_source_versions.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_test -f db/tests/001_smoke.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_test -f db/tests/003_normative_versions.sql
```

В smoke-тесте ожидается сообщение `PASS`, после чего `ROLLBACK` удалит только созданные самим тестом записи. Он проверяет 18 таблиц, 33 FK, timestamp заявки, ручные позиции, запреты на изменение утверждённой сметы и её состава, прямой INSERT утверждённой сметы, добавление позиции в финальную версию и контроль итоговой суммы при утверждении. `003_normative_versions.sql` отдельно проверяет две нормативные редакции, две версии коммерческого прайса, поиск, множитель нормативной единицы, канонический snapshot, неизменность исторической цены и негативные ограничения.

### SQL-сценарии матрицы (50)

50 SQL-сценариев из `docs/database/test_scenarios.md` вынесены в исполняемый harness. Каждый сценарий запускается в отдельной транзакции и завершается `ROLLBACK`, поэтому база не изменяется. Нужна чистая БД с применёнными `001_init.sql` и `003_normative_source_versions.sql`.

**Вариант 1 — PostgreSQL на хосте (psql в PATH):**

```bash
createdb -h localhost -p 5432 -U fixrate fixrate_scenarios
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_scenarios -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate_scenarios -f db/003_normative_source_versions.sql

PGHOST=localhost PGPORT=5432 PGUSER=fixrate PGDATABASE=fixrate_scenarios \
  python db/tests/run_sql_scenarios.py
```

**Вариант 2 — psql внутри Docker-контейнера:**

```bash
docker exec fixrate_pg_test createdb -U fixrate fixrate_scenarios
docker cp db/001_init.sql fixrate_pg_test:/tmp/001_init.sql
docker cp db/003_normative_source_versions.sql fixrate_pg_test:/tmp/003_normative_source_versions.sql
docker exec fixrate_pg_test psql -X -v ON_ERROR_STOP=1 -U fixrate \
  -d fixrate_scenarios -f /tmp/001_init.sql
docker exec fixrate_pg_test psql -X -v ON_ERROR_STOP=1 -U fixrate \
  -d fixrate_scenarios -f /tmp/003_normative_source_versions.sql

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
| 22.10.2026 | PostgreSQL 16.15 + pgvector 0.8.7, новый изолированный контейнер | Повторно подтверждены: чистое применение `001_init.sql`, smoke-тест, двукратный идемпотентный seed, 50/50 SQL-сценариев и полный backend-прогон против живой схемы (`34 passed`) |
| 22.10.2026 | PostgreSQL 16.15 + pgvector 0.8.7, отдельная чистая БД для миграции 003 | Цепочка `001 → 002 → 003`, повторный seed, smoke, новый тест редакций/исторической цены и прежние 50/50 SQL-сценариев → PASS; DDL↔ORM и полный backend-прогон → `34 passed` |

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
- Для утверждения нужны заполненные `reviewed_by`/`reviewed_at`, хотя бы одна позиция, все позиции со статусом `valid`, точная сумма `total_cost` по позициям и совпадение `additional_materials_cost` с суммой только строк материалов `cost_treatment=additional`.
- Для ручных позиций без нормативного `rate_id` указывайте `source_snapshot` с `{"origin":"manual"}` и источник/основание цены. У любой позиции со статусом `valid` должно выполняться `total_cost = base_cost + COALESCE(additional_materials_cost,0)`.
- Для ручной цены snapshot дополнительно содержит `source_description`, `entered_by`, `basis`, `unit_code`, `unit_price`, `currency`.
- Для каталожной цены используйте `fixrate_rate_snapshot(rate_id)`. Триггер проверяет все канонические поля источника/расценки, единицу, цену и валюту, а также формулу `round(quantity × unit_price × coefficient / rate_unit_multiplier, 2)`.
- Создание номера версии внутри одной заявки должно сериализоваться на уровне сервиса, например блокировкой `repair_requests` через `SELECT ... FOR UPDATE`.

## Версии нормативов и прайсов

- Каждая редакция — отдельная строка `norm_sources` и отдельный набор `rates`; цены старой редакции не перезаписываются.
- `source_series_id` объединяет редакции одного документа/прайса, `supersedes_source_id` задаёт последовательность.
- В серии может быть только одна явно рекомендуемая строка `is_current=true`. Периоды `effective_date`/`valid_to` всё равно проверяются на дату расчёта; при неоднозначном результате выбор должен сделать backend/сметчик.
- Для коммерческого источника сохраняются `provider_name` и `default_currency`; подтверждённый источник требует версию и реквизиты.
- `FER`, `FERR`, `TER`, `TERR`, `COMMERCIAL` и `DEMO` различаются явно. `DEMO` нельзя пометить подтверждённым.
- Готовые запросы поиска, сравнения редакций, диагностики неполного происхождения и восстановления исторической строки: [`queries/normative_catalog.sql`](queries/normative_catalog.sql).

## Что проверяет приложение

Авторизацию и роли пользователей, применимость нормативной методики, преобразование совместимых единиц, выбор редакции на дату расчёта, правильность бизнес-классификации материалов, наличие обязательных вводных данных заявки, статусы и журнал бизнес-событий. База проверяет арифметику уже приведённой единицы и при утверждении принимает в `additional_materials_cost` только строки `cost_treatment=additional`, но не угадывает смысл материала или правила преобразования физических размерностей.

`tsvector` в PostgreSQL не равно BM25; векторный индекс HNSW/IVFFlat создаётся отдельной миграцией после выбора модели эмбеддингов и размерности `vector`.

## Дальнейший шаг

1. SQLAlchemy-модели backend синхронизированы с цепочкой `001 + 003`, без `create_all()`; см. [`../docs/backend/card-2-database-models.md`](../docs/backend/card-2-database-models.md).
2. Интеграционные проверки S1–S8; 13 сценариев `SQL+APP` и 34 сценария `APP`/`APP+INFRA` из `docs/database/test_scenarios.md` после появления backend/API/ML.
3. Отдельная миграция для HNSW/IVFFlat после выбора embedding-модели и размерности `vector`.
4. При следующем изменении схемы добавляйте новую миграцию `004_*.sql`; `001_init.sql` остаётся снимком начальной схемы.

История изменений DDL: [`CHANGELOG.md`](CHANGELOG.md).
