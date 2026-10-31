# FixRate AI — интеграционная ветка dev

Система ТО/ППР: оборудование → регламент → календарь → задание → фотоотчёт → решение инженера.

В `dev` собраны PostgreSQL 001–005, SQLAlchemy repository/service, FastAPI с серверными сессиями и проверками доступа, React SPA и ML/CV. Исходные рабочие ветки сохранены; перенос выполнен файлами и обычными коммитами, без Git-слияний. Ветка создана **локально**, публикация не выполнялась.

**Начните с [SYSTEM_OVERVIEW](docs/SYSTEM_OVERVIEW.md)**: устройство системы, роли, фактические API, установка, запуск, диагностика и ограничения. [Отчёт интеграции](docs/DEV_INTEGRATION_REPORT.md) содержит результаты проверок; [реестр источников](docs/BRANCH_SOURCES.json) и [порядок следующих переносов](docs/BRANCH_INTEGRATION_GUIDE.md) фиксируют происхождение кода.

## Что работает

- Чтение реестра и принятой истории, календарных вхождений, заданий и очереди инженера из настоящей PostgreSQL.
- Вход по email/паролю; серверная сессия, CSRF, роли, ограничения объекта и доступ исполнителя только к назначенным работам.
- Начало попытки, ответы на замороженный чек-лист, сохранение комментария и фото до/после, сдача, доработка и приёмка с аудитом и контролем ревизии.
- RF-прогноз на явно синтетических данных, фиксация общего входного снимка и обоих результатов, честные `needs_input` / `unavailable`.
- Проверка фото, одинаковых файлов, качества и скрытых операций; CLIP вызывается только при наличии локальных зависимостей и весов. Фотоанализ не принимает работу.

**Границы реализации:** универсального генератора/утверждения календаря, редакторов регламентов, автоматического назначения бригад и обученного прогноза для данных заказчика в источниках нет. Календарь читает сохранённые вхождения; метод `persisted-calendar-v1` использует их только для подтверждённых правил. Неподтверждённые даты не назначаются автоматически. Дополнительный CV-профиль проверен с настоящими закреплёнными весами; точность на фотографиях заказчика не оценивалась. Это не подтверждение готовности к промышленной эксплуатации.

## Быстрый запуск (PowerShell, из корня)

Требуются Python 3.12, Node.js 24, PostgreSQL 16+. Создайте отдельную базу и пользователя с правом применять проектные миграции.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
# Укажите подключение к своей новой базе в .env.
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m app.manage migrate
.\.venv\Scripts\python.exe -m app.manage seed-demo
npm --prefix frontend ci
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000
```

Откройте [приложение](http://127.0.0.1:8000) и [OpenAPI](http://127.0.0.1:8000/docs). Seed запрашивает новый пароль (12+ символов); готового пароля в репозитории нет. Аккаунты: `fixrate-demo-1@example.test` (исполнитель), `fixrate-demo-engineer@example.test`, `fixrate-demo-dispatcher@example.test`, `fixrate-demo-admin@example.test`. Это отдельные синтетические данные; импортированные неоднозначные нормы заказчика остаются неподтверждёнными. Для обычной эксплуатации вместо seed используйте `app.manage create-user` — подробности в основном документе.

## Проверки

```powershell
.\.venv\Scripts\python.exe scripts/verify.py --browser
```

Команда создаёт **собственный временный кластер PostgreSQL**, прогоняет исходные SQL/ORM/QA/ML тесты, миграции новой и заполненной базы, HTTP-процесс, сборку и UI-тесты, затем запускает реальную SPA в Chrome. Рабочий `DATABASE_URL` не используется. Подробности, включая путь к PostgreSQL и запуск без Chrome: [SYSTEM_OVERVIEW](docs/SYSTEM_OVERVIEW.md#проверки).

Матрица доступа, переходы заданий, результаты проверки и ещё не реализованные действия: [ROLE_WORKFLOW_AUDIT](docs/ROLE_WORKFLOW_AUDIT.md).

## Сохранённые предметные материалы

- [Архитектура и контракты maintenance-0.1](docs/architecture/README.md), [домен и сценарии](docs/domain/README.md), [матрица P0](tests/p0_scenarios.md).
- [Логическая ER-модель](docs/database/README.md), [спецификация](docs/database/specification.md), [сопоставление DTO/БД](docs/architecture/dto_db_mapping.md).
- [Excel заказчика](docs/customer/techical_service_schedule.xlsx), [анализ неоднозначных исходных данных](docs/architecture/customer_schedule_analysis.md).
- [ML/CV](ml_service/ARCHITECTURE.md), [UI kit](docs/ui/ui-kit.md), [карта экранов](docs/ui/screen-map.md).

![Логическая ER-модель из исходной main](docs/database/erd.png)

[Масштабируемая ER-диаграмма](docs/database/erd.svg) сохраняет исходные 35 доменных таблиц. Дополнения runtime описаны в миграции 005 и SYSTEM_OVERVIEW; изображение не подменяет физическую схему.
