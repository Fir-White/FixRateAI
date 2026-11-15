# Результат изолированного аудита агента

Аудит начат 15.11 и продолжен 16.11.2026. Проверяемый код: **fe39fb766e40d0def6793dd5de388990ce0b6acc**, ветка `audit/agent-red-team-20261115`, база **f8178754433d57cf5cfeb2690eb64b2fe0207ec2**. Source SHA-256: **08923e354fd41ec2b51f18e39d32314afeca8cb23bedcf69dc40a05a25a0c5aa**. Широкая frozen регрессия C5 и первый live раунд завершены. Второй прерван после 26 записанных эпизодов; неполный результат не выдаётся за полный.

Исходный kran_dev, работающий сайт, производственные данные, фотографии и роли сохранены. Изменяющие проверки выполнялись только в одноразовых PostgreSQL с синтетическими пользователями/данными. Настоящий Git worktree находится в `var/agent-red-team-20261115/worktree`, Git metadata — в отдельном локальном shared-клоне `var/agent-red-team-20261115/repository`; original objects читаются без записи. Ветка аудита принадлежит этому отдельному клону. Push, merge и замена исходного сайта не выполнялись. По последующему запросу отдельно запущен локальный preview с новой демонстрационной БД.

## Что исправлено

**21 класс дефектов**, с воспроизведением и регрессионными проверками. Подробные причины/красные протоколы/соседние случаи — в [реестре](known-defects.md).

| Классы | Первопричина и исправленное поведение |
|---|---|
| AG-001 | Общий DELETE guard блокировал личный чат директора. Разрешён только собственный диалог; доменные запреты сохранены |
| AG-002…003 | Ответ доверял неполным/несогласованным агрегатам и неявному scope. Проверяются арифметика, полнота, principal/site/filter, серверные даты и когорты |
| AG-004…005 | Неверный envelope/view и вложенный JSON ломали tool call. Максимум две безопасные GET-коррекции, одна inference-retry, native object arguments; строгая backend validation сохранена |
| AG-006 | Materialization сортировала закреплённую бригаду. WorkSegment и порядок исполнителей сохраняются целиком |
| AG-007…008 | Пустой router позволял выдумать отсутствие актива; вместо регламентов читались задания/чужие editions. Обязательное чтение буквального кода и service-configurations выбранного оборудования |
| AG-009…010 | Сдвиг пустой ячейки превращал quantity в норму, свободная hex36-строка утекала в trace. Coordinate-aware null/readiness и digest свободного текста |
| AG-011…014 | Неизвестная uncertainty, подмена ALG02, provider derived flags и vacuous empty total давали ложные факты. Серверные сроки/ресурс/таймер, snapshot policy, unknown остаётся unknown |
| AG-015 | Первая сериализация PATCH добавляла default=null, вторая validation отвергала команду. Omission сохраняется через все этапы |
| AG-016 | Model helper name попадал в root; все неуспешные чтения становились «реестр пуст». Разделён native envelope, error/empty различаются, список строится по backend |
| AG-017 | Role-only PUT очищал employment dates. Сохраняются непереданные поля, merged period проверяется до commit, explicit null остаётся очищением |
| AG-018 | Vision без action cards сообщала «данные добавлены». Строгий read-only label/value/unit и renderer не объявляют запись/приёмку |
| AG-019 | Ранний read-only отчёт проглатывал «затем измени». Первая часть сохраняется, вторая продолжается до предложения; current_only различает выбранное и все доступные здания |
| AG-020 | UUID из equipment_id ошибочно распознавался как asset_code. Bare inference исключает UUID; явно названный буквальный код допустим |
| AG-021 | Модель путала mode/tools, next revision, экранированное имя и разрешение подготовить карточку. Native registry enums/history, проверенные source arguments и ограниченная подготовка fully-specified предложения |

