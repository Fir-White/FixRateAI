# FixRate AI — backend

FastAPI-сервер для приёма заявок на ремонт и формирования **черновика** сметы (ВОР).
Сейчас реализован каркас (карточка YouGile FRAI-31): сервер, health, Swagger, ошибки, логи.
Бизнес-логики (заявки, фото, сметы, JWT) ещё нет — она в следующих карточках.

Подробное описание решений: [`../docs/backend/card-1-fastapi-skeleton.md`](../docs/backend/card-1-fastapi-skeleton.md).

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

## Проверка
```bash
pytest -q          # ожидается: 13 passed
curl -i http://127.0.0.1:8000/health          # 200 + заголовок X-Request-ID
curl -i http://127.0.0.1:8000/no-such-path    # 404 + единый JSON ошибки
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
```

Подробности, проверка и smoke-тест — в [`../db/README.md`](../db/README.md). В `backend/.env` укажите `DATABASE_URL` с тем же портом. SQLAlchemy-модели и engine появятся в карточке 2.

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
