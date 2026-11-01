# Интеграция исходных веток

Назначение: сохранять происхождение перенесённого поведения и порядок следующих переносов. [Точные SHA](../BRANCH_SOURCES.json), [карта исходных путей и blob](../BRANCH_FILE_MAP.json) остаются машинными справочниками.

`dev` — единственная интеграционная ветка. Исходники не переименованы, не перестроены и не обновлялись нашими коммитами. Изменения переносились файлами и ручными адаптерами, без merge/rebase/cherry-pick. Публикация и PR требуют отдельного разрешения.

## Реестр и доказательство переноса

Полная [машинная карта](../BRANCH_FILE_MAP.json) сохраняет все исходные пути/blob. В таблицах ниже сокращённые frontend-пути относятся к `frontend/`, ML-пути — к `ml_service/`. [Датированные доказательства интеграции](../verification/integration.md) отделены от описания возможностей; наличие проектного DTO не означает наличие HTTP endpoint.

[BRANCH_SOURCES.json](../BRANCH_SOURCES.json) хранит точный учтённый SHA каждой ветки, статус и карту соответствия. [BRANCH_FILE_MAP.json](../BRANCH_FILE_MAP.json) перечисляет изменённые пути источников и их назначение. Ниже приведены решения по источникам; [архив](../branches/archive--legacy-ai-estimator.md) исключён.

`git log` и ancestry `dev` не доказывают перенос коммитов рабочих веток: их SHA не стали родителями интеграционных коммитов. Запись в реестре означает проверенный перенос поведения, а не возможность будущего автоматического бесконфликтного слияния. Архивная `archive/legacy-ai-estimator` всегда исключена только по полному имени; ML ветка включена.

## Практический цикл

1. Проверьте текущую ветку, `git status --short`, remotes и чужие незакоммиченные изменения. Не применяйте перенос поверх чужой работы; при необходимости используйте отдельный worktree существующей согласованной ветки. Не сбрасывайте и не чистите рабочее дерево.
2. Выполните `git fetch origin`, зафиксируйте новый SHA источника. В существующем реестре найдите **последнюю полностью учтённую версию**, а не только последний просмотренный tip. Сохраните refs исходных локальных веток для заключительной проверки.
3. Получите разницу **старый учтённый SHA → новый SHA**. Не копируйте очередную ветку целиком и не применяйте её отставание от `main` как удаление компонентов. Проверьте доступность старого объекта через `git cat-file -e OLD_SHA`; при переписанной/недоступной истории восстановите зафиксированную версию для сравнения и документируйте факт, не угадывайте по дате коммита.
4. Прочитайте карту данной ветки. Сопоставьте новые/переименованные/удалённые пути с их нынешними назначениями в `dev`; для `db/tests` используйте `database/qa`, для P0 — `docs/verification/testing.md`, для frontend mocks — только demo transport. Удаление файла в источнике не разрешает автоматически удалить его адаптированную реализацию.
5. Сначала обновите схемы/миграции и DTO, затем сервисы, ML и UI по зависимостям. Изучите tests и документацию вместе с кодом. Не редактируйте уже применённые SQL 001–008: добавляйте следующую миграцию. Сохраняйте работу ранее перенесённых компонентов.
6. Применяйте выбранные hunks вручную либо обычным `git apply` после `--check`; пути и контексты адаптируйте по карте. Не используйте `--3way`, merge, rebase, cherry-pick или `git pull`, запускающий слияние. Не разрешайте конфликты выбором «вся новая ветка».
7. Выполните связанные проверки и `scripts/verify.py --browser` для критических изменений. Для схемы проверьте новую БД и upgrade с данными. Для UI/API проверьте настоящий transport, для ML — реальные origin/hash/границы/отказы; демо fixtures не заменяют такую проверку.
8. Обновите соответствующий узел в `docs/service`, архитектуру/план при изменении возможностей, существующую карту файлов и доказательства проверки. Только после переноса всех нужных изменений и проверок замените учтённый SHA. При частичном переносе сохраните прежний полностью интегрированный SHA и отдельные `reviewed_sha` / `pending_paths` с конкретными исключениями — нельзя помечать tip полностью интегрированным.
9. Создайте обычный commit только в `dev`, указав источник и SHA в сообщении. Сравните refs всех исходных локальных веток с начальным снимком; убедитесь, что новые коммиты не имеют нескольких родителей. Push/PR выполняются только в отдельно разрешённом процессе.

Пример подготовки разницы (подставьте реальные SHA из реестра и нового снимка):

```powershell
git diff --name-status OLD_SHA NEW_SHA
git diff --binary --output=.git/kran-update.patch OLD_SHA NEW_SHA -- backend/app/db database
# Сначала адаптируйте патч к нынешним путям/контрактам.
git apply --check .git/kran-update.patch
git apply .git/kran-update.patch
git diff --check
```