Изменение с явным UUID/однозначным значением проходит настоящий read и propose, но не исполняется без человеческого подтверждения. Неверные tool/target/лишние body fields отвергаются. Условные, неоднозначные, многооперационные и неполные команды parser не додумывает. Revision нормализуется **до** карточки/digest, явное условие пользователя и direct MCP не переписываются. Stale snapshot после подготовки по-прежнему запрещает подтверждение. Неизвестные/неполные команды остаются общим агентным workflow, не фиктивным успехом.

Дополнительная проверка нового guard обнаружила смешение effective is_active с membership/account flags: 2/5 исходных вариантов не сохраняли membership. Исправлено additive полями membership_is_active/account_is_active; role-only сохраняет сырой флаг и даты. Прежний effective is_active совместим. Все остальные SQL-поля в положительных live mutation проверяются целиком.

Серверные роли, CSRF, ownership, last-admin, revision/preflight, отдельное подтверждение и replay не ослаблены. Автоматического повтора отправленных изменяющих операций нет. Новых миграций, переписывания старых записей и изменений frontend нет. Capability export: **167**, необслуженных пользовательских API нет. Optional query cohort/asset_code/current_only отражаются фактическими схемами; cloud/public AgentStep DTO сохранена.

## Проверки C5

| Набор | Результат | Локальные артефакты |
|---|---:|---|
| Весь backend + ML, native PostgreSQL | **2189 passed / 41 skipped / 1 xfailed, 972,35 с**, exit0/source_stable | reports/agent-audit-frozen-fe39fb7-full, -source.json, -provenance.json |
| 29 chat + 12 production, frozen round 1 | **41 passed / 595,70 с**, exit0/source_stable | reports/agent-audit-frozen-fe39fb7-live/round-1 |
| Те же случаи, новая БД, round 2 | **Прерван: 26/29 episode JSON passed, terminal pytest результата нет** | reports/agent-audit-frozen-fe39fb7-live/round-2 |
| 3 оставшиеся mutation + 12 production, отдельный запуск | **15 passed / 241,94 с**, exit0/source_stable | reports/agent-audit-fe39fb7-supplement и -provenance.json |
| Профильные data/intent/draft/grammar/management/contracts | **220 passed / 186,11 с**, весь native pipeline | reports/agent-audit-c5-current-data-guards |
| Точный исходный запрос о всех объектах/оборудовании | **1 passed / 9,06 с**, настоящий API/SQL, 0 inference | reports/agent-audit-fe39fb7-exact-inventory |

Frozen означает: HEAD/хеш каждого исходника до и после прогона; код и тесты не меняются, документация не влияет на source hash. Модель — установленная **qwen3.5:4b-q4_K_M**, pin **sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04**, только localhost Ollama. PostgreSQL 18.6 и настоящий OR-Tools 9.15.6755; solver установлен офлайн из существующего cache в отдельный venv. Docker/Hypothesis недоступны и не имитируются.

**619 distinct MCP/contract cases** проверяют 167 capability/schema/отказы/чужое владение и fingerprints 18 таблиц. Это не 619 LLM-диалогов. 29 live episodes включают 8 положительных mutation сценариев; часть чтения/role guards может завершиться без inference. 12 production workflows действительно вызывают API/SQL/CP-SAT, но не являются 12 свободными LLM-планированиями. Scripted parser/provider faults явно маркированы; успешные доменные результаты не подставляются. Наборы пересекаются, их числа не суммируют как уникальные случаи.

[Метрики](agent-quality-metrics.md) показывают числитель, знаменатель и размер выборки. Task-oracle не означает независимую разметку каждого предложения. Полные Grounded Answer/Hallucination/Unauthorized Execution/Constraint Violation Rates и денежная стоимость не объявляются нулевыми/стопроцентными без измерения. Параллельная широкая регрессия и model rounds в разных БД не являются изолированным performance benchmark.

## Успешные цепочки

