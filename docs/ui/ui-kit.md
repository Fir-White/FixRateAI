> Интеграционный runtime dev описан в [SYSTEM_OVERVIEW](../SYSTEM_OVERVIEW.md). Ниже сохранён дизайн/срез frontend источника; актуальные серверные возможности и команды определяет основной документ.

# UI-kit FixRate AI

Срез: 30.10.2026. Единый интерфейс корпоративного прототипа: почти чёрный фон, глубокий зелёный свет, белая типографика и тонкие линейные иконки. Палитра и логотип повторяют утверждённый визуал FixRate AI.

## Правила

- Страницы не задают собственные цвета, размеры кнопок и формы. Используются токены и компоненты из `frontend/src/shared/ui`.
- Основной фон — `canvas`, поверхности — `surface`, границы — `line`, текст — `ink` / `ink-soft` / `muted`, акцент — `accent`.
- Цветовой акцент используется для действий, активной навигации и фокуса. Статусы используют полупрозрачные тона, а не яркие заливки.
- Один визуальный вес: `font-semibold` для заголовков, действий и меток. Не добавлять произвольные `font-black`, `shadow-*` и hex-цвета в страницы.
- Все интерактивные элементы нативные (`button`, `a`, `input`, `select`, `textarea`) и имеют видимый `focus-visible`.
- Мобильная сетка строится на `grid` с одним столбцом; таблицы прокручиваются внутри `Table`.

## Палитра

| Токен | Значение | Назначение |
|---|---|---|
| `canvas` | `#020706` | Фон приложения |
| `canvas-soft` | `#04100d` | Sidebar, мобильное меню |
| `surface` | `#07110e` | Карточки и панели |
| `surface-raised` | `#0b1814` | Наведение, вложенные поверхности |
| `line` | `#182722` | Основные границы |
| `line-strong` | `#2a4039` | Поля и активные границы |
| `ink` | `#f3f7f5` | Основной текст |
| `ink-soft` | `#b8c9c4` | Вторичный текст |
| `muted` | `#7b938b` | Подписи и служебные данные |
| `accent` | `#67e8c4` | Акцент, фокус, ссылки |
| `accent-ink` | `#03251c` | Текст на акцентной заливке |

Статусные тона: `info` — голубой, `success` — акцентный зелёный, `warning` — янтарный, `danger` — розово-красный, `violet` — фиолетовый.

## Типографика

- `text-hero`: `clamp(2.5rem, 6vw, 4.5rem)` — только входной экран.
- `text-page`: `clamp(1.75rem, 3.5vw, 2.35rem)` — заголовок страницы через `PageHeader`.
- `text-section`: `clamp(1rem, 2vw, 1.15rem)` — заголовок карточки через `CardHeader`.
- Основной текст: `text-sm leading-6`; служебные подписи: `text-xs` или `text-[10px]` с uppercase-трекингом.
- Заголовки используют `tracking-[-0.035em]`; длинные заголовки переносятся через `text-wrap: balance`.

## Отступы и радиусы

- Внешний контейнер: `px-4 py-6 sm:px-6 lg:px-8 lg:py-10`.
- Карточка: `rounded-2xl border border-line bg-surface/90`.
- Внутренние отступы: `p-5 sm:p-6`; компактные панели — `p-4`.
- Кнопки и поля: `rounded-xl`; бейджи и чипы: `rounded-md` / `rounded-lg`.
- Сетки: `gap-4` для карточек, `gap-6` между крупными блоками, `gap-2` для действий.

## Компоненты

### Layout

- `AppShell` — desktop sidebar, верхняя панель, мобильное меню, skip-link и контент.
- `ExecutorLayout` — отдельная мобильная оболочка исполнителя с нижней навигацией.

### Бренд

```tsx
import { BrandLockup, BrandMark } from "@/shared/ui/Brand";

<BrandLockup size="md" />
<BrandMark size={48} className="text-ink" />
```

### Страница и карточки

```tsx
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardBody, CardHeader, CardFooter } from "@/shared/ui/Card";

<PageHeader
  eyebrow="Планирование"
  title="Календарь ТО"
  description="Проекция вхождений по локальным суткам объекта."
  actions={<Button>Действие</Button>}
/>

<Card>
  <CardHeader title="Заголовок" description="Короткое пояснение" />
  <CardBody>Содержимое</CardBody>
  <CardFooter>Действия</CardFooter>
</Card>
```

### Кнопки

```tsx
import { Button, IconButton } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";

<Button>Основное действие</Button>
<Button variant="secondary">Второстепенное</Button>
<Button variant="danger">Опасное действие</Button>
<IconButton label="Закрыть" variant="ghost">
  <Icon name="close" size={18} />
</IconButton>
```

