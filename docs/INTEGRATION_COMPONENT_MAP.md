# Карта компонентов перед переносом

Основа: удалённая `main` d94f528df8c0e0f69c344ebd8c79a99bfbe5c1f2.
Версии всех источников зафиксированы в [реестре](BRANCH_SOURCES.json).

| Источник | Фактическое содержимое | Пересечение и решение | Зависимости |
|---|---|---|---|
| main | DTO, архитектура и домен, SQL 001–003, RF и CV | Сохраняется как основа, устаревший README актуализируется | Python, PostgreSQL, ML-артефакт |
| kran_dev | SQL 004, отражаемый ORM, repository/service, demo seed, SQL/ORM тесты | SQL 001–003 и DTO уже есть; переносить только дополнения | Мигрированная PostgreSQL |
| new_backend | Проверка ролей и 7 тестов | Удаления отсутствующих в старой основе файлов не переносить | DTO ролей |
| qa/roles-contracts | Контрактные позитивные/негативные RBAC тесты | security совпадает с new_backend; одна реализация | new_backend |
| docs/tests-p0 | ORM/SQL/RBAC и P0 документы, самостоятельная SQL проверка | ORM повторяет kran_dev; QA повторяет qa; db/tests объединить с database | SQL 001–004, pytest, psql |
| front/mvidy | React SPA, страницы, UI kit, тесты маршрутов, локальные fixtures | UI сохраняется; production transport подключить к БД через FastAPI; fixtures только demo/test | Настоящие сессии, site scope, DTO адаптер |
| feat/ml-forecasting-photo-review | RF/CV улучшения, condition evidence, JSON/provider границы, тесты | Продолжает ML из main, без второго ML проекта; namespace ml_service.app | Единые maintenance-0.1 DTO и фото storage |
| archive/legacy-ai-estimator | История прежнего сметного продукта | Уникальный код исключён по заданию | Нет |

Порядок: SQL/ORM и QA → ML → frontend → HTTP/session/DTO адаптеры → сквозные проверки → итоговые документы.

Исходники содержат контракты, но не готовый HTTP backend, планировщик или аутентификацию. Интеграционный API должен явно отделять поддерживаемое поведение от ещё не реализованного. Нельзя выдавать календарные примеры за рассчитанный план, model unavailable за успешный AI или demo выбор роли за настоящую аутентификацию.
