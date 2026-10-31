# feat/ml-forecasting-photo-review

## Назначение и версия

RF, condition evidence, JSON/provider boundaries и CLIP photo review.

Зафиксированный SHA: `2b8488f71ec295c94cb4874cbe9f8b324c3b0e41`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [SYSTEM_OVERVIEW](../SYSTEM_OVERVIEW.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

## Уже выполнено в dev

Все изменения 2b8488f поверх main перенесены: condition/api/backend_adapter, CV, tests, inspect_pairs, requirements-cv и документы/эксперименты. RF/артефакт уже были в main. Настоящий CLIP inference дополнительно проверен в отдельном CV профиле с pinned весами через HTTP.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| ml_service/app/forecast/* | Те же пути + backend/app/integration/ml.py | Снимок из БД и сохранение обоих результатов; condition completeness | Проверять feature schema, hash, происхождение и cutoff |
| ml_service/app/cv/* | Те же пути + HTTP photo-review | Только фото текущего scope-checked submitted отчёта | Guardrails 1.5/1.6, идентичность, сопоставимость и unavailable |
| forecast/client.py | Тот же путь | Необязательный use_active_model; модель FastAPI изолирована | Не возвращать глобальный кеш при явном отсутствии модели |
| ml_service/tests/* | Те же пути | Все тесты сохранены; namespace/importlib устраняет shadowing | Запускать совместно с backend tests |
| docs/ml/*experiment.json | Те же пути | Исторические эксперименты источника сохранены | Не выдавать их за результаты текущего inference |
| requirements-cv.txt; var/artifacts/* | Те же пути + root lock | RF SHA проверяется при startup; CV stack отдельный | Проверять sklearn совместимость и cache модели |

Полная машинная карта изменённых путей: [BRANCH_FILE_MAP](../BRANCH_FILE_MAP.json). В строках frontend сокращённые пути относятся к frontend/src. Если путь сохранён, дополнительных переименований для него не требуется.

## Проверки и известные несовместимости

RF/condition/provider/CV tests, настоящий persisted snapshot/hash/RF через HTTP и браузер. Настоящий CLIP inference подтверждён в строгом CV профиле; оценка качества на customer фото не выполнялась.

Фактические текущие итоги находятся в [DEV_INTEGRATION_REPORT](../DEV_INTEGRATION_REPORT.md). Проектные DTO не означают наличие всех HTTP endpoints. Общие ограничения: неподтверждённые customer даты, отсутствие customer-trained модели и оценки точности AI/CV на фотографиях заказчика. Код не исключался из-за сложности интеграции; внешняя готовность и перенос кода учитываются отдельно.

## Рекомендации для исходной ветки

Diff после 2b8488f переносить отдельно по forecast/CV/DTO. Импорты только ml_service.app. Дополнительные переименования не требуются; изменение модели требует нового manifest и проверки.

Это рекомендации, **не выполненные изменения источника**. Переименования и adapters выполнены только в dev. Не заменяйте исходную ветку всей dev. Там, где таблица сохраняет путь, дополнительное переименование не требуется.

## Конкретный следующий перенос

1. Возьмите `2b8488f71ec295c94cb4874cbe9f8b324c3b0e41` из [реестра](../BRANCH_SOURCES.json), получите новый SHA после fetch.
2. Сравните только `git diff OLD_SHA NEW_SHA`, сопоставьте hunks по таблице. Не применяйте отставание источника от main как удаление компонентов.
3. Адаптируйте интерфейсы, выполните перечисленные проверки, обновите карту/реестр/отчёт и создайте обычный commit только в dev.
4. При частичном переносе перечислите pending_paths и сохраните последнюю полностью учтённую версию. Полный процесс — [BRANCH_INTEGRATION_GUIDE](../BRANCH_INTEGRATION_GUIDE.md).
