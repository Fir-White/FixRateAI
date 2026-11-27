# Локальный стенд Agent v3

[Цель](GOAL.md) · [Исходное состояние](BASELINE.md) · [Архитектура](ARCHITECTURE.md) · [План](PLAN.md) · [Прогресс](PROGRESS.md) · [Итоговый отчёт](FINAL_REPORT.md) · [Метрики](METRICS.json)

Требуются установленные зависимости проекта, PostgreSQL и локальная Ollama с загруженной моделью. Штатный runner создаёт отдельный новый кластер, применяет миграции и удаляет собственный временный кластер после проверки. Ollama используется через loopback с зафиксированным digest. Для запуска в PowerShell укажите путь к Python с зависимостями проекта и новый подкаталог в `reports`.

```powershell
$env:FIXRATE_ASSISTANT_AGENT_VERSION = 'v3'
python -B scripts/verify_agent_local.py --live --output reports/agent-reliability-v3-repeat-01 --pytest-target tests/agent_reliability_lab/evals
python -B tests/agent_reliability_lab/evals/summarize.py reports/agent-reliability-v3-repeat-01 --write
```

Для повторения конкретного случая передайте pytest node ID после `--pytest-target`. `FIXRATE_RELIABILITY_SEED` задаёт варианты генератора, исходный seed `20261123`. Параметр `--pg-bin` указывает каталог бинарных файлов PostgreSQL, если локальный путь отличается от стандартного для runner.

Отдельный набор для приёмки находится в `acceptance/test_release_holdout.py`. Укажите новый целочисленный `FIXRATE_RELIABILITY_RELEASE_SEED` перед первым прогоном. Запишите его вместе с результатом. При диагностике воспроизводите прежний seed, а для следующего независимого измерения используйте новый. `runtime/test_wire_processes.py` запускает отдельные процессы Uvicorn и проверяет подтверждение, потерю тела ответа и кратковременную недоступность тестовой БД по настоящему HTTP.

Зафиксированный релизный контроль воспроизводится с seed `384075`. Для проверки исполнения выберите другой каталог вывода. При параллельной проверке браузера и backend используйте разные копии исходников, поскольку production-сборка пересоздаёт `frontend/dist/assets`.

```powershell
$env:FIXRATE_RELIABILITY_RELEASE_SEED = '384075'
python -B scripts/verify_agent_local.py --live --output reports/agent-reliability-v3-control-repeat --pytest-target tests/agent_reliability_lab/acceptance
python -B scripts/verify_agent_local.py --live --output reports/agent-reliability-v3-runtime-repeat --pytest-target tests/agent_reliability_lab/runtime
```

Отчёты сохраняются в `reports/agent-reliability-v3-*/` и `logs/agent-reliability-v3-*/`. `provenance.json` фиксирует версии и исходники. `independent-summary.json` агрегирует сохранённые ответы, оценки, число вызовов и задержки. Развёрнутые результаты SQL-oracle сохраняются в `independent-v3`, а ответы и события всех эпизодов широкого набора — в `transcripts`. Итог всех фаз теста находится в pytest log. В прерванном прогоне доступны уже записанные эпизоды и отсутствует итоговый статус runner.
