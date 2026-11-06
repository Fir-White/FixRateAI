# Регрессия редизайна v2

[Baseline](BASELINE.md) · [Изменения](IMPLEMENTATION_LOG.md) · [Визуальная проверка](VISUAL_QA.md) · [Итог](FINAL_REPORT.md).

Исходная версия: `frontend_polished` / `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Изменения находятся только в `feat/frontend-redesign-v2`. Проверки чтения использовали существующий стенд :8000 через Vite :5174; все мутации — отдельный seed PostgreSQL 18/API :18074. Облачные ключи очищены, production-приёмки не создавались.

## Проверки и границы

| Проверка | Статус | Доказательство и границы |
|---|---|---|
| Backend: seed, scheduling, roles, runtime, analyst | passed | 258 тестов на отдельной PostgreSQL, Python 3.12; `reports/redesign-v2/c16-backend.log` |
| Полный backend + ML pytest | passed | **727/727**,0failed,0skipped,122.30s; отдельные runtime и пустая persistence DB. `c16-python-full.log`. Runtime/ML source не менялся |
| after_accepted_completion, date-only, future/accepted history, timezone | passed | Существующие scheduling/runtime тесты; алгоритм не менялся. Следующий срок зависит от фактического выполнения принятой работы |
| API capabilities, forbidden mutation, files, attempts, revision conflicts | passed | Backend roles/runtime. Подробный состав: [контракты](CONTRACT_AUDIT.md) |
| Семь периодичностей и скрытые обязательные поля | passed | `ServiceSettingsPage.test.tsx`: сохранённый payload, раскрытие/фокус ошибки; live keyboard без записи на :8000 |
| Сохранённая смена: открыть → изменить → сохранить → открыть | passed | Изолированный `settings.spec.ts`: тот же ID, expected_revision, revision+1, прежние calendar intervals/diagnostics. 2/2 целевых E2E |
| Legacy sparse CalendarPattern | passed | 19 parser + 3 workforce unit; live открытие сохранённого sparse pattern. Неизвестный формат блокирует сохранение |
| Executor/director document readonly и фактический ноль | passed | `ReadOnlyEvidence.test.tsx`: 3 проверки, инженерное основание недоступно, исходный документ доступен |
| Права навигации шести ролей | passed | 112 unit. Query охватывает также CSS-hidden запрещённые ссылки; видимый heading проверяется отдельно. Таймаут не повышался |
| Подбор/сохранение назначения | passed | Реальные `assignment.spec.ts`, `planning.spec.ts`, регистрация→crew→service→confirmed work в изолированной БД; отсутствие relation старого стенда не обходится |
| Protected visual regression | passed | 32/32 exact comparisons, 0 changed pixels; `protected-after-final-shared.json` |
| Archive integrity | passed | Все 1933 извлечённых файла совпали по SHA-256 с ZIP; исходный ZIP hash совпал с BASELINE |
| Полная итоговая UI unit-регрессия | passed | 433/433,40files; `unit-final.log`, default5s timeout, maxWorkers1 |
| TypeScript UI/E2E тестов | passed | `tsc -p tests/web/tsconfig.json --noEmit` |
| Итоговая desktop browser-регрессия | passed | 31/31 на fresh QA DB,3.5min,exit0; `e2e-final.log`, `e2e-final/`. Все6ролей, assignment, planning, auth, settings, readonly director |
| Executor → engineer → director, live390 | passed | Финальный1/1,14.7s на свежей QA DB/source c5d4c65; innerWidth390 всех3ролей; выполнение/фото/возврат/новая попытка/приёмка/история/оригинал/readonly. Raw ISO исключён, ракурс «Спереди» проверен; `e2e-mobile-final.log`, `e2e-mobile-final/checkpoints.jsonl` |
| Финальная production-сборка | passed | `build-final.log`, tsc+Vite. Сохраняется предупреждение размера общего bundle; лимит не повышался |
| Screen reader, реальная экранная клавиатура ОС | blocked | В доступном headless Chromium нет поддержанного ручного окружения этих проверок; Tab/Enter/Escape не подменяют их |
| Контраст выборки активного текста/полей/focus | passed | 30 состояний4anchors и2photo modal; checklist7.35:1, placeholder7.90:1, instruction border3.89:1 после исправлений. [Метод и evidence](CONTRACT_AUDIT.md) |
| Полный аудит контраста всех hover/focus/disabled/overlay | blocked | Group opacity/image backgrounds и полный набор состояний не покрыты поддерживаемым вычислением; narrow sampling не является WCAG audit |
| Исторические задания :8000 без equipment relation | blocked | Исправлен seed новых заданий; старые записи не изменялись. Назначение на них честно блокируется |
| Реальный cloud AI / customer приёмка | blocked | Полный локальный Python/ML suite прошёл; реальные внешние модели и неутверждённые customer-нормативы не подменялись синтетикой. Browser E2E проверяет guardrails на явно тестовых данных |

Ранний общий E2E: 30 passed / 1 failed — прежний тест пытался заполнить свёрнутую секцию. Исправлена последовательность пользовательских действий теста, обязательность полей не ослаблялась; повтор settings 2/2 passed. Ранний unit: 432 passed / 1 failed по 5s timeout обхода большой календарной DOM; оптимизированы selectors проверки прав, полный role-suite 112 passed. Это история обнаруженных дефектов, не результат финального gate.

Полный433unit прогон предшествовал последним цветовым/историческим presentation-правкам; после них выполнены6целевых readonly/presentation unit, production build и реальный mobile E2E. Полный desktop31 прогон не повторялся ради цвета и текста истории; изменённый потребитель повторён мобильным сценарием. Артефакты старых неготовых checkpoint PNG не являются финальными: актуальный список только в `e2e-mobile-final/checkpoints.jsonl`.

Первый полный Python run:712passed/1failed/14skipped. Persistence требует отдельную пустую БД — предоставлена при повторе. Существующий тест unavailable photo review выбирал произвольную первую запись анализа отчёта, хотя submit уже создал auto-review. Выборка уточнена по ID результата проверяемого POST, добавлена проверка canonical.ai_review_id; исходные assertions сохранены. Targeted воспроизведение failure и6passed после исправления сохранены рядом с финальным727passed. Backend/ML поведение ради теста не изменялось.

## Неизменяемые контракты

`deadlineBreached` означает приёмку после срока и не переопределён как текущая просрочка. Нормативный срок, плановый интервал, фактическое выполнение и приёмка показываются отдельно. CSV/XLSX сохраняют прежний серверный scope; пагинация реестра применяется только к полному загруженному набору. AI не заполняет основание решения и не принимает работу; ограничения и неопределённость доступны до подробного разбора.

DTO акта не содержит сохранённого основания проверки: интерфейс не выдумывает его. Причина итогового решения и вводимое основание проверки акта остаются разными полями. Существующие блокировки смены при назначениях без точного времени сохранены (409); тест использует нового работника без таких назначений.

## Воспроизведение

Из `frontend`: `npm.cmd test -- --maxWorkers=1`, `npm.cmd run build`; TypeScript тестов: `node node_modules/typescript/bin/tsc -p ../tests/web/tsconfig.json --noEmit`. Отдельного lint script нет.

Для изолированного браузерного окружения: `powershell -ExecutionPolicy Bypass -File scripts/redesign_qa_start.ps1`, затем `powershell -ExecutionPolicy Bypass -File scripts/redesign_qa_browser.ps1`. Нужны Docker, PostgreSQL image и локальный Python 3.12 image `fixrate-ai:notice-copy`. `redesign_qa_reset.ps1` пересоздаёт только именованную QA-среду, отказывает для неизвестного destination. Не запускать mutating E2E против :8000.

Для отдельного mobile flow добавить `-Mobile` к browser runner. После проверки `redesign_qa_stop.ps1` удаляет только собственные QA контейнеры/сети и приватный state. При передаче обе изолированные PostgreSQL-среды и Vite5174 остановлены, QA credentials удалены; исходный :8000 остаётся рабочим.
