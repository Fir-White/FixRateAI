# FixRate AI — backend

FastAPI-сервер для приёма заявок на ремонт и формирования **черновика** сметы (ВОР).
Сейчас реализованы каркас (карточка 1), слой БД (карточка 2) и API заявок:
SQLAlchemy 2.0 + psycopg3, engine/session, 18 ORM-моделей по DDL, а также
создание, список, получение и редактирование заявок. Фото-файлы и JWT остаются
в следующих карточках; API заявок уже возвращает сохранённые метаданные фото.

Подробное описание решений: [`../docs/backend/card-1-fastapi-skeleton.md`](../docs/backend/card-1-fastapi-skeleton.md)
и [`../docs/backend/card-2-database-models.md`](../docs/backend/card-2-database-models.md).
Контракт и инструкция API заявок: [`../docs/backend/card-4-request-api.md`](../docs/backend/card-4-request-api.md).

## Требования
- Python **3.12**
- (опционально) Docker — только для локального PostgreSQL

## Установка и запуск
Из каталога `backend/`:

**Linux / macOS**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

**Windows (PowerShell)**
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Сервер: http://127.0.0.1:8000

| Что | URL |
|---|---|
| Проверка живости | http://127.0.0.1:8000/health → `{"status":"ok"}` |
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |

## API заявок

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/v1/requests` | создать заявку |
| `GET` | `/api/v1/requests` | список с `limit`, `offset`, `status`, `building_id` |
| `GET` | `/api/v1/requests/{request_id}` | получить заявку, фото и текущие размеры |
| `PATCH` | `/api/v1/requests/{request_id}` | изменить текстовые поля, отменить или добавить размеры |
| `POST` | `/api/v1/requests/{request_id}/estimate` | запустить MVP AI-пайплайн и сохранить черновик ВОР |
| `GET` | `/api/v1/requests/{request_id}/estimate` | получить последнюю сохранённую версию сметы |

Пример создания:

```powershell
$body = @{
  building_id = "d4000000-0000-4000-8000-000000000001"
  title = "Трещина на фасаде у входа"
  description = "Вертикальная трещина, длина около 3 м"
  location_description = "подъезд 2, наружная стена"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/requests `
  -ContentType "application/json" -Body $body
```

После создания заявки запустите сквозной MVP с mock CV/LLM/RAG:

```powershell
$requestId = "<request_id из ответа POST>"
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/requests/$requestId/estimate"
```

Ответ содержит `estimate.total_cost`, позиции ВОР, формулы, источники и
`run.status`. Для демонстрационной заявки с текстом о трещине длиной 3 м
ожидается площадь `0.3000 m2` и итог `255.00 RUB` по источнику `DEMO`.
Демонстрационные расценки не являются ФЕР/ТЕР. Если масштаба недостаточно,
ответ имеет `needs_clarification`, а смета не создаётся.

ML Service должен быть запущен отдельно:

```powershell
cd ml_service
..\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Backend использует `ML_BASE_URL=http://127.0.0.1:8001`. Каждый запуск
сохраняется в `ai_runs` и `ai_results`, а сформированная версия — в
`estimates` и `estimate_items`.

В заявке можно передать уже сохранённую ссылку на фото вместо описания:

```json
{
  "building_id": "d4000000-0000-4000-8000-000000000001",
  "title": "Повреждение фасада",
  "photos": [{
    "storage_key": "requests/demo/photo-1.jpg",
    "original_filename": "photo-1.jpg",
    "mime_type": "image/jpeg",
    "file_size": 123456,
    "checksum_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }]
}
```

Обновление размера:

```powershell
$body = @{
  measurements = @(@{
    parameter_code = "length_m"
    value = 3.0
    unit_code = "m"
    is_approximate = $true
  })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Patch `
  -Uri "http://127.0.0.1:8000/api/v1/requests/<request_id>" `
  -ContentType "application/json" -Body $body
```

## Проверка
```bash
pytest -q          # без DATABASE_URL: unit/API-тесты проходят, DB-тесты skipped
curl -i http://127.0.0.1:8000/health          # 200 + заголовок X-Request-ID
curl -i http://127.0.0.1:8000/no-such-path    # 404 + единый JSON ошибки
```

Если в `backend/.env` уже указан `DATABASE_URL`, а PostgreSQL ещё не запущен,
перед проверкой без БД в PowerShell очистите переменную текущего процесса:

```powershell
$env:DATABASE_URL=""
python -m pytest -q
```

Если `8000` занят другим процессом, запускайте сервер на `8002` и открывайте
`http://127.0.0.1:8002/docs`:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Интеграционные проверки моделей против живой схемы включаются переменной
`DATABASE_URL` (нужен применённый `db/001_init.sql`):

```bash
# Linux / macOS
DATABASE_URL='postgresql+psycopg://fixrate:ChangeMe-local-only@localhost:5432/fixrate' \
  pytest -q tests/test_models_db.py

# Windows PowerShell
$env:DATABASE_URL="postgresql+psycopg://fixrate:ChangeMe-local-only@localhost:5432/fixrate"
python -m pytest -q tests/test_models_db.py
# с применённым DDL и DATABASE_URL полный прогон: 34 passed
```

Для Docker PostgreSQL на `5433` используйте:

```powershell
$env:DATABASE_URL="postgresql+psycopg://fixrate:ChangeMe-local-only@127.0.0.1:5433/fixrate"
python -m pytest -q tests/test_models_db.py
```

## PostgreSQL (локально)
Схема приходит из `db/001_init.sql`; backend **не** создаёт таблицы через `Base.metadata.create_all()`.
Из корня репозитория поднимите PostgreSQL и примените DDL + DEMO-данные:

```bash
docker compose up -d
# если порт 5432 занят локальным PostgreSQL:
# POSTGRES_PORT=5433 docker compose up -d

psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/001_init.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/002_seed_demo.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U fixrate -d fixrate -f db/003_photo_processed_storage.sql
```

Подробности, проверка и smoke-тест — в [`../db/README.md`](../db/README.md). В `backend/.env` укажите `DATABASE_URL` с тем же портом. Модели и engine уже реализованы в `app/models/` и `app/db/`; они только читают/пишут существующую схему.

## ORM и сессии
- `app/db/base.py` — `Base` для декларативных моделей.
- `app/db/session.py` — ленивый engine, `get_db()` для FastAPI, `session_scope()` для скриптов, `check_database_connection()`.
- `app/models/` — 18 таблиц по `db/001_init.sql` и миграции `003_photo_processed_storage.sql`.
- `app/models/__init__.py` — импорт всех моделей; он регистрирует таблицы в `Base.metadata`.
- `app/db/session.py` не вызывает `Base.metadata.create_all()`: схема приходит только из SQL-миграций.
- `DATABASE_URL` обязателен только при реальном обращении к БД; импорт приложения и unit-тесты работают без него.
- Деньги и объёмы — `Decimal`/`NUMERIC`; в моделях нет `Float`.
- `normative_chunks.embedding` — `pgvector.Vector` без размерности. HNSW/IVFFlat появится отдельной миграцией после выбора embedding-модели.

## Фотографии дефектов

После применения `db/003_photo_processed_storage.sql`:

```powershell
curl.exe -X POST -F "file=@C:\photos\defect.jpg" `
  http://127.0.0.1:8000/api/v1/requests/<request_id>/photos
curl.exe -o defect.jpg http://127.0.0.1:8000/api/v1/photos/<photo_id>
```

`STORAGE_DIR` содержит отдельные каталоги `originals/` и `processed/`.
Размер ограничен `STORAGE_MAX_FILE_SIZE` (10 MiB по умолчанию). API принимает
только JPG/JPEG, PNG и WEBP, проверяет MIME, фактический формат, целостность,
имя и лимит пикселей. Подробная приемочная инструкция — в
[`../docs/backend/card-6-photo-storage.md`](../docs/backend/card-6-photo-storage.md).

## Слои (не смешивать в одном модуле)
```
api (роутеры, Pydantic) → services (правила) → repositories (SQL) → adapters (файлы, пайплайн, ML)
```
Роуты, которые ходят в БД, объявляем как обычные `def` (не `async def`): стек sync (SQLAlchemy 2.0 + psycopg3).

## Правила
- Секреты только в `.env` (в git — `.env.example`).
- Деньги и объёмы — `Decimal`/`NUMERIC`, не `float`.
- Не хватает масштаба/норматива/цены → статус уточнения, **не выдумывать числа**.
- Не логировать пароли, JWT, содержимое `.env`, тела файлов.
