# front/mvidy

## Назначение и версия

React SPA, дизайн-система, маршруты, все экраны и demo transport.

Зафиксированный SHA: `226f3266a29cd43121ddca2c707cdcf5d71d375c`. Статус: `integrated`. Исходная ветка не изменялась. Зависимости по компонентам описаны в [SYSTEM_OVERVIEW](../SYSTEM_OVERVIEW.md); tests требуют test-only БД, SQL/ORM — миграции, SPA — runtime API, ML — canonical DTO и подходящий artifact.

## Уже выполнено в dev

Сохранены компоненты, стили, UI kit, screen map и 18 исходных UI тестов. Production подключён к реальному API. Добавлены рабочие формы исполнения/приёмки и browser E2E.

| Исходный путь или интерфейс | Расположение или интерфейс в dev | Что изменено и почему | Что учитывать при следующих обновлениях |
|---|---|---|---|
| shared/api/maintenance.ts | frontend/src/shared/api/maintenance.ts + maintenance.demo.ts | Production fetch отделён от fixtures | Новые mock функции переносить в demo файл, не затирать fetch |
| shared/session/SessionContext.tsx | Тот же путь + api/request.ts | Cookie session/CSRF; demo role только с VITE_DEMO_MODE=true | Не доверять localStorage роли в production |
| ExecutorTaskPage.tsx; QualityTaskPage.tsx | Те же пути | Заглушки действий заменены API и revision | Сохранять попытки, freeze и обработку ошибок |
| shared/types/domain.ts; EvidenceGallery.tsx | Те же пути | Nullable неизвестные поля и настоящие авторизованные фото | Не создавать фиктивные UUID/сроки/происхождение |
| vite.config.ts; package*.json | Те же пути | Host-preserving proxy; Vitest 4.1.12; отдельный E2E | npm ci/build/tests/audit/browser |
| docs/ui/*; frontend/README.md | Те же пути | Карта и kit сохранены; runtime ссылка актуализирована | Согласовывать новые экраны с backend |

Полная машинная карта изменённых путей: [BRANCH_FILE_MAP](../BRANCH_FILE_MAP.json). В строках frontend сокращённые пути относятся к frontend/src. Если путь сохранён, дополнительных переименований для него не требуется.

## Проверки и известные несовместимости

TypeScript/Vite, исходные 18 UI tests, HTTP transport test, npm audit и browser E2E.

Фактические текущие итоги находятся в [DEV_INTEGRATION_REPORT](../DEV_INTEGRATION_REPORT.md). Проектные DTO не означают наличие всех HTTP endpoints. Общие ограничения: неподтверждённые customer даты, отсутствие customer-trained модели и оценки точности AI/CV на фотографиях заказчика. Код не исключался из-за сложности интеграции; внешняя готовность и перенос кода учитываются отдельно.

## Рекомендации для исходной ветки

Diff после 226f326 разделять между компонентами, production и demo transport. Рекомендовано выделить demo слой и nullable контракты в источнике. Переименования в источнике не выполнялись.

Это рекомендации, **не выполненные изменения источника**. Переименования и adapters выполнены только в dev. Не заменяйте исходную ветку всей dev. Там, где таблица сохраняет путь, дополнительное переименование не требуется.

## Конкретный следующий перенос

1. Возьмите `226f3266a29cd43121ddca2c707cdcf5d71d375c` из [реестра](../BRANCH_SOURCES.json), получите новый SHA после fetch.
2. Сравните только `git diff OLD_SHA NEW_SHA`, сопоставьте hunks по таблице. Не применяйте отставание источника от main как удаление компонентов.
3. Адаптируйте интерфейсы, выполните перечисленные проверки, обновите карту/реестр/отчёт и создайте обычный commit только в dev.
4. При частичном переносе перечислите pending_paths и сохраните последнюю полностью учтённую версию. Полный процесс — [BRANCH_INTEGRATION_GUIDE](../BRANCH_INTEGRATION_GUIDE.md).
