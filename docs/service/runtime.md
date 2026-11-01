# Запуск и эксплуатация

Назначение: установить и проверить текущий модульный сервис. Команды выполняются из корня репозитория; проверенная среда — Windows, Python 3.12, Node 24.14, PostgreSQL 16.13.

## Код и пространства имён

```text
backend/app/main.py                 HTTP и раздача SPA
backend/app/manage.py               миграции, аккаунты, явный seed
backend/app/db/                     исходный ORM/repository/service
backend/app/integration/            согласование SQL, SPA и ML
backend/app/schemas/                maintenance-0.1, runtime management и исходные API DTO
backend/app/security/               исходные RBAC helpers и новые сессии
ml_service/app/                     ML/CV библиотека внутри backend
ml_service/var/artifacts/            исходный RF и его manifest
frontend/src/shared/api/            production fetch и отдельный demo transport
database/migrations/                одна упорядоченная SQL-цепочка
database/seeds/                     исходные демонстрационные данные
database/qa/                        SQL QA из прежнего db/tests
docs/verification/                 машинные протоколы прежних запусков
docs/service/verification.md        единственная методика, сценарии и доказательства
scripts/verify.py                   автономный временный тестовый стенд
docs/BRANCH_SOURCES.json            зафиксированные версии исходных веток
docs/BRANCH_FILE_MAP.json           происхождение и адаптация исходных путей
var/                               локальные фото/логи, игнорируется Git
```

Backend импортируется как `app`, ML исключительно как `ml_service.app`. Добавлен `ml_service/__init__.py` и pytest `--import-mode=importlib`: иначе ML test package мог заслонять `app` backend. В runtime используется тот же класс канонического DTO; JSON/provider границы ML сохранены.

## Установка и запуск

Проверено: Windows, Python 3.12, PostgreSQL 16.13, Node 24.14.0. Для воспроизводимого Python окружения используется `requirements.lock.txt`; функциональные зависимости описаны также в `requirements.txt` и манифестах компонентов. Опциональный CLIP устанавливается отдельно. Frontend использует `package-lock.json` и `npm ci`.

PowerShell, из корня проекта:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
# Отредактируйте DATABASE_URL: новая проектная PostgreSQL, не рабочая БД с чужими данными.
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m app.manage migrate
.\.venv\Scripts\python.exe -m app.manage seed-demo
npm --prefix frontend ci
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000
```

CLI загружает корневой `.env`, сохраняя приоритет переменных окружения. Команда seed явная и необязательная. Она запрашивает пароль минимум из 12 символов (или читает `FIXRATE_DEMO_PASSWORD`, который не нужно сохранять/публиковать). При повторе не сбрасывает пароли и выполненные работы. Исходный SQL seed из `kran_dev` сохранён отдельно и тестируется как исходный артефакт.

Демонстрационные аккаунты:

| Email | Роль |
|---|---|
| `fixrate-demo-1@example.test` | executor |
| `fixrate-demo-engineer@example.test` | engineer |
| `fixrate-demo-dispatcher@example.test` | dispatcher |
| `fixrate-demo-admin@example.test` | admin |

Учётные записи создаются только внутри demo объекта. Для создания обычного пользователя существующего объекта:

```powershell
.\.venv\Scripts\python.exe -m app.manage create-user --email user@example.test --name "Имя" --site <UUID-объекта> --role engineer
```

Первый объект создаётся через SQL/bootstrap; оборудование и настройки обслуживания вводятся через /settings/equipment, работники и смены — /settings/workforce. Исходный импорт Excel хранится отдельно от новых операторских версий.

Linux/macOS: `python3.12 -m venv .venv`, `.venv/bin/python` вместо Windows python.exe, `export PYTHONPATH=backend:.`; остальные команды аналогичны. Lock установлен и проверен на Windows; Linux запуск полного стенда здесь не проверялся.

Приложение: `http://127.0.0.1:8000`, OpenAPI: `/docs`, готовность: `/api/health`. Сначала примените миграции и соберите frontend, потом запускайте backend. Импорт модуля не соединяется с БД; lifespan откажет с понятной ошибкой, если схема не готова.

