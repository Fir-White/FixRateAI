# Изолированный red-team аудит агента, 15–16.11.2026

База f817875; кодовый checkpoint fe39fb7; ветка audit/agent-red-team-20261115 в отдельном локальном shared-клоне/worktree. Original kran_dev, рабочий сайт, production БД/фото/роли не изменяются. Push/merge/замены исходного сайта нет. Позже по запросу владельца поднят изолированный локальный preview на localhost:8010; current frontend пересобран и чат проверен настоящим браузером. [Итоговый отчёт](../agent-audit/final-report.md), [81 изменённый файл](../agent-audit/changed-files.md), [матрица требований](../agent-audit/requirements-matrix.md), [метрики](../agent-audit/agent-quality-metrics.md).

## Изменения

- AG-001…005: личный чат директора, полные evidence/scope/cohort/server dates, ограниченная безопасная GET-коррекция и native object wire. Strict backend validation и separate approval сохранены.
- AG-006…010: целая locked бригада и порядок, точное чтение кода/регламентов актива, unknown нормы/coordinate-aware Excel и digest свободных trace строк.
- AG-011…015: серверные derived fields/ресурс/таймер, uncertainty/fallback/snapshot, null неизвестной нормы пустого периода, PATCH omission через двойную validation.
- AG-016…018: error не становится empty, native helper envelope, сохранение employment dates/merged range, typed read-only vision без ложного объявления записи/приёмки.
- AG-019…021: read-then-change не обрывается ранним отчётом; current_only inventory; UUID не становится bare code; native registry tool-mode/history, источник literal/revision; bounded fully-specified proposal после model hesitation. Это подготовка карточки, не автоматическое выполнение.
- Дополнительно: raw membership/account flags сохраняются при role-only update, проверяются остальные SQL-поля целиком. Wrong target/tool/extra поля, conditional/missing команды не превращаются в выдуманное действие.

Новые optional query cohort/asset_code/current_only сопровождаются фактическими OpenAPI-схемами; capability coverage 167, необслуженных пользовательских API нет. Staff read/list добавляют membership_is_active/account_is_active с сохранением прежнего effective is_active. Public/cloud AgentStep не меняется. Новых миграций/правок frontend нет. Версии forecast policy/method и placement-candidates-v3 маркируют новое происхождение; прежние записи не переписываются.

## Проверки и ограничения

Профильный C5: 220 passed / 186,11 с, все стадии native verify пройдены. Точный исходный inventory запрос: 1 passed / 9,06 с, реальные API/PostgreSQL и независимое SQL-сравнение, 0 inference (детерминированный путь). Общая frozen backend/ML регрессия: 2189 passed/41 opt-in skipped/1 strict xfailed за 972,35 с; первый полный live-only раунд 41 passed/595,70 с, source_stable=true. Второй прерван после 26 episode JSON; он не выдаётся за полный. Дополнительные результаты — в [итоговом отчёте](../agent-audit/final-report.md).

619 distinct MCP/schema/negative cases не выдаются за 619 LLM диалогов. Live корпус: 29 эпизодов (8 mutation), плюс 12 настоящих typed production/CP-SAT workflows, которые не являются свободным генеративным планированием. Scripted provider/fault помечены отдельно; положительные доменные результаты настоящие. Original XLSX прочитаны локально без изменения/отправки модели; live использует synthetic XLSX/PNG и pinned localhost Ollama qwen3.5:4b-q4_K_M.

Повторные C3/C4 раунды выявляли дефекты после первого зелёного; красные протоколы сохранены, качество не объявлено стопроцентным. Четыре прежних xfail стали обычными проходящими проверками с исходными бизнес-ожиданиями; конфликт demo/unknown (BUG05/ENV-003) остаётся строгим xfail. Legacy upgrade ENV-001, неподдержанный what-if, multi-site solve, unknown реальные нормы и полная положительная проверка всех 167 возможностей не закрыты. Полный frontend/mobile аудит не выполнялся; local preview login/chat desktop/mobile проверены отдельно реальным браузером. Журнал: [verification](../service/verification.md), [autonomous-progress](../agent-audit/autonomous-progress.md).