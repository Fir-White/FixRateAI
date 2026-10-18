# FixRate AI — Backend

Каркас FastAPI (карточка 1 YouGile). Сейчас доступны health и Swagger; заявки, JWT, БД и фото — в следующих карточках.

## Требования

- Python **3.12+** (рекомендуется 3.12)
- Опционально: Docker для PostgreSQL (схема DDL ещё не подключена)

## Установка и запуск

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
# source .venv/bin/activate

pip install -r requirements-dev.txt
copy .env.example .env
# Linux / macOS: cp .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Откройте:

| URL | Назначение |
|---|---|
| http://127.0.0.1:8000/health | Проверка живости |
| http://127.0.0.1:8000/docs | Swagger (демо UI до фронтенда) |
| http://127.0.0.1:8000/openapi.json | OpenAPI JSON |

## Пример: health

**Запрос**

```http
GET /health HTTP/1.1
Host: 127.0.0.1:8000
```

или:

```bash
curl -i http://127.0.0.1:8000/health
```

**Ответ `200`**

```json
{"status":"ok"}
```

В ответе всегда есть заголовок `X-Request-ID` (принятый от клиента или сгенерированный UUID).

## Пример: неизвестный путь

```bash
curl -i http://127.0.0.1:8000/no-such-path
```

**Ответ `404`** (формат стабильный для всех ошибок):

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Not Found",
    "details": [],
    "request_id": "…"
  }
}
```

## Самопроверка

```bash
cd backend
pytest -q
```

Ожидается: все тесты зелёные; вручную — `/health` и `/docs` отдают `200`.

## Конфигурация

См. `.env.example`. Ключи `DATABASE_URL`, `STORAGE_DIR`, `ML_BASE_URL`, `JWT_SECRET` зарезервированы под следующие карточки; в карточке 1 приложение их только читает в settings.

## PostgreSQL (опционально)

Из корня репозитория:

```bash
docker compose up -d
```

Поднимается Postgres 16 с образом `pgvector/pgvector:pg16`. Таблицы появятся после официального DDL архитектора (папка `db/`). Пока `create_all` и самодельные миграции **не используются**.

## Структура слоёв

```
app/
  api/v1/       # роутеры + позже Pydantic на границе
  core/         # config, logging, errors, middleware
  schemas/      # схемы ответов/запросов
  services/     # бизнес-правила
  repositories/ # SQL
  adapters/     # файлы, пайплайн, stubs
  models/       # ORM — карточка 2
```