Для горячей разработки запускайте backend так же, а во второй консоли `npm --prefix frontend run dev`. Vite слушает 5173 и проксирует `/api` на 8000, сохраняя Host для same-origin проверки. Остановка: Ctrl+C в обеих консолях; PostgreSQL управляется его штатным сервисом. Локальный скрипт проверки останавливает только созданные им процессы.

Переменные:

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…`; обязательно |
| `PHOTO_STORAGE_ROOT` | Каталог файлов, по умолчанию `var/photos`; не внутри публичной статики |
| `COOKIE_SECURE` | `false` для loopback HTTP; `true` для HTTPS |
| `HF_HOME` | Необязательный каталог cache моделей |
| `VITE_DEMO_MODE` | По умолчанию false; true создаёт явно демонстрационную SPA с fixtures, без реальных изменений |
| `TEST_DATABASE_URL` | Только исходные ORM тесты; пустая база `fixrate_test_*` |
| `INTEGRATION_DATABASE_URL`, `FIXRATE_TEST_PASSWORD` | Только подготовленный временный HTTP тестовый стенд; задаёт runner |

Docker Compose/nginx/CI в рабочих источниках были проектными решениями, исполняемых конфигураций не было. Они не выдаются за готовый способ развёртывания. Сейчас реализован запуск одного FastAPI процесса со статикой и PostgreSQL. Инфраструктура для публичного доступа, TLS, резервное копирование и эксплуатационный мониторинг требуют отдельной задачи.

## Проверки

### Отдельное окружение с настоящим CLIP

Обычная установка поддерживает RF и guardrails без тяжёлого CV стека. Для локального семантического анализа подготовьте отдельный профиль. Веса не включаются в Git и не скачиваются API во время запроса:

```powershell
py -3.12 -m venv .venv\cv
.\.venv\cv\Scripts\python.exe -m pip install -r ml_service/requirements-cv.lock.txt
$env:HF_HOME = Join-Path (Resolve-Path .venv).Path 'cv-cache'
.\.venv\cv\Scripts\python.exe scripts/prepare_clip.py --download
$env:FIXRATE_REQUIRE_CLIP = '1'
.\.venv\cv\Scripts\python.exe scripts/verify.py --browser --output var/verification-cv
```

`prepare_clip.py` скачивает только заданный revision публичной модели, без токена аккаунта, и проверяет локальную загрузку. `FIXRATE_REQUIRE_CLIP=1` добавляет к HTTP сценарию обязательную проверку использованного model_ref; такой прогон не проходит за счёт unavailable или тестового классификатора. Без сети повторный запуск использует подготовленный cache.

Для приложения с этим профилем сохраните тот же `HF_HOME` и запускайте `.venv/cv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000`. После подготовки отсутствовавших артефактов перезапустите backend. Проверка на искусственных тестовых изображениях подтверждает исполнение модели и контракты, но не точность на фотографиях заказчика.

Основная команда из корня:

```powershell
.\.venv\Scripts\python.exe scripts/verify.py --browser --pg-bin "C:\Program Files\PostgreSQL\16\bin"
```

`--browser` требует установленный Chrome. Без этого флага выполняются все остальные проверки. Логи сохраняются в `var/verification/`; аргумент `--output` меняет каталог. Runner не использует рабочий `DATABASE_URL`: создаёт новый кластер в TEMP, слушающий loopback на свободном порту, отдельные БД для ORM, runtime, upgrade и браузера; останавливает свои процессы и удаляет только проверенный собственный временный каталог.

Проверяются 001–004 и все SQL assertion исходников, повторный исходный seed, upgrade заполненной 004 до 008 с сохранением истории работ/назначений, повтор мигратора, новая 001–008, повтор runtime seed, все Python тесты с настоящей БД, 12 исполняемых сценариев оркестрации, архитектурный валидатор, compileall, TypeScript/Vite, UI тесты и npm audit. Browser E2E использует собранную SPA и настоящий uvicorn: календарь → два прогноза → создание задания → подтверждение бригады → reload; также сохранены проверки четырёх ролей, фотоотчёта, доработки, приёмки и RF.

Изолированные команды:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q
.\.venv\Scripts\python.exe -B docs/architecture/validate_artifacts.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix frontend audit --audit-level=moderate
```