`buttonClassName(variant, size, className)` используется для ссылок, которые выглядят как кнопки.

### Формы

```tsx
import { FormField, Input, Select, Textarea, Checkbox } from "@/shared/ui/Form";

<FormField label="Поиск" htmlFor="search" hint="Название или номер">
  <Input id="search" leadingIcon={<Icon name="search" size={17} />} />
</FormField>

<FormField label="Состояние" htmlFor="state" required>
  <Select id="state">...</Select>
</FormField>

<Textarea aria-label="Комментарий" rows={4} />
<Checkbox label="Выполнено" checked readOnly />
```

`FormField` связывает `hint` и `error` с контролом через `aria-describedby`; при ошибке контрол получает `aria-invalid`.

### Таблицы

```tsx
import { Table, Th, Td, Tr } from "@/shared/ui/Table";

<Table label="Очередь заданий" minWidth={860}>
  <thead>
    <tr>
      <Th>Задание</Th>
      <Th>Статус</Th>
    </tr>
  </thead>
  <tbody>
    <Tr highlighted={task.isOverdue}>
      <Td>{task.title}</Td>
      <Td><TaskStateBadge state={task.state} /></Td>
    </Tr>
  </tbody>
</Table>
```

`Table` сам создаёт клавиатурно-фокусируемую область прокрутки с `aria-label`.

### Статусы, Callout и данные

```tsx
import { Badge } from "@/shared/ui/Badge";
import { TaskStateBadge, OriginBadge } from "@/shared/ui/StatusBadge";
import { Callout } from "@/shared/ui/Callout";
import { InfoList, InfoItem } from "@/shared/ui/InfoList";

<Badge tone="warning">Нужны данные</Badge>
<TaskStateBadge state="submitted" />
<OriginBadge origin="synthetic_demo" />

<Callout tone="danger" title="Просрочено.">
  Обязательный срок нарушен.
</Callout>

<InfoList className="grid gap-4 sm:grid-cols-2">
  <InfoItem label="Оборудование" value="Тепловой пункт №1" />
  <InfoItem label="Ревизия" value="3" mono />
</InfoList>
```

### Состояния

```tsx
import { LoadingState, EmptyState, ErrorState } from "@/shared/ui/States";

<LoadingState label="Загрузка заданий" />
<EmptyState title="Заданий нет" description="Измените фильтр." />
<ErrorState description={query.error} />
```

`LoadingState` показывает skeleton и `role="status"`, `ErrorState` — `role="alert"`.

### Модальное окно

```tsx
import { Modal } from "@/shared/ui/Modal";

<Modal
  open={pending}
  title="Принять работу?"
  description="Действие закроет задание."
  onClose={() => setPending(false)}
  footer={
    <>
      <Button variant="secondary" onClick={() => setPending(false)}>
        Отмена
      </Button>
      <Button onClick={confirm}>Подтвердить</Button>
    </>
  }
>
  Проверьте фотографии и заключение AI.
</Modal>
```

`Modal` переносит фокус внутрь, удерживает `Tab`, закрывается по `Escape`, возвращает фокус на инициатора и блокирует прокрутку body.

## Адаптивность

- `< 768px`: одна колонка, компактные отступы, мобильное меню в `AppShell`, нижняя навигация в `ExecutorLayout`.
- `768–1024px`: двухколоночные карточки, верхняя панель без демо-метки.
- `>= 1024px`: sidebar `18rem`, контент с `lg:pl-72`, доска календаря и таблицы.
- `>= 1280px`: расширенные обзорные сетки диспетчера и инженера.

## Доступность

- В `AppShell` и `ExecutorLayout` есть skip-link к `#main-content`.
- Мобильное меню имеет `role="dialog"`, `aria-modal`, `aria-label`, закрытие по `Escape` и focus trap.
- Мобильный контент под открытым меню получает `inert`; фокус возвращается на кнопку меню.
- У фильтров есть `aria-pressed`; у навигации — `aria-current` через `NavLink`.
- Таблицы имеют клавиатурно-фокусируемый scroll-region.
- Иконки декоративные (`aria-hidden`); icon-only кнопки обязаны иметь `label` / `aria-label`.
- Не отключать `:focus-visible`; не заменять нативные контролы на `div`.

## Чек-лист нового экрана

1. Начать с `PageHeader`, затем `Card` / `Table`.
2. Для формы использовать `FormField` + `Input` / `Select` / `Textarea`.
3. Для данных — `InfoList` или entity-компоненты.
4. Для статусов — `TaskStateBadge`, `EquipmentStateBadge` или `Badge`.
5. Для предупреждений — `Callout`, для загрузки/пустоты/ошибки — `States`.
6. Проверить мобильную сетку, клавиатурный фокус и `npm run typecheck`, `npm test`, `npm run build`.