Эти команды не обещают автоматическое применение: например, следующий `maintenance.ts` из frontend источника содержит mock transport, тогда как в `dev` тот же путь является production fetch. Его функциональные изменения следует разделить между demo transport, типами и API.

## Согласованные правила

| Область | Правило |
|---|---|
| Python | Backend — `app`, ML — `ml_service.app`; не добавлять вторую top-level `app` в PYTHONPATH. Root pytest использует importlib |
| Канонические DTO | `backend/app/schemas/maintenance.py`, копия проектного контракта и JSON Schema обновляются совместно. ML использует canonical adapter; не создавать третью независимую схему |
| UI DTO | CamelCase проекции в `/api/v1/maintenance/ui`; snake_case доменные DTO не менять молча. Новые поля должны пройти типизацию, API и browser тест |
| Состояния | Физические SQL значения преобразуются на границе. Не записывать `accepted` в `work_orders.status` или `needs_input` в SQL CHECK `forecast_runs.status` |
| Роли | Новые аккаунты используют canonical роли. Старые роли отображаются явно; admin не получает автоматическую приёмку или выполнение |
| Фото | Только авторизованные endpoints, UUID пути, привязки к попытке/оборудованию/чек-листу, SHA-256. Новая попытка не меняет старые файлы |
| ML | Один immutable snapshot, один hash у результатов, accepted history до cutoff. Customer без модели — unavailable; синтетика всегда помечена |
| Конфигурация | Один `.env.example`, никаких секретов. Same-origin transport; фактические порты и команды в [runtime](runtime.md) |
| БД | Одна SQL-цепочка `database/migrations`; ORM отражает её. Реальные данные не использовать для тестовых destructive сценариев |
| Зависимости | Python lock и frontend package-lock обновлять после проверки совместимости. CLIP stack опционален и отдельно описан |
| Документация | AGENTS/INDEX — вход; ARCHITECTURE — вся система; service — узлы; PLAN — состояние работ; decisions — принятые решения |

Новые будущие задачи удобно начинать от актуальной `dev`, но такая рекомендация не означает переустройство существующих веток в этой работе. Автоматической синхронизации, перезаписывающей файлы или двигающей исходные refs, нет.

## Карта компонентов источников

Исторический состав исходников до адаптации (полный перенос описан по каждой ветке ниже). Основа: удалённая `main` d94f528df8c0e0f69c344ebd8c79a99bfbe5c1f2.
Версии всех источников зафиксированы в [реестре](../BRANCH_SOURCES.json).

| Источник | Фактическое содержимое | Решение исходного этапа | Зависимости |
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

## main

### Назначение и версия

Основа ТО/ППР: canonical DTO, SQL 001–003, домен и исходные RF/CV.

