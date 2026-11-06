# Контракты C00, C17 и семантика C02

Исходная версия: `frontend_polished`, `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Аудит 06.11.2026. Этот документ фиксирует исследование исходников и отдельные проверки, а не прохождение C16. Исходный архив и `evidence/` не изменяются. Правила размещения описаны в [разработке](../service/development.md), текущая архитектура — в [ARCHITECTURE](../ARCHITECTURE.md).

## C17: причина отсутствия оборудования

В [presentation.py](../../backend/app/integration/presentation.py) вложенная `create_work` создавала `work_orders`, назначения, отчёты и решения, но не создавала `work_order_equipment`. Связь известна seed точно: `settings[code]` содержит конкретное оборудование соответствующей `rule_equipment`, а не результат поиска по названию.

Детерминированное вычисление `uuid5(NAMESPACE_URL, 'fixrate:presentation:v1:' + key)` подтверждает все пять архивных IDs:

| Архивное задание | Ключ seed | Оборудование seed |
|---|---|---|
| `88cf6240-48a0-55a9-ba29-1bbd75a6af85` | `month-2026-11-1.1-2026-11-06` | `identity('point')` |
| `a9431cd0-48a5-55e7-a98e-61f63619930c` | `month-2026-11-1.2-2026-11-06` | `identity('point')` |
| `c1285cfc-b3fc-5891-bf7c-bc69f9f6a5ee` | `month-2026-11-1.3-2026-11-05` | `identity('controller')` |
| `e856be90-077a-5b50-ae78-885a40b80ae1` | `month-2026-11-1.5-2026-11-06` | `identity('gauge')` |
| `2629e873-6c95-5678-8a4d-32e9e53924c0` | `history-1.1-0` | `identity('point')` |

Трасса: storage `work_order_equipment` → [Views.task_view](../../backend/app/integration/projections.py) → `{equipmentId, equipmentName}` → [maintenanceApi](../../frontend/src/shared/api/maintenance.ts) → TaskTable/TaskLine/TaskDetail. Клиент получает DTO непосредственно, отдельного теряющего связь mapper нет. При пустом relation сервер намеренно выдаёт `null` и «Не указано». [assignment._job](../../backend/app/integration/assignment.py) использует ту же таблицу и возвращает `EQUIPMENT_CONTEXT_INVALID`, если связей не ровно одна. Executor visibility паспорта также строится по этой таблице; её отсутствие объясняет пустой реестр оборудования исполнителя. Календарь получает identity через rule binding, поэтому его подписи сами по себе не подтверждают relation задания.

Минимальный патч добавляет relation только при создании **нового** presentation order. Ранний возврат существующего заказа сохранён: повторный seed не восстанавливает исторические отсутствующие связи и не изменяет принятые работы. Производственный стенд не изменялся. Для существующего стенда остаётся отдельная задача контролируемого восстановления после проверки конкретных сохранённых binding/snapshot; массовая миграция и эвристика по названию здесь не выполняются.

[Регрессионный тест](../../tests/backend/test_presentation_equipment.py) проверяет точные ID в list/detail, доступ executor к паспорту, отказ чужому заданию, исчезновение именно equipment blocker у нового draft и сохранение намеренно отсутствующей исторической связи после повторного seed. Используется disposable PostgreSQL, не рабочая БД.

## Карта маршрутов и прав

[Router](../../frontend/src/app/router.tsx) связывает `/executor` и `/executor/tasks/:taskId` с исполнительскими страницами; `/engineer`, `/quality`, `/quality/:taskId` с проверкой; `/director`, `/chief-engineer`, `/dispatcher`, `/admin` используют DispatcherPage с ролью; `/tasks`, `/equipment`, `/calendar`, `/reports`, `/comparisons` — общие чтения; `/settings/equipment` и `/settings/workforce` — настройки. `/profile` защищён от редизайна. `/login`, `/register`, unknown route имеют собственные страницы.

UI capability-источник — [roles.ts](../../frontend/src/shared/lib/roles.ts). Серверная иерархия [has_role](../../backend/app/security/sessions.py): chief включает engineer и dispatcher; engineer включает dispatcher; admin не получает автоматически операционные полномочия. Director получает серверный запрет любой обычной мутации; исключения относятся только к своему профилю, сессии и уведомлениям. Executor task lookup проверяет активное назначение и возвращает 404 для чужого задания. Все Views-выборки ограничены site principal. Отображение кнопки не заменяет эти серверные проверки.

Основной API: `/api/v1/maintenance/ui/tasks`, `/ui/tasks/{id}`, `/ui/equipment`, `/ui/calendar`, `/ui/quality`; запись `/tasks/{id}/start`, `/report`, `/photos`, `/submit`, `/review`, `/assign`, `/assignment-preview`. CSRF обязателен для мутаций. Expected revision сверяется сервером, конфликт возвращает 409. Директор не получает доступ к ним через общий task detail.

## Попытки и решения

[main.py](../../backend/app/main.py) разрешает start только assigned/rework, создаёт новую `work_reports.revision_no=max+1`, сохраняя прежние отчёты. Изменять можно лишь последнюю draft-попытку собственного авторства при in_progress. Приёмка проверяет текущую submitted-попытку и запрещает свою работу. Непустой `reason` обязателен для обеих веток. Документ проверяется отдельно; его основание не заменяет reason решения. При принятии `completed_at` берётся из `execution_context.performed_at`, при отсутствии — из submitted_at, а не reviewed_at. Решение сохраняет performed_at в `decision_context`.

## C02: точные значения

| Поле / подпись | Действующий источник | Безопасное представление |
|---|---|---|
| `state` | mapping in_review→submitted, rework→rework_required, completed→accepted, clarification→draft | Отдельный процесс; неизвестное значение нейтрально с исходным кодом |
| `isOverdue` | deadline < now и order не completed/cancelled | Самостоятельный badge «Просрочено» |
| `deadlineBreached` | существует accepted review, reviewed_at > deadline | «Приёмка после срока», false — «Не зафиксирована»; формулу не менять |
| `mandatoryDueDate` | persisted regulatory_deadline_on; затем snapshot earliest_date; затем deadline в зоне объекта | Календарная дата без сдвига UTC |
| `scheduledStart/End` | planned timestamps в зоне объекта | «Плановое начало/окончание» или интервал |
| `performedAt` | decision context actual performed_at либо order.completed_at | Фактическое выполнение, отдельно от приёмки |
| `acceptedAt` | review.reviewed_at | Дата приёмки |
| `person_hour` | persisted norm unit | «чел.-ч», без умножения на бригаду |
| `elapsed_hour` | persisted norm unit | «ч», не смешивать с человеко-часами |

Просроченное rework и false deadlineBreached совместимы: ещё нет поздней принятой проверки. Это не основание пересчитать поле в UI.

[analyst.py](../../backend/app/integration/analyst.py) считает SLA по времени **приёмки**: числитель accepted reviews до deadline, знаменатель accepted reviews с deadline. `accepted` — число reviews, `jobs` — work_orders, `actualReports` и `actualPersonHours` — все отчёты с submitted_at и сохранёнными человеко-часами, включая повторные. Эти множества не взаимозаменяемы. Planned norm переводит elapsed_hour в person-hours умножением на required_people; person_hour повторно не умножает. Редизайн не меняет определения.

[format.ts](../../frontend/src/shared/lib/format.ts) обрабатывает date-only через UTC date и UTC formatter, сохраняя календарный день. Timestamp consumers TaskDetail, QualityTask, TaskTable используют [useSiteDateTime](../../frontend/src/shared/lib/useSiteDateTime.ts) с profile.timezone. Отдельный риск baseline: ExecutionProtocol преобразует datetime-local через зону браузера, а не явно через зону объекта; исправление требует отдельной проверки ввода/сохранения, не замены подписи.

Локальные consumers raw единиц: ExecutionProtocol, EquipmentOperations, MonthlyMatrix в [AnalystPanels](../../frontend/src/features/analyst/AnalystPanels.tsx). TaskTable выводит scheduledEnd под неоднозначным «План». EvidenceGallery оставляет `front`, PhotoReviewCard — `before/after` в readingComparison. Known-values можно локализовать, unknown/raw сохранять как provenance.

`after_accepted_completion` остаётся enum: [calendar](../../backend/app/integration/calendar.py) передаёт performed_at и accepted_at отдельно, [generator](../../backend/app/scheduling/generator.py) отбирает принятую историю до cutoff и берёт последнюю performed_at в зоне объекта; при отсутствии подходящей истории работает исходный anchor. Никакая будущая плановая запись не становится фактом.

## Проверки и границы

| Проверка | Статус | Результат |
|---|---|---|
| UUID source trace пяти C17 records | passed | Точное совпадение uuid5, без поиска по названию |
| Source trace relation→DTO→UI/assignment | passed | Пропуск найден в seed; DTO/client relation не теряют |
| PG18 disposable fresh migrations 001–010 | passed | Отдельный loopback cluster, рабочая БД не использована |
| Первый C17 pytest | blocked | Python 3.11 collection: baseline PEP701 f-string в analyst.py:136; тест ещё не исполнялся |
| C17 pytest в изолированном Docker Python 3.12 / PG18 | passed | 1 passed, 10.15s; пять identity, list/detail, executor passport и 404, historical null/rerun; временная БД и сеть удалены |
| Существующий стенд: repair relations | blocked | Автоматическое исправление истории не выполняется |
| C17 живое сравнение пяти IDs между ролями | blocked | Source trace не заменяет API проверку текущего стенда |

Локальные артефакты targeted запуска: `reports/redesign-v2/c17-pytest.log`, `c17-postgres.log`. `.venv` корневого checkout не содержит sqlalchemy; установленный system Python 3.11 содержит backend dependencies. Python 3.14 установлен без этих зависимостей. Исходный код требует Python 3.12+ синтаксис в одной XLSX-функции; это ограничение первого запуска, не ошибка нового relation patch.
