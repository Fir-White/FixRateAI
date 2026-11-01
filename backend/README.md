# Backend в dev

FastAPI + SQLAlchemy reflection + PostgreSQL. Canonical DTO: `app/schemas/maintenance.py`; runtime HTTP: `app/main.py`; SQL/SPA/ML adapters: `app/integration`.

ALG01/ALG02: `app/scheduling.generate_month` — новый чистый генератор чернового
календаря на текущих DTO. [Правила, JSON-примеры и вызов](../docs/algorithms/scheduling_rules.md).
Read-only HTTP-предпросмотр: `GET /api/v1/maintenance/ui/calendar/preview?year=2026&month=10`
для диспетчера/инженера. Входы загружаются из PostgreSQL на сервере. Диспетчер может
подтвердить создание заданий отдельным `POST /api/v1/maintenance/calendar/generate`.

ALG03: `app/assignment.select_crew` — подбор полного состава на общем интервале
с проверкой доступности, допусков и загрузки. [Правила и HTTP API](../docs/algorithms/assignment_rules.md).
Контекст: `GET /api/v1/maintenance/ui/tasks/{id}/assignment-context`;
расчёт: `POST /api/v1/maintenance/tasks/{id}/assignment-preview`, только диспетчеру.
Подключён к карточке задания в SPA; возвращает рекомендацию и каноническую команду,
не сохраняет назначение.

BE05: `POST /api/v1/maintenance/tasks/{id}/assign` сохраняет полный состав, интервал,
снимки допусков, ревизию и аудит в одной транзакции с повторной проверкой и блокировками.
В SPA — «Подтвердить назначение» после подбора. [Контракт и проверки](../docs/algorithms/assignment_persistence.md).

ALG04–ALG08: `app/orchestrator` и `app/integration/planning.py` — независимый ALG02/RF,
безопасная политика, bounded AI, сохранение календаря/заданий с `preview_token` и
`idempotency_key`, предложение состава в одном ответе. [Правила, API и веб-путь](../docs/algorithms/orchestration_rules.md).
Эталонный прогон: `scripts/verify_orchestration.py`, отчёты в `reports/`.

Установка, миграции новой/существующей базы, запуск, таблица API и роли: [SYSTEM_OVERVIEW](../docs/SYSTEM_OVERVIEW.md). Проверки: из корня `.venv/Scripts/python.exe scripts/verify.py --browser`.

Исходный repository/service из kran_dev сохранён. ORM не создаёт схему через `create_all`; примените SQL 001–008 до запуска. Канонические DTO описывают также будущие сервисы; фактические endpoints определяет OpenAPI приложения, а не только схемы.

`integration/management.py`: CRUD оборудования, версии обслуживания, регистрация/роль, смены, допуски, исключения, бригады; одна SQL-цепочка и общий auth. [Рабочий процесс](../docs/WORKFORCE_PLANNING.md).
