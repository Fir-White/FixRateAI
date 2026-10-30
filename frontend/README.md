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
