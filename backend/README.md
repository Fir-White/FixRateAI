# Backend

## Запуск через Docker Compose

Из корня репозитория требуется Docker Desktop с Compose v2:

```powershell
docker compose up -d db
docker compose build backend
docker compose run --rm migrate
$env:FIXRATE_DEMO_PASSWORD = "Local-demo-password-2026"
docker compose run --rm seed
docker compose up -d backend
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

Пароль seed задаётся только через переменную окружения и не записывается в
репозиторий. Для остановки и удаления локальных данных:

```powershell
docker compose down
docker compose down -v  # удалить только локальную БД и фото Compose
```

`migrate` и `seed` запускаются явно: API не изменяет схему и данные при старте.
Повторный `migrate` безопасен благодаря журналу checksum миграций, повторный
`seed` не сбрасывает пароли и историю.

## Локальный запуск без Docker

Полная инструкция с `.env`, PostgreSQL, frontend и проверками находится в
[`docs/service/runtime.md`](../docs/service/runtime.md).

Ключевые параметры:

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | PostgreSQL URL с драйвером `postgresql+psycopg` |
| `PHOTO_STORAGE_ROOT` | Приватный каталог загруженных фото |
| `COOKIE_SECURE` | `true` только за HTTPS |
| `CORS_ORIGINS` | Явный список origin через запятую; wildcard запрещён |

Ошибки API возвращают JSON с `code`, `message`, `details` и `request_id`.
Серверные логи содержат метод, путь, статус и request ID, но не cookies,
заголовки авторизации, тела запросов или пароли.