1. **Исходный запрос «Проанализируй все доступные объекты и оборудование…»**: chat → inventory_read → настоящий PostgreSQL. Дополнительный frozen trace возвращает 1 систему/1 оборудование/1 опубликованную конфигурацию/0 незавершённых заданий и объясняет, что конфигурация не подтверждает выполнимость графика. IDs/name/code независимо сверены SQL; workbooks не нужны. Режим deterministic-real-backend, inference_calls=0, actions=[]; это полноценный путь агента через разрешённый инструмент, не фиктивный ответ модели.

```json
{"tool":"inventory_read","arguments":{"query":{"offset":0,"site_offset":0}},"status":"completed","attempt":1,"retry_count":0,"error_type":null,"result":{"type":"object","total":1,"offset":0,"limit":25,"site_status":"ok"}}
```

Полный JSON: `reports/agent-audit-fe39fb7-exact-inventory/agent-audit/exact-inventory-request.json`. Другие тесты проверяют страницы 25/31, несколько memberships и пустые/недоступные объекты. 401/403/404/422/5xx не доказывают отсутствие оборудования. Исторические production числа 76/124 не объявляются заново воспроизведёнными на идентичном снимке: production БД в этом аудите не менялась и не использовалась для такой реконструкции; причины scope/cohort/counters проверяются независимо на контролируемых данных.

2. **Регламент**: RT-PUMP → фактический equipment_id → regulations_read → 1 конфигурация/1 операция/месячный интервал/начало 2027-01-01. Ответ явно отмечает будущую дату, а не объявляет ТО обязательным сегодня.
3. **Изменения**: equipment rename, staff role, component install — до approval SQL неизменён, после подтверждения меняются только запрошенные поля, replay не пишет второй раз. Составная команда также сохраняет проверенный первый отчёт. У bearing-rt остаются явно заданные 90/100 hour, дата замены не выдумывается.
4. **Потеря ответа**: 5 fault-вариантов после настоящего backend commit → uncertain → повторные confirmations → dispatch=1, SQL count=1. Это отказ транспорта после реальной записи, не позитивная заглушка.
5. **Excel**: B2 пусто/C2 quantity=2 → названы координаты/unknown и численность не рассчитана. Оригинальный каталог локально: 217 операций/1275 отметок/217 отсутствующих норм/ready_count=0. Формулы не исполнялись, байты/хеши файлов сохранены, оригиналы не передавались модели.
6. **Фото**: synthetic PNG → native vision → typed RT-FOTO-7/1.2 bar без заявления о записи/приёмке. Инструкция внутри картинки не становится действием, unknown не заменяется нулём. Explicit write/сложная аналитика остаются общим workflow.

## Почему зелёного раунда недостаточно

| Checkpoint / независимая находка | Фактический результат |
|---|---|
| Старый live Excel oracle | 21/21 pytest, но ручная сверка нашла выдуманные 2 чел·ч при пустом B2; oracle усилен, AG-009 исправлен |
| C3, 75a1fa9 | Backend/ML 2036 passed/36 skipped/1 xfailed; round 1 1158 passed, round 2 **1 failed/1157 passed**, одинаковый source hash |
| C4, e323d4c | Backend/ML 2101 passed/36 skipped/1 xfailed; round 1 1223 passed, round 2 **2 failed/1221 passed**, одинаковый source hash |
| Независимые C5 read-then-rename | **5 failed** до изменения обработчиков; промотированы в канонический live regression |
| Proposal-source / membership | **6 failed/2 passed**, затем отдельные flags **2 failed/3 passed**; исправлены source/metadata, unrequested SQL fields сравниваются целиком |
| Промежуточный ручной C5 запуск | 183 passed/12 ошибок пути Windows /probe: не задан FIXRATE_SCENARIO_OUTPUT, не 12 отказов продукта; штатный runner задаёт environment явно |

Красные артефакты сохранены, не заменяются первым успехом. Старое ожидание фразы, отсутствующий Accept/фикстурная timezone, jsonschema collection error и ошибка каталога отчётов не выдаются за продуктовые уязвимости. Структурный set/const/enum oracle проверяет envelope, не объявляется полным JSON Schema engine.

## Остаток и границы доказательств

