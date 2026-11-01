# new_backend: адаптация c559d27

Учтён исходный commit `c559d27046d5028f83ed4f67dda4e8418618303d` от 31.10.2026, Implement users, roles, and equipment API. Сравнение с ранее перенесённым `16b79affc155d75b76f585dcdfa4e5acc1781cfb`; исходная ветка не изменена.

| Возможность источника | Текущее место dev | Решение |
|---|---|---|
| Equipment CRUD, pagination, optional type/date, properties, soft retirement | integration/management.py; schemas/management.py | Адаптировано к существующим SQL таблицам, site scope, CSRF, revision и защите активных работ |
| Users, roles, me, assignment of role | management API + security/sessions.py | Профиль и роли реализованы, admin выдаёт членство только своего объекта, регистрация создаёт ожидающую заявку |
| Auth, session routers | app/main.py; security/sessions.py | Сохранена общая opaque session с CSRF. Cookie с UUID пользователя из источника не переносится как механизм доступа |
| Async engine/models, create_all, source 004_sessions | database/migrations 001–008, reflected models | Дублирующая схема/номер миграции не копируются; рабочие факты добавлены 008 без изменения применённых SQL |
| Security helper и прежние тесты | backend/app/security; tests | Сохранены; добавлены реальные PostgreSQL/HTTP и browser проверки |

Это перенос поведения и совместимых контрактов, не Git merge и не обещание идентичности файлов. Source users list/me с 501 заменены действующими реализациями; небезопасные/незавершённые пути не подключены вторым приложением. Все 42 изменённых пути учтены в BRANCH_FILE_MAP.json с назначением. После следующих fetch сравнивать только diff от c559d27046d5028f83ed4f67dda4e8418618303d; не копировать источник поверх текущего runtime.

[Проверки](../../reports/flexible_planning_verification.md), [процесс](../WORKFORCE_PLANNING.md), [правила переноса](../BRANCH_INTEGRATION_GUIDE.md).
