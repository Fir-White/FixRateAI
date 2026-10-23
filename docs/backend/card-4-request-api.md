# FRAI — API управления заявками

**Статус:** DONE  
**Зона:** `backend/` · **Исполнитель:** Яна

## Реализовано

Добавлены четыре стабильных endpoint-ы:

- `POST /api/v1/requests` — создание заявки;
- `GET /api/v1/requests` — список с пагинацией и фильтрами;
- `GET /api/v1/requests/{request_id}` — заявка, метаданные фото и текущие размеры;
- `PATCH /api/v1/requests/{request_id}` — редактирование, отмена и ручные размеры.

Слои разделены:

```text
api/v1/requests.py
    -> services/request_service.py
        -> repositories/request_repository.py
            -> models + PostgreSQL
```

Схема БД не изменялась: используются существующие `repair_requests`,
`request_photos`, `defects` и `defect_measurements` из `db/001_init.sql`.

## Правила

- При создании нужен непустой `description` или хотя бы одно фото. Для уже
  загруженного файла передаются его `storage_key` и проверяемые метаданные.
- `building_id` проверяется на существующий активный объект.
- `title` обрезается и ограничен 255 символами.
- Фильтры списка: `limit` 1–100, `offset` от 0, `status`, `building_id`.
- Редактирование текста доступно в статусах `created` и
  `needs_clarification`.
- Отмена разрешена из `created`, `needs_clarification` и `ready_for_review`,
  только с непустым `cancellation_reason`.
- Размеры сохраняются как `source_type='manual'`; предыдущая текущая запись
  помечается `is_current=false`, новая ссылается на неё через
  `supersedes_measurement_id`.
- Неактивный или отсутствующий пользователь API возвращает `401`.
- Ошибки БД возвращают `503 DB_UNAVAILABLE`; traceback не попадает клиенту.
- До внедрения JWT используется `DEMO_USER_EMAIL`/`demo_user_email` с дефолтом
  `demo.operator@fixrate.local`.

Загрузка бинарных файлов и полноценный адаптер хранилища остаются в карточке
фото. Текущий endpoint сохраняет только безопасную ссылку и метаданные
(`storage_key`, имя, MIME, размер и SHA-256); `photo_ids` предназначен для уже
сохранённых метаданных фото.

## Проверка

Из корня репозитория в PowerShell:

```powershell
.\venv\Scripts\python.exe -m pytest -q backend\tests\test_requests_api.py
.\venv\Scripts\python.exe -m pytest -q backend\tests
```

С живой PostgreSQL:

```powershell
docker compose up -d
# применить db/001_init.sql и db/002_seed_demo.sql
$env:DATABASE_URL="postgresql+psycopg://fixrate:fixrate@localhost:5432/fixrate"
.\venv\Scripts\python.exe -m pytest -q backend\tests\test_models_db.py
```

Интерактивная проверка доступна через Swagger: `http://127.0.0.1:8000/docs`.

Если Docker PostgreSQL запущен на `5433`, перед проверкой задайте:

```powershell
$env:DATABASE_URL="postgresql+psycopg://fixrate:ChangeMe-local-only@127.0.0.1:5433/fixrate"
.\venv\Scripts\python.exe -m pytest -q backend\tests\test_models_db.py
```
