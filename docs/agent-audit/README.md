# Автономный аудит AI-агента

База аудита: `f8178754433d57cf5cfeb2690eb64b2fe0207ec2`, 15.11.2026. Аудит проводился в ветке `audit/agent-red-team-20261115` отдельного Git worktree с метаданными в локальном shared-клоне. На этом этапе исходный kran_dev и его данные не менялись. По последующему запросу владельца 16.11.2026 шесть коммитов перенесены fast-forward в kran_dev; перенос зафиксирован коммитом b2546ad. Audit-worktree сохранён отдельно, исходная база остаётся доступной в истории. [Протокол переноса](../service/verification.md), [срез и ограничения](final-report.md).

Пути `reports/`, `logs/` и `var/` в доказательствах ниже относятся к audit-worktree `var/agent-red-team-20261115/worktree` относительно исходного integration-dev. Например, протокол полного прогона находится в `var/agent-red-team-20261115/worktree/reports/agent-audit-frozen-fe39fb7-full-provenance.json`. Приватные результаты не включены в Git и отсутствуют в новом клоне; опубликованные корпус, runner и документация позволяют повторить проверки в подготовленной среде.

Директива владельца: автономный red team именно агента, инструментов, состояния, планирования и RBAC. UI-редизайн и реальные доменные мутации не входят в проверку. Используются отдельный PostgreSQL, фиктивные пользователи и приватный test photo storage; исходные customer-файлы читаются только локально.

Docker недоступен в текущем разрешении. Повышение прав не запрашивается. Доступен PostgreSQL 18 для отдельного нативного кластера и локальная Ollama с pinned qwen3.5:4b-q4_K_M. Загрузка OR-Tools/Hypothesis в отдельный venv была отклонена сетевым sandbox (WinError 10013). Затем совместимые Windows wheels OR-Tools 9.15 и всех solver dependencies найдены в существующем pip HTTP cache и установлены **офлайн только в отдельный venv**. ML-зависимости заимствуются чтением из ранее существовавшего окружения; системная среда не изменяется, запись pyc отключена. Hypothesis недоступен; воспроизводимые seeded/metamorphic/stateful проверки используют стандартную библиотеку, а не имитируют установку Hypothesis.

Аудит начат 15.11 и продолжен 16.11.2026. Исправления AG-001…021 охватывают инструменты, достоверность аналитики, нормы, закреплённые бригады, сохранность карточек и составные команды. Повторные frozen C3/C4 прогоны выявили дополнительные ошибки после первых зелёных раундов; неуспешные результаты сохранены. Проверяемый срез C5 — fe39fb7. [Итоговый срез](final-report.md) и [изменённые файлы](changed-files.md) содержат доказательства и ограничения; это не сертификат завершения всего MVP или стопроцентной надёжности.

Воспроизводимый запуск в подготовленном Python-окружении:

```powershell
python scripts/generate_agent_redteam.py
python scripts/assistant_capabilities.py --write
python scripts/agent_redteam.py --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --live
```

Нужны зависимости проекта, requirements-solver.txt, уже установленная локальная Ollama с указанным pin и нативный PostgreSQL. Runner ничего не скачивает, не использует cloud fallback, не принимает production DATABASE_URL и не публикует результаты во внешние сервисы. Без --live модельные тесты явно skipped. --rounds 1…10 задаёт ограниченное число раундов; при ошибке сохраняется красный результат, автоматического перезапуска до зелёного нет. Каждый раунд записывает HEAD и хеши исходников; изменение кода во время прогона делает его непригодным как проверку единого среза.

Обычный --agent-only создаёт текущую схему и повторяет migrate/seed, но намеренно не засчитывает legacy upgrade SQL, у которого выявлен ENV-001. Никакая проверка фронтенда не заменялась или не объявлялась пройденной. Полные исходные и неуспешные трассы остаются в ignored reports/logs/var, публикуются только код, обезличенные корпуса и проверяемые агрегаты.

- [Матрица требований](requirements-matrix.md)
- [Инвентарь тестов](test-inventory.md)
- [Воспроизводимые дефекты](known-defects.md)
- [Безопасность](security-findings.md)
- [Контракты инструментов](tool-contract-audit.md)
- [Планирование](planning-evaluation.md)
- [Метрики](agent-quality-metrics.md)
- [Ход работы](autonomous-progress.md)
- [Итоговый срез и ограничения](final-report.md)

Повтор только модели и production workflows: `python scripts/agent_redteam.py --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --live --live-only --rounds 2`. Это 29 эпизодов чата и 12 typed production workflows на раунд. Широкая регрессия обязательна отдельно: `python scripts/verify.py --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --agent-only --pytest-target tests/backend tests/ml`. Opt-in live tests в ней явно skipped. Штатный live runner задаёт output/provider environment сам; ручной запуск production tests без них может упасть на пути артефактов.
