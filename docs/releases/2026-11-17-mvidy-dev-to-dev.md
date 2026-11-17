# Слияние mvidy_dev в dev — 17.11.2026

По запросу владельца выполнен `git pull --ff-only origin dev`: опубликованная база `33d696b03e0f27d8f3e3c75069773e091ff3712b` уже актуальна. Из указанного репозитория `https://github.com/Fir-White/FixRateAI.git` получена `mvidy_dev` с вершиной `7cd729f2a1af39cfce43d505676947609e00444e`. У настроенного `origin` (`krangras/FixRateAI`) обе ветки при проверке имели те же SHA. Общий предок совпадает с исходным dev; обычный merge с двумя родителями прошёл без конфликтов.

Сохраняются три исходных коммита: `da68d48`, `768f5cf`, `7cd729f`. Семь входящих файлов содержат серверный адаптер `task_assign` через чтение заданий и `assignment_prepare`, защиту от повторения HTTP 400/403/404/422, обработку `needs_input`, отдельный адаптер и читаемый вывод `tasks_find`, сводку результата и ссылку на задание в `ActionCard`, объединение system-сообщений для строгих шаблонов Ollama Qwen3.5 и три теста адаптеров. Запись остаётся за существующим подтверждением и серверной проверкой.

Новых маршрутов, миграций и изменений публичных DTO нет. Runtime-код и тесты объединённого дерева побайтно совпадают с `mvidy_dev`; интеграция не исправляет поведение входящей ветки. Дополнительно обновлён генерируемый `contracts/assistant-acceptance.json`: только списки `candidate_test_mentions` трёх операций. Каталог, cells, evidence и summary неизменны; новые положительные результаты приёмки не добавлялись.

## Пользовательский сценарий

Инженер открывает личный чат и первым действием запрашивает ближайшие ТО либо назначение исполнителя. После подготовки проверяет параметры карточки и подтверждает изменение; после успеха читает сводку и открывает задание по ссылке. Техник читает доступные ему задания в своём контексте. Подтверждения, исходные параметры и серверные права сохраняются. Отказы сценариев выбора задания перечислены ниже; этот merge не объявляет их принятыми.

## Фактические проверки

| Проверка на объединённом дереве | Результат |
|---|---|
| Backend: domain adapters, orchestrator, fact presenter, assignment end-to-end, capabilities; отдельный PostgreSQL 18 | **95 passed / 3 failed**, 36,73 с pytest; runner exit1 |
| Ollama chat и agent grammar, HTTP-фикстуры без настоящей генерации | **58 passed**, 15,22 с |
| Assistant UI и AssistantPage | **85 passed**, 9 файлов, 21,37 с |
| TypeScript и production Vite build | PASS; Vite 3,68 с, начальный JS 123,76 kB gzip при бюджете 150 KiB |
| Production Chrome: сохранённая история, текст/факты, 1440/390 px, обычный/reduced motion | **8 passed**, 31,4 с |
| `assistant_capabilities.py` | PASS, 173 инструмента, неучтённых пользовательских маршрутов нет |
| `assistant_acceptance_matrix.py` после штатной генерации | PASS согласованности; 708 клеток, исторические 17 positive PASS / 691 NOT_RUN |

Три падения в `tests/backend/test_assistant_capabilities.py`:

- `test_chat_lists_real_task_ids_after_missing_task_parameter`: ожидался `partial`, получен `blocked`.
- `test_selection_by_number_checks_required_crew_without_guessing`: ожидался `partial` без actions, получен `awaiting_confirmation`.
- `test_deleted_selected_task_returns_honest_error_without_model_guessing`: ожидался `blocked` без actions, получен `awaiting_confirmation`.

Assertions сохранены. Выбор по номеру, требуемый состав и отказ для удалённого задания требуют исправления и повторной проверки перед приёмкой назначения. Отдельный сравнительный прогон этих трёх тестов на исходной базе не выполнялся.

Первый объединённый backend/ML runner остановился при collection: системному Python не хватает `joblib`. Backend повторно запущен отдельно. Прямой ML-прогон в старом `.venv` дал 57 passed / 1 failed из-за отсутствующего `fastapi`. Итоговые 58 ML-тестов запущены системным Python 3.11 с добавлением совместимого `.venv/Lib/site-packages` в конец `sys.path`, без установки пакетов и изменения окружения проекта. Исходные неуспешные запуски не считаются зелёными.

Evidence рабочего дерева dev: `reports/verification/verify-20261117-223401-08d03242`, `reports/verification/verify-20261117-223544-ecc3a79e` и соответствующие `logs/verification`. Backend использовал временную БД, штатные migrations/seed и HTTP TEST-провайдеры. Browser-тесты работали на production preview с API-фикстурами: это не настоящий backend/LLM E2E, физический touch или новый профиль времени рендера ActionCard. Полный frontend/ML suite не запускался; прежние открытые отказы и release gates сохраняются.

Слияние выполняется в отдельном чистом worktree dev. Незакоммиченные документы и дизайн-файлы исходного `kran_dev` не включены. Merge, публикация dev и production-приёмка — отдельные действия; этот протокол не объявляет выпуск или развёртывание.
