# Backend в dev

FastAPI + SQLAlchemy reflection + PostgreSQL. Canonical DTO: `app/schemas/maintenance.py`; runtime HTTP: `app/main.py`; SQL/SPA/ML adapters: `app/integration`.

Установка, миграции новой/существующей базы, запуск, таблица API и роли: [SYSTEM_OVERVIEW](../docs/SYSTEM_OVERVIEW.md). Проверки: из корня `.venv/Scripts/python.exe scripts/verify.py --browser`.

Исходный repository/service из kran_dev сохранён. ORM не создаёт схему через `create_all`; примените SQL 001–005 до запуска. Канонические DTO описывают также будущие сервисы; фактические endpoints определяет OpenAPI приложения, а не только схемы.