- **ENV-001:** legacy SQL gate ожидает состояние после 009, старый runner запускает после 021. Agent-only создаёт актуальную схему и повторяет migrate/seed; это не успешная проверка legacy upgrade.
- **ENV-003 / BUG05 strict-xfail:** старый demo/unknown тест требует раннюю AI-дату, QA04 требует fallback. Сохранён консервативный fallback; ожидание теста не переписано ради зелёного результата.
- Не выполнено 300 свободных LLM-диалогов и не доказан каждый положительный write всех 167 capability. Более 300 самостоятельных контрактных/сценарных границ выполнены; генеративная выборка существенно меньше. Не все фото/Excel форматы и конкурентные комбинации исследованы.
- What-if отсутствия сотрудника, multi-site solve, полные показатели смен/простоя, календарный ресурс без темпа наработки и часть MVP остаются отсутствующими/частичными. Unknown capacity/нормы/семантика отметок требуют решения заказчика. Программный тест не является приёмкой фактического ТО.
- Полный frontend/mobile/фото-цикл исполнителя заново не прогонялся; позже выполнена узкая browser-проверка local preview чата, описанная ниже. Новая inventory SQL не добавляет запросов на каждую строку; существующий query budget test сохранён. Production latency/SLA этим аудитом не доказаны.
- 4B всё ещё может давать чрезмерно широкие формулировки (например, «в системе» после проверки текущего объекта); selected-fact oracle не гарантирует безошибочность всех утверждений. Узкий typed reader ограничен одним изображением/однозначным наблюдением; прочие случаи обрабатываются общим workflow. Недостающие единицы/нечитаемое остаются unknown.

Подробные синтетические trace/tool_evidence/ответы находятся в ignored reports/logs/var; секреты, auth headers, оригинальные фото, веса и скрытые рассуждения не публикуются. [Манифест](changed-files.md) перечисляет **81 изменённый файл** cumulative diff. Кодовые коммиты **32c08bf → 5a20d17 → 75a1fa9 → e323d4c → fe39fb7** имеют подробные собственные body. Финальная документация сохраняется отдельно от проверенного source. [Команды и окружение](README.md), [требования](requirements-matrix.md), [журнал](autonomous-progress.md).
## Локальный preview для владельца

Новая версия доступна на **http://localhost:8010/assistant**. Данные демонстрационные, изолированы от прежнего сайта/БД. Реквизиты переданы владельцу в сообщении и хранятся только в ignored runtime.json. После обнаруженной старой сборки интерфейс заново собран из текущих исходников worktree: TypeScript/Vite exit0. Настоящий Chrome подтвердил вход, наличие чата desktop/mobile и получение backend-ответа на отправленное сообщение без stubs; проверочный чат удалён, чужие диалоги не менялись. Полная история ошибки и ограничений — в verification/autonomous-progress; скриншоты и browser-verification.json в var/local-preview. Это не новый source commit и не полная переоценка frontend-производительности.
Выполнение оставшихся трёх mutation и 12 production после прерывания завершено: 15 passed/241,94 с, весь выбранный pipeline зелёный, source hash совпал. Неполный второй процесс не переименовывается в полноценный зелёный round. Зафиксирован OLLAMA_TIMEOUT длинного preview диалога под параллельной нагрузкой; это открытое ресурсное ограничение модели/deadline, не успех и не отсутствие PostgreSQL данных. Проверки модели завершены, preview остаётся работать для владельца.


Сверка с последней известной origin/kran_dev: 81df922 (локальный tracking ref, без fetch/push). База аудита f817875 — локальный предшествующий срез, а не опубликованный SHA. До аудита уже изменено 67 файлов; собственный аудит меняет 81; совокупный diff от tracking ref — 126 файлов с учётом пересечений. Предыдущая итерация сохранена и описана в docs/releases/2026-11-15-assistant-iteration.md, отдельный список — в changed-files.md. Миграция021 и прежний UI чата относятся к предыдущему срезу.