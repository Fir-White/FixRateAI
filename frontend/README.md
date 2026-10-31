# Frontend в dev

React/TypeScript/Vite/Tailwind SPA из front/mvidy. Сохранены дизайн-система, экранные компоненты, маршруты и исходные UI тесты.

Обычная сборка обращается к настоящему same-origin `/api`: серверные сессии, чтение БД, выполнение/фото/сдача/приёмка и ML. Полный запуск — [SYSTEM_OVERVIEW](../docs/SYSTEM_OVERVIEW.md).

```powershell
npm ci
npm run dev
npm run build
npm test
```

Dev сервер: 5173, API proxy: 8000. Для одной собранной системы выполните build и запускайте backend из корня: он раздаёт SPA вместе с API. Статика монтируется при startup; после первой сборки перезапустите backend.

`VITE_DEMO_MODE=true` создаёт явно обозначенный fixture-only режим с выбором роли; мутации в нём не являются настоящей работой приложения. По умолчанию флаг false. Vitest проверяет исходные экраны на fixtures и production HTTP transport отдельно; Playwright проверяет настоящий backend/БД из `scripts/verify.py --browser`.

[Карта экранов](../docs/ui/screen-map.md), [UI kit](../docs/ui/ui-kit.md), [карта переноса](../docs/branches/front--mvidy.md). Скрытие кнопки не заменяет серверный контроль доступа. Disabled кнопки редакторов/назначений отмечают ещё не реализованные сервисы.