Зафиксированный SHA: `d94f528df8c0e0f69c344ebd8c79a99bfbe5c1f2`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [Архитектура](../ARCHITECTURE.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

### Уже выполнено в dev

Сохранены код, архитектурные материалы, Excel, ER, примеры, валидатор и RF artifact. README актуализирован.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| README.md | README.md; docs/SYSTEM_OVERVIEW.md | Состояние и запуск приведены к runtime | Не возвращать устаревшее утверждение об отсутствии SPA/сервисов |
| backend/app/schemas/*; docs/architecture/contracts/* | Те же пути | Контракты сохранены | Обновлять DTO, JSON Schema, fixtures и ML adapters совместно |
| database/migrations/001–003 | Те же пути | Без изменений | Добавлять миграции вместо редактирования применённых |
| README_1.md; p0_scenarios.md | tests/README.md; tests/p0_scenarios.md | Идентичные документы объединены с tests-p0 | Не восстанавливать корневые дубликаты |
| ml_service/* | Те же пути | Дополнено ML источником; добавлен package initializer | Не заслонять backend app при импорте |


### Проверки и известные несовместимости

Валидатор архитектуры, весь pytest, исходные SQL и ML tests.


## kran_dev

### Назначение и версия

PostgreSQL persistence: SQL 004, reflection ORM, repository/service, demo seed.

Зафиксированный SHA: `c31570eaf970d6c6d3398995b58cf7173e89d183`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [Архитектура](../ARCHITECTURE.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

### Уже выполнено в dev

Перенесены все ORM модули/тесты, SQL 004, tests 003–005, исходный seed, фото и TL03 документы. SQL 001–003 уже совпадали с main. new_file содержит только букву a и исключён как неисполняемый placeholder.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| backend/app/db/* | Те же пути | Исходные API и неоднозначные mapper отказы сохранены | Новые проекции согласовывать в integration, не подставлять неизвестные defaults |
| database/migrations/004* | Тот же путь | Сохранены точность и NOT VALID FK | Проверять старые данные перед VALIDATE |
| database/seeds/*; database/demo/* | Те же пути | Явный исходный seed; не автоматический startup | Не превращать demo историю в customer факты |
| backend/requirements.txt | Тот же путь + root requirements/lock | Объединён runtime | Проверять SQLAlchemy/psycopg и lock |
| docs/database/*; dto_db_mapping.md | Те же пути | Исходные ограничения сохранены; runtime описан отдельно | Не считать все DTO/SQL расхождения решёнными |


### Проверки и известные несовместимости

Исходные ORM/transaction tests на отдельной БД, SQL 001–008, повтор seed, upgrade и HTTP history.


## new_backend

Учтён исходный commit `c559d27046d5028f83ed4f67dda4e8418618303d` от 31.10.2026, Implement users, roles, and equipment API. Сравнение с ранее перенесённым `16b79affc155d75b76f585dcdfa4e5acc1781cfb`; исходная ветка не изменена.

| Возможность источника | Текущее место dev | Решение |
|---|---|---|
| Equipment CRUD, pagination, optional type/date, properties, soft retirement | integration/management.py; schemas/management.py | Адаптировано к существующим SQL таблицам, site scope, CSRF, revision и защите активных работ |
| Users, roles, me, assignment of role | management API + security/sessions.py | Профиль и роли реализованы, admin выдаёт членство только своего объекта, регистрация создаёт ожидающую заявку |
| Auth, session routers | app/main.py; security/sessions.py | Сохранена общая opaque session с CSRF. Cookie с UUID пользователя из источника не переносится как механизм доступа |
| Async engine/models, create_all, source 004_sessions | database/migrations 001–008, reflected models | Дублирующая схема/номер миграции не копируются; рабочие факты добавлены 008 без изменения применённых SQL |
| Security helper и прежние тесты | backend/app/security; tests | Сохранены; добавлены реальные PostgreSQL/HTTP и browser проверки |

Это перенос поведения и совместимых контрактов, не Git merge и не обещание идентичности файлов. Source users list/me с 501 заменены действующими реализациями; небезопасные/незавершённые пути не подключены вторым приложением. Все 42 изменённых пути учтены в BRANCH_FILE_MAP.json с назначением. После следующих fetch сравнивать только diff от c559d27046d5028f83ed4f67dda4e8418618303d; не копировать источник поверх текущего runtime.

[Проверки](../../reports/flexible_planning_verification.md), [процесс](assignment.md), [правила переноса](integration.md).

## front--mvidy

### Назначение и версия

React SPA, дизайн-система, маршруты, все экраны и demo transport.

Зафиксированный SHA: `226f3266a29cd43121ddca2c707cdcf5d71d375c`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [Архитектура](../ARCHITECTURE.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

### Уже выполнено в dev

Сохранены компоненты, стили, UI kit, screen map и 18 исходных UI тестов. Production подключён к реальному API. Добавлены рабочие формы исполнения/приёмки и browser E2E.

Последующая [проверка ролей и переходов](web.md) согласовала ссылки с `shared/lib/roles.ts:SECTION_ROLES`, кнопки с серверным `allowedActions`, сохранение перед фото/сдачей и переходы входа/выхода. Эти изменения находятся только в dev; при переносе новых изменений источника не затирать их старой навигацией или редактором.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| shared/api/maintenance.ts | frontend/src/shared/api/maintenance.ts + maintenance.demo.ts | Production fetch отделён от fixtures | Новые mock функции переносить в demo файл, не затирать fetch |
| shared/session/SessionContext.tsx | Тот же путь + api/request.ts | Cookie session/CSRF; demo role только с VITE_DEMO_MODE=true | Не доверять localStorage роли в production |
| ExecutorTaskPage.tsx; QualityTaskPage.tsx | Те же пути | Заглушки действий заменены API и revision | Сохранять попытки, freeze и обработку ошибок |
| shared/types/domain.ts; EvidenceGallery.tsx | Те же пути | Nullable неизвестные поля и настоящие авторизованные фото | Не создавать фиктивные UUID/сроки/происхождение |
| vite.config.ts; package*.json | Те же пути | Host-preserving proxy; Vitest 4.1.12; отдельный E2E | npm ci/build/tests/audit/browser |
| docs/ui/*; frontend/README.md | Те же пути | Карта и kit сохранены; runtime ссылка актуализирована | Согласовывать новые экраны с backend |


### Проверки и известные несовместимости

TypeScript/Vite, исходные 18 UI tests, HTTP transport test, npm audit и browser E2E.


## feat--ml-forecasting-photo-review

### Назначение и версия

RF, condition evidence, JSON/provider boundaries и CLIP photo review.

Зафиксированный SHA: `2b8488f71ec295c94cb4874cbe9f8b324c3b0e41`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [Архитектура](../ARCHITECTURE.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

### Уже выполнено в dev

Все изменения 2b8488f поверх main перенесены: condition/api/backend_adapter, CV, tests, inspect_pairs, requirements-cv и документы/эксперименты. RF/артефакт уже были в main. Настоящий CLIP inference дополнительно проверен в отдельном CV профиле с pinned весами через HTTP.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| ml_service/app/forecast/* | Те же пути + backend/app/integration/ml.py | Снимок из БД и сохранение обоих результатов; condition completeness | Проверять feature schema, hash, происхождение и cutoff |
| ml_service/app/cv/* | Те же пути + HTTP photo-review | Только фото текущего scope-checked submitted отчёта | Guardrails 1.5/1.6, идентичность, сопоставимость и unavailable |
| forecast/client.py | Тот же путь | Необязательный use_active_model; модель FastAPI изолирована | Не возвращать глобальный кеш при явном отсутствии модели |
| ml_service/tests/* | Те же пути | Все тесты сохранены; namespace/importlib устраняет shadowing | Запускать совместно с backend tests |
| docs/ml/*experiment.json | Те же пути | Исторические эксперименты источника сохранены | Не выдавать их за результаты текущего inference |
| requirements-cv.txt; var/artifacts/* | Те же пути + root lock | RF SHA проверяется при startup; CV stack отдельный | Проверять sklearn совместимость и cache модели |


### Проверки и известные несовместимости

RF/condition/provider/CV tests, настоящий persisted snapshot/hash/RF через HTTP и браузер. Настоящий CLIP inference подтверждён в строгом CV профиле; оценка качества на customer фото не выполнялась.


## qa--roles-contracts

### Назначение и версия

Позитивные/негативные контракты DTO, ролей, ownership и собственной приёмки.

Зафиксированный SHA: `00b0dcafb55ccf30514e0dca413897ae01f61f37`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [Архитектура](../ARCHITECTURE.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

### Уже выполнено в dev

Все 85 role tests сохранены. Protocol уточнён версией docs/tests-p0. Helper совпадает с new_backend и не продублирован; появились отдельные настоящие HTTP tests.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| backend/tests/test_roles_contracts.py | Тот же путь | Контрактная suite сохранена | Новые policy сверять с реальным OpenAPI/HTTP |
| ROLES_CONTRACTS_PROTOCOL.md | backend/tests/ROLES_CONTRACTS_PROTOCOL.md | Исторический protocol плюс ссылка на runtime | Исторические показатели не выдавать за текущие |
| backend/app/security/* | Одна копия new_backend | Подтверждено совпадение | Не добавлять вторую модель principal/session |
| PrincipalDirectory/ROUTES в tests | Сохранены в tests; runtime отдельно | Тестовая аутентификация не стала production | Проверять 401/403/404 через настоящий сервер |


### Проверки и известные несовместимости

85 исходных случаев, 7 helper tests, реальные session/role/CSRF/revision/self-review tests.


## docs--tests-p0

### Назначение и версия

P0 регламент, ORM/RBAC проверки и самостоятельный PostgreSQL schema QA.

Зафиксированный SHA: `f3730e86e5794d45c5fb154b194ce75a9ff9c522`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [Архитектура](../ARCHITECTURE.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

### Уже выполнено в dev

P0 сохранены в tests, SQL QA/PowerShell runner перенесены в database/qa, исторический лог сохранён. Дубли ORM/RBAC подтверждены и не размножены. new_file=a не является возможностью.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| db/tests/* | database/qa/* | Один каталог БД; обновлены пути runner | Следующие изменения старого пути перенаправлять в database/qa |
| tests/README.md; tests/p0_scenarios.md | docs/verification/testing.md; tests/README.md — ссылка | Объединены идентичные root дубликаты | Не восстанавливать README_1 в корне |
| backend/app/db/*; security/*; tests/* | Те же пути, одна копия | Совпадение с kran/new_backend/qa подтверждено | Переносить только новые уникальные hunks |
| test_maintenance_schema.sql | database/qa/test_maintenance_schema.sql | Ожидаемый SQLSTATE удаления FK исправлен на 23503; assertions не сняты | Проверять на PostgreSQL 16, не по прошлому логу |
| run_schema_test.ps1 | database/qa/run_schema_test.ps1 | Пути и проверка каталога перед cleanup | Не удалять вычисленный путь вне проверенной области |
| Компонентные проверки | scripts/verify.py + frontend/e2e | Добавлены fresh/upgrade/HTTP/browser | Отделять уровни тестов и непроверенный CLIP |


### Проверки и известные несовместимости

Все SQL assertions, ORM/RBAC tests, fresh/upgrade/seed, полный pytest и browser suite.
