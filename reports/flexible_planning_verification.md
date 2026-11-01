# Проверка гибкого планирования в dev

Дата: 01.11.2026. Изменения расширяют текущую систему ТО/ППР; legacy-оценщик не используется.

## Критерии собственных задач

| YouGile | Реализация | Проверка |
|---|---|---|
| [ALG01 / FRAI-30](https://ru.yougile.com/team/c4b6454ff761/#FRAI-30) | scheduling_rules.md, CalendarPattern, единые реальные кварталы/годы и ISO-недели | test_recurrence, test_domain_scenarios, canonical schema validator |
| [ALG02 / FRAI-37](https://ru.yougile.com/team/c4b6454ff761/#FRAI-37) | scheduling.generate_month, ресурсы и диагностика, веб-предпросмотр | test_scheduling, runtime integration, settings E2E |
| [ALG03 / FRAI-47](https://ru.yougile.com/team/c4b6454ff761/#FRAI-47) | assignment.select_crew, employment/смены/исключения, допуски и нагрузка, ручной выбор | test_assignment, test_shifts, test_management, CrewSelectionPanel, settings E2E |
| [ALG04 / FRAI-53](https://ru.yougile.com/team/c4b6454ff761/#FRAI-53) | orchestrator/decision.py, общий snapshot, независимые методы и fallback | test_orchestration, verify_orchestration.py |
| [ALG05 / FRAI-62](https://ru.yougile.com/team/c4b6454ff761/#FRAI-62) | integration/planning.py, source token, idem key и уникальное вхождение | test_planning, PostgreSQL/HTTP, planning E2E |
| [ALG06 / FRAI-68](https://ru.yougile.com/team/c4b6454ff761/#FRAI-68) | единый API PostgreSQL → прогнозы → решение → задание → предложение состава | test_planning, test_runtime_integration, planning/settings E2E |
| [ALG07 / FRAI-75](https://ru.yougile.com/team/c4b6454ff761/#FRAI-75) | prediction_comparison.md, 12 воспроизводимых сценариев | verify_orchestration.py, нет заявления точности на заказчике |
| [ALG08 / FRAI-79](https://ru.yougile.com/team/c4b6454ff761/#FRAI-79) | bounded AI, ошибки JSON/провайдера/снимка, таймаут, повтор, диагностика | test_orchestration/test_planning, orchestration_resilience.md |

Назначение сохраняется только отдельным подтверждением BE05; предложение состава в ответе генерации не является бронью. Правила, допуски и версия чек-листа читаются сервером; изменения кадров не могут молча сделать подтверждённую будущую работу недопустимой.

## Результаты проверки

Полный запуск: `.venv/Scripts/python.exe -B scripts/verify.py --browser --output var/verification-flexible-verified-20261101`. Все **24 этапа успешны**: **423 Python-теста**, **91 UI-тест**, **11 browser E2E**, **12 сценариев оркестрации**, SQL/ORM/QA, установка новой БД 001–008, upgrade заполненной 004 до 008 с сохранением истории, повтор мигратора/seed, архитектурный валидатор, compileall, pip check, TypeScript/Vite и npm audit. npm audit сообщил 0 уязвимостей; два сетевых сбоя TLS потребовали повторов, проверка сертификатов не отключалась.

Дополнительный запуск после уточнения browser assertions: `.venv/Scripts/python.exe -B scripts/verify.py --browser --output var/verification-flexible-date-controls-20261101 --pytest-target backend/tests/test_management.py`. Все 24 этапа успешны: 6 связанных Python integration tests, 91 UI, 11 E2E; отдельно проверены передача и сохранение valid_until у смены и обслуживания. npm audit — 0 уязвимостей. Это дополнительный целевой прогон, не замена полного suite выше. Неполучившиеся промежуточные прогоны сохранены в var для диагностики и не выдаются за успешные.

## Рабочая БД и Chrome

Перед применением SQL 008 создана резервная копия `var/deployments/flexible-008-20261101-114530/before-008.dump` и хеши прежних данных. Миграция применена штатным app.manage.migrate; сравнение исходных полей подтвердило неизменность данных **37 прежних таблиц**. Backend перезапущен в существующем CV-окружении; OpenAPI отвечает HTTP 200, рабочий PID 21972, loopback 8000.

Через Chrome создан отдельный synthetic_demo узел DEMO-ISO-20261101 и смена работника «DEMO — работник планирования 2» по вторникам нечётных ISO-недель. Предпросмотр ноября показал **3 и 17 ноября**. Созданы два draft-задания. Для задания `aac88c0b-5cb6-5e2a-8c5f-91f8354fe1f3` диспетчер выбрал отдельного работника, повторно проверил состав и подтвердил назначение: **03.11.2026, 09:00–10:00 Asia/Yekaterinburg**, revision 2. После reload состав/интервал/статус assigned сохранились. Второе задание `e6c8a64a-43a3-5aae-92bd-aac9e73dfdd5` осталось без назначения; генерация не резервирует человека автоматически.

Readonly SQL-проверка после веб-сценария подтвердила неизменность всех прежних work_orders/work_assignments, оборудования, пользователей, членств, бригад, ручных интервалов доступности и допусков. Прежние назначения 2 ноября сохранены. Для другого демонстрационного работника с назначением без точного времени изменение смены было отклонено 409 — неопределённая бронь не обходится.

Доказательства: `migration.json`, `web-verification.json`, `web-assignment.png` в том же каталоге развёртывания. Секреты туда не публиковались; каталоги var игнорируются Git.

## Источник new_backend

Поведение commit `c559d27046d5028f83ed4f67dda4e8418618303d` адаптировано в текущий dev. Учтены все 42 изменённых пути относительно ранее интегрированного `16b79af`; карта и исключения дублирующего/небезопасного runtime отражены в docs/BRANCH_FILE_MAP.json, BRANCH_SOURCES.json и branches/new_backend.md. Исходная ветка и legacy не изменялись; merge/push не выполнялись.

## Статус YouGile

Описания и критерии всех восьми собственных ALG01–ALG08 прочитаны в живом YouGile и сопоставлены с таблицей выше. Незавершённой реализации по этим критериям не обнаружено; исходное слово «назначение» применяется с обязательным ручным подтверждением.

**ALG01–ALG08 отмечены выполненными в YouGile:** FRAI-30, FRAI-37, FRAI-47, FRAI-53, FRAI-62, FRAI-68, FRAI-75 и FRAI-79. После новой загрузки проекта FireWhite и открытия «Мои задачи» подтверждены **0 входящих, 8 выполненных**, у каждой из восьми карточек установлен флаг завершения. Изменён только флаг выполнения собственных задач; чужие карточки, описания и сообщения не изменялись.

Подтверждение: `var/deployments/flexible-008-20261101-114530/yougile-completed.json` и `yougile-completed.png`. Код и настройки зафиксированы в dev commit `69a54c9`; последующее обновление этого отчёта фиксирует административное завершение.

## Границы

Customer-trained RF и оценка точности CV на заказчике отсутствуют; синтетические сценарии проверяют корректность процесса/политики. Формальное утверждение месяца и матрица операций по дням — отдельные функции. Остальные командные задачи не закрываются автоматически: [предлагаемые корректировки](../docs/PLAN.md).
