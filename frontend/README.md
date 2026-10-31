# FixRate AI frontend

Каркас SPA для планирования и контроля технического обслуживания.

## Стек

- React 19 + TypeScript
- Vite 6
- Tailwind CSS 4
- React Router 7
- Vitest + React Testing Library

## Запуск

```bash
npm install
npm run dev
```

Приложение откроется на `http://localhost:5173`. Запросы `/api` проксируются на `http://localhost:8000`.

Проверки:

```bash
npm run typecheck
npm run build
npm test
```

## Маршруты

Полная карта и границы страниц: [docs/ui/screen-map.md](../docs/ui/screen-map.md).

Единая палитра, типографика и инструкция по компонентам: [docs/ui/ui-kit.md](../docs/ui/ui-kit.md).

- `/login` — выбор демонстрационной роли
- `/dispatcher` — панель диспетчера
- `/equipment`, `/equipment/:equipmentId` — реестр и карточка
- `/calendar` — календарь ТО
- `/tasks`, `/tasks/:taskId` — очередь и карточка задания
- `/comparisons`, `/comparisons/:runId` — прогнозы
- `/executor`, `/executor/tasks/:taskId` — кабинет исполнителя
- `/quality`, `/quality/:taskId` — контроль качества

## Данные

Пока backend не реализует HTTP-слой, `src/shared/api/maintenance.ts` использует fixtures из `src/shared/mocks/data.ts`. Все синтетические данные помечены `synthetic_demo`.

Демонстрационная роль хранится в `localStorage` и управляет только навигацией. Серверная авторизация, RBAC, site scope, CSRF и запрет собственной приёмки должны проверяться backend.

## UI-kit

Интерфейс использует тёмную палитру FixRate AI: `canvas`, `surface`, `line`, `ink`, `muted` и `accent` из `src/index.css`. Готовые компоненты находятся в `src/shared/ui`:

- `Button`, `IconButton`, `FilterChip`
- `FormField`, `Input`, `Select`, `Textarea`, `Checkbox`
- `Card`, `PageHeader`, `Table`, `InfoList`, `Callout`
- `Badge`, статусные бейджи, `LoadingState`, `EmptyState`, `ErrorState`
- `Modal` с focus trap и закрытием по `Escape`
- `BrandMark`, `BrandLockup`

Правило: страницы не задают собственные hex-цвета, размеры кнопок и стили полей. Примеры и чек-лист нового экрана — в [UI-kit](../docs/ui/ui-kit.md).

## Структура

```text
src/
├── app/          router, guards, providers
├── layouts/      AppShell, ExecutorLayout
├── pages/        страницы маршрутов
├── entities/     таблицы и карточки домена
├── widgets/      составные блоки
└── shared/       API, типы, mocks, session, UI
```

Зависимости направлены сверху вниз: `pages` → `widgets`/`entities` → `shared`.
