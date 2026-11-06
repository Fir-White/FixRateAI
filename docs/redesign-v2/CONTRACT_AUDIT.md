# Контракты C00, C17 и семантика C02

Исходная версия: `frontend_polished`, `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Аудит 06.11.2026. Этот документ фиксирует исследование исходников и отдельные проверки, а не прохождение C16. Исходный архив и `evidence/` не изменяются. Правила размещения описаны в [разработке](../service/development.md), текущая архитектура — в [ARCHITECTURE](../ARCHITECTURE.md).

## C17: причина отсутствия оборудования

Обновление07.11.2026: владелец отдельно разрешил подготовить оборудование для демонстрации с существующими заданиями. Выполнено контролируемое восстановление117missing relations по сохранённым binding/rule IDs, без переписывания фактов. Создан backup,117audit events, preview повторно missing0;4роли подтверждают паспорта/историю/связи, engineer assignment-context200. [Операция и доказательства](IMPLEMENTATION_LOG.md). Следующий исходный аудит описывает предыдущее состояние; исторический blocker теперь устранён на текущем локальном стенде.

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

### C16: полный backend + ML и проверка найденного падения

Первый полный `pytest tests/backend tests/ml`: **failed**, 712 passed / 1 failed / 14 skipped, 142.32s; лог `reports/redesign-v2/c16-python-full-before-fix.log`. Skips относятся к persistence: тесту нужна отдельная пустая `TEST_DATABASE_URL`, а runtime использует уже migrated/seeded `INTEGRATION_DATABASE_URL`. Отдельная пустая БД предоставлена, весь persistence файл: **passed**, 15 tests, 1.82s (`c16-python-persistence.log`).

Единственное падение — `test_real_cv_adapter_with_missing_local_weights_returns_persisted_unavailable`: HTTP возвращал корректный `unavailable / MODEL_NOT_READY`, но SQL теста выбирал произвольную первую запись по `work_report_id`. До явного POST submission уже создал automatic review (`uncertain`), поэтому assertion проверял чужую запись. Неизменённый тест воспроизведён отдельно на новой БД: **failed**, 9.46s (`c16-python-ml-rerun.log`). Сравнение с baseline `422eacf` показывает: backend/ML и эти fixtures/test идентичны, кроме пяти строк независимого presentation seed; это не изменение модели/сохранения от frontend redesign.

Исправлен только тест: SELECT дополнительно ограничен `ai_quality_check_id=response.id`; добавлено совпадение `canonical.ai_review_id` с ID ответа. Исходные assertions статуса, пустых item_results, model_ref и состояния задания сохранены. Полный файл ML endpoints после исправления: **passed**, 6 tests, 10.62s (`c16-python-ml-fixed.log`). Ответы провайдера не подменялись, серверный код не менялся.

Финальный полный повтор: **passed — 727 tests, 0 failed, 0 skipped, 122.30s**, один third-party Starlette/httpx deprecation warning. Использованы две новые БД (runtime и пустая persistence) в одном собственном tmpfs PostgreSQL18; Python3.12 image, internal network, source read-only, cloud API keys пусты. Лог полного повтора: `reports/redesign-v2/c16-python-full.log`; runner: `run-python-full-docker.py`. После завершения собственные контейнер БД и сеть удалены, рабочая БД не изменялась. Это реальный backend/ML suite, не замена браузерному C16 gate.

### C14: фактический контраст computed styles

Read-only Chrome на `:5174`, 1440×900, четыре живых anchor: executor/engineer `e856be90-077a-5b50-ae78-885a40b80ae1`, chief — существующее обслуживание в открытом редакторе, director `/director`. Скрипт `reports/redesign-v2/measure-contrast.mjs`, результат `contrast-computed.json`. Отдельно реально открыты photo modal исполнителя и инженера. Измерены default, hover и keyboard-focus доступных первых пяти controls (видимые); всего 30 снимков DOM-состояния. Форма не отправлялась, серверные данные не изменялись.

Метод: браузер вычисляет CSS, canvas нормализует RGB/OKLab, alpha цвета текста и цепочка полупрозрачных фонов композируются до непрозрачного фона; relative luminance/ratio вычисляются по sRGB. Placeholder получает собственный `::placeholder` style. Порог обычного текста 4.5, крупного 3; границы controls и focus screening 3. Поля с group opacity/background-image помечены `blocked`: их приблизительные ratios нельзя использовать как passed. Disabled явно выделены и не оцениваются как активный текст.

| Измерение | Статус | Фактическое покрытие |
|---|---|---|
| ChecklistSummary метаданные инженера | passed | Найдено 4.30:1; после исправления владельцем `text-muted/70` → `text-muted` реально 7.35:1 |
| Default обычный активный текст без неподдерживаемого композитинга | passed | Executor минимум 7.35; chief 7.35; director 5.41. Engineer исключение placeholder вынесено отдельно |
| Placeholder основания решения | failed | В первоначальном измерении 3.58:1; результат отправлен владельцу для scoped исправления |
| Placeholder после scoped исправления | passed | Реальный повтор: `--fr2-muted`, opacity 1, 7.90:1; все 30 sampled states повторены, активных text ratios ниже порога в поддерживаемой выборке нет |
| Input/select/textarea borders | passed | Измеренные обычные input borders 3.62–3.89:1; legacy поле «Инструкция» сначала 1.43, после scoped исправления владельцем повторно 3.89 |
| Keyboard focus | passed | 12 sampled controls: solid outline 2–3px, 11.53–16.39:1; hover alone не ошибочно выдаётся за keyboard focus |
| Photo modals executor/engineer | passed | Реальные открытые overlays; измеренный активный текст без новых низких ratios; underlying-page placeholder учитывается отдельно |
| Disabled/group opacity, изображение под overlay-подписью | blocked | Сложное group compositing не покрыто; эти значения исключены из passed |
| Все виды control boundary | blocked | Borders кнопок 1–2.18 требуют проверки совместно с fill/icon: одна граница не является достаточным основанием для WCAG failure/pass |

Это ограниченное измерение текущих ролевых состояний, **не полный WCAG-аудит**. Не покрыты все controls, pseudo-icons/SVG stroke, error/conflict состояния, focus всех overlay controls, полнота контраста при mobile/zoom, все снимки изображений, анимация. Регрессионное измерение после последнего исправления должно иметь отдельную строку результата; исходный дефект не скрывается.

Архив измерений: `reports/redesign-v2/contrast-before-placeholder-fix.json` (исходный placeholder 3.58 и border «Инструкция» 1.43), `contrast-after-fixes.json` (повтор после всех трёх исправлений). `contrast-computed.json` содержит тот же последний прогон. Первоначальный ChecklistSummary 4.30 зафиксирован выше и в рабочем журнале; отдельного первоначального JSON до его исправления не сохранилось, не выдаём новый JSON за старый.

### C15: полный визуальный просмотр обзора директора

Лично просмотрены все последовательные viewport tiles в `reports/redesign-v2/after-final-shared/`: `director-home-1440-y{0,800,1037}.png`, `director-anchor-1440-y{0,800,1017}.png`, `director-anchor-390-y{0,744,1488,2232,2740}.png`. Все 11 изображений просмотрены целиком; для каждой из трёх серий статус **FULL**, результат **passed** с замечаниями ниже. Это `/director` с раскрытым/свёрнутым sidebar и mobile; отдельной серии `director-home-390` нет, её нельзя заявлять просмотренной. Верх/середина/конец покрыты с overlap; конец страницы виден, повторов начала длинного PNG нет. `director-errors.json` пуст.

Сравнение: `reports/redesign-v2/before/director-home-1440-y0.png` и `director-anchor-390-y0.png` (исходный верх), [desktop concept](source/FixRateAI-phase2-visual-design-2026-11-06/concepts/director-desktop.png), [mobile concept](source/FixRateAI-phase2-visual-design-2026-11-06/concepts/director-mobile.png). В baseline экспорт/аналитика занимали верх до заголовка; теперь роль, заголовок, компактные метрики и просроченная работа читаются первыми. Концепты — композиционный ориентир, не live доказательство.

| Критерий Phase II | Наблюдение по FULL сериям |
|---|---|
| composition | Ясный центр исключений; desktop rail 336px с результатами/AI; mobile один поток. Реальный журнал дня сохранён. |
| typography | Заголовок отделён от eyebrow, числа метрик крупные, длинные названия строк переносятся; вторичные данные компактны. |
| information_hierarchy | H1 и 4 метрики перед исключениями; первая просрочка видна в первом mobile viewport. Даты плана и обязательный срок подписаны раздельно. |
| color_system | Графит/мята и спокойные разделители сохранены; просрочка выделена красным отдельно от процессного статуса. |
| component_quality | Метрики единая поверхность, списки строками; статусы/ссылки не перекрываются. Раскрытие экспорта не раздувает начальный экран. |
| information_density | Desktop плотный без лишних карточек. Mobile шесть строк дня удлиняют путь к принятым результатам примерно до y2750 — остаточное отличие от более короткого концепта. |
| consistency | Метрики, отступы, подписи статусов и scoped поверхности согласованы; защищённая оболочка визуально соответствует исходному верхнему снимку. Это не pixel-diff всего shell. |
| mobile_adaptation | 390px: метрики 2×2, строки переносятся, дни недели помещаются, bottom ссылки доступны; sticky shell не скрывает конец содержимого. |
| professional_finish | Нет обрезанных названий/необоснованных пустых блоков; AI явно «Нет результата» с причиной и raw раскрытием. Историческое «Не указано» остаётся честным ограничением данных C17. |

Критерии являются экспертным визуальным заключением, не WCAG-сертификатом или количественным usability score. Новые баллы не подменяют исторический `visual-scores.csv`. Проверка скрытых loading/error/overlay в этих сериях не выполнялась.

Граница C16 директора: эти FULL серии подтверждают **только live read-only отображение обзора**, а `owned-pages` — непосредственное открытие результата/отчёта/паспорта. Они не доказывают единый click-through «обзор → проблемный объект → история → фото/документ → решение». `roles.spec.ts` проверяет реальные вход, маршруты, доступность ссылок и GET фото при их наличии, однако отдельный результат полного директорского сценария здесь не получен. Поэтому такой E2E остаётся **blocked в этом протоколе** до отдельного подтверждения владельцем C16; backend RBAC и attempt contracts подтверждены перечисленными ниже 258 тестами.

### Контрольный срез C06/C07/C09/C11/C19 и backend C16

Реализованы контекст назначения и подтверждение выбранного состава/интервала, сохранение ввода при неопределённом сетевом результате, явный equipment blocker, ролевой обзор с исключениями перед журналом, read-only протокол директора и история внизу. Реестр получил локальную пагинацию по 25 строк с поиском по всей загруженной выборке; отчёт показывает первые 10 записей со ссылкой на полный реестр, экспорт сохраняет прежний набор. Паспорт отделяет справочную операцию от связанных версий обслуживания. C19 меняет пояснения доступа и анонимную ссылку 404; геометрия и логотип auth сохранены.

| Проверка | Статус | Результат |
|---|---|---|
| TypeScript после интеграции | passed | Без ошибок |
| Targeted frontend role/navigation, dispatcher, task detail, assignment | passed | 127 tests, 106.56s |
| Пагинация, поиск вне текущей страницы, директор | passed | Отдельный новый тест: 1 passed |
| Изолированный backend C16 subset | passed | 258 tests, 58.91s; scheduling, roles_contracts, runtime_integration, analyst_workflows, presentation_equipment; один third-party deprecation warning |
| Реальный read-only результат/отчёт/паспорт | passed | Before :8000 / after :5174; 1440/1280/768/390/360/320; document overflow отсутствует, browser errors 0 |
| Login/register/404 | passed | Before/after 390/360/320; overflow отсутствует, browser errors 0; просмотрены login320, register360 bottom, 404320 |
| Успешное назначение на существующем live seed | blocked | Исторические связи отсутствуют; стенд не исправлялся ради проверки |
| Полный браузерный C16 gate | blocked | Этот протокол подтверждает только перечисленный subset; итог объединяется с ролевым E2E владельца C16 |

Backend прогон использовал Python 3.12 container, отдельную tmpfs PostgreSQL18, fresh migrations 001–010, изолированную сеть и read-only source mount. После результата временная БД и сеть удалены. Рабочая БД не использовалась. Команда pytest включала `tests/backend/test_presentation_equipment.py tests/backend/test_scheduling.py tests/backend/test_roles_contracts.py tests/backend/test_runtime_integration.py tests/backend/test_analyst_workflows.py`; лог: `reports/redesign-v2/c16-backend.log`.

Снимки и manifests находятся в `reports/redesign-v2/owned-pages`, `common`, `c07-c11`. Для результата просмотрены desktop top и mobile top/middle/bottom; для отчёта desktop/mobile top и mobile middle/bottom; для паспорта mobile top/bottom; для director overview desktop top/bottom. Новые region captures меньше 16384px, без склейки. Старые промежуточные PNG, отсутствующие в актуальном manifest, не являются доказательством последнего состояния. Проверка геометрии ширин автоматическая; не все снимки всех ширин просмотрены вручную. Наличие seed-значения «Не указано» сохранено честно. Auth регистрация не отправлялась и новые пользователи не создавались.

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