Обычный pytest без тестовых URL пропускает PostgreSQL/HTTP проверки: такой запуск не равен полному прогону. Vitest использует demo fixtures для проверки всех исходных маршрутов/доступности; production transport отдельно проверяется браузерным E2E. Фактические итоги, команды и ограничения — в [проверках](verification.md).

## Диагностика и ограничения

- `DATABASE_URL is required`: настройте `.env` и передайте `--env-file .env` uvicorn; драйвер должен быть `postgresql+psycopg`.
- Ошибка startup о 004/008: примените SQL-цепочку. Сервер не запускает миграции автоматически и не создаёт таблицы через ORM.
- UI 404 при прямом открытии: сначала соберите `frontend/dist`, затем перезапустите backend; статика монтируется при создании приложения.
- 401: повторный вход или проверка активности пользователя/членства/объекта; клиентский выбор роли в production не даёт доступ.
- 403 при mutation: CSRF cookie/header, роль или запрет собственной приёмки. За reverse proxy сохраняйте корректный Host/origin.
- 409: перечитайте карточку; параллельный запрос мог уже увеличить revision. Повторная сдача/приёмка не создаёт дубликатов, но универсального Idempotency-Key store пока нет.
- `MISSING_CHECKLIST` / `MISSING_BINDING`: запись в БД не содержит согласованного входа; заполнение не подменяется fixtures.
- `UNCONFIRMED_RULE`: seed намеренно не утверждает неоднозначные правила заказчика. Нужно предметное подтверждение, а не снятие проверки.
- `MODEL_NOT_READY` / `CLIP_MODEL_UNAVAILABLE`: проверьте manifest, артефакт, опциональные зависимости и локальный cache. Отсутствие ML не означает успешный прогноз.
- Нет `ui` payload в старом сравнении: нужны дополнительные достоверные поля и backfill. Старые записи не удалены.

Физическая модель и проектные DTO содержат ещё не покрытые отображением сценарии. Поддержка нескольких единиц оборудования в одном наряде остаётся в repository; нынешняя форма загрузки фото требует ровно одну единицу и возвращает 422 для неоднозначного наряда. Проекции SPA показывают основное оборудование наряда; расширение для нескольких единиц требует отдельного UI, а не потери исходных связей в БД.

## Границы поставки

Готовых конфигураций Docker Compose, nginx и CI для всего приложения в текущем дереве нет. Проектный ориентир 4 CPU / 8 ГБ RAM не является измеренным ресурсным бюджетом. GPU не обязателен архитектурно. Перед внешней эксплуатацией нужны замеры на целевом стенде, резервирование БД/фото/моделей и проверка восстановления, мониторинг, ограничения запросов и политика регистрации. Миграции применяются отдельно; `create_all()` не используется.

Для будущего развёртывания сохранена последовательность: готовность PostgreSQL → отдельное применение миграций с остановкой при ошибке → запуск backend → проверка `/api/health` → SPA/proxy с корректным Host/origin. БД, фото и модели требуют постоянного хранения и совместимого восстановления. Сейчас health проверяет `SELECT 1`, а не качество или готовность AI; Compose volumes/healthchecks остаются проектом, не существующей конфигурацией. Прогрев CLIP при startup не реализован, см. [ML/CV](ml.md).

## Связи

[Данные и миграции](database.md) · [проверки и протоколы](verification.md) · [разработка и обновление источников](development.md).
