# Журнал реализации редизайна v2

## Дизайн-итерация 07.11.2026: фото до/после по требованиям регламента

По запросу владельца заменена одиночная форма с пунктом/этапом/ракурсом и отдельной кнопкой загрузки. Для каждого `photoRequired` пункта текущего `execution.checklist` показаны две зоны «Прикрепите фото до» и «Прикрепите фото после». При выборе или перетаскивании одного/нескольких файлов загрузка начинается автоматически. На мобильном доступны выбор файла и снимок через системный диалог. После загрузки фотографии открываются существующим просмотрщиком с оригиналами и метаданными; дополнительная зона становится компактной.

Требования берутся из сохранённого snapshot попытки, а не из первого пункта списка. Действующий серверный контракт задаёт минимум одну пару одинакового ракурса для каждого `photoRequired` пункта, в том числе при `required=false` у ответа. Поэтому минимум равен 2 × число таких пунктов. Разные пункты/ракурсы не образуют готовую пару. Произвольного поля количества фото на пункт в текущем DTO нет; непроверенный разбор свободного текста ТЗ не добавлялся. Необязательные пункты и дополнительные ракурсы доступны в раскрываемых разделах. Все ранее сохранённые вложения остаются доступны; readonly-попытка использует прежний EvidenceComparison.

Очередь последовательно вызывает существующий `/tasks/{id}/photos`, без bulk API и перекодирования оригиналов. Перед первым фото сохраняются несохранённые ответы, комментарий и фактическое выполнение. Последняя revision передаётся следующему фото и панели документов. Фото обновляются локально без размонтирования редактора. При ошибке очередь останавливается, сохранённые файлы не отправляются повторно, остальные остаются для продолжения; ошибка доступна рядом с файлом. Сдача и ручное сохранение заблокированы до освобождения очереди. Фотографии и документы взаимно блокируют конфликтующее сохранение. Пустые файлы, неподдерживаемый MIME и размер >10 МБ отсекаются до транспорта; подлинность/качество/права по-прежнему проверяет сервер.

Файлы: `frontend/src/entities/execution/PhotoEvidenceUpload.tsx`, `photo-evidence-upload.css`, `frontend/src/shared/lib/evidence.ts`, `frontend/src/pages/ExecutorTaskPage.tsx`, совместимые optional props `disabled/onBusyChange` в `ActsPanel` (`AnalystPanels.tsx`). Изменённые стили ограничены `.fr-content-v2 .fr-photo-*`. Серверные права, API, история, AI-анализ после сдачи и protected shell не изменены. Тесты: `tests/web/unit/entities/execution/PhotoEvidenceUpload.test.tsx`, `tests/web/unit/pages/ExecutorTaskPage.test.tsx`, актуализированный `tests/web/e2e/maintenance.spec.ts`.

Проверки: **passed** — production build/TypeScript приложения и всех UI/E2E-тестов; 70 целевых unit-тестов (7 новых + 63 существующих). Покрыты требования snapshot, разные ракурсы, несколько файлов/этапов в очереди, ошибка и продолжение без повторной отправки сохранённого файла, формат/размер/disabled, сохранение ответа и актуальная revision при последующей загрузке документа.

**passed** — отдельная QA PostgreSQL/API :18074: настоящий drop до/после, сохранение черновика, одна намеренно перехваченная 503 после успешного первого фото, повтор, ровно 2 сохранённых фото и доступная сдача после опустошения очереди. Desktop 1440/1280/768 и узкие viewport 390/360/320: переполнения и browser errors 0. **passed** — полный SPA/API/PostgreSQL сценарий desktop и mobile390/touch: начало, ответы, фотографии, сдача, автоматический AI guardrail, возврат инженером, новая попытка, повторная сдача, приёмка, readonly директор, история обеих попыток и открытие оригинального файла. Последний mobile прогон повторён после синхронизации панели документов.

Две начальные попытки E2E завершились **failed**: старое ожидание видимого RULE_INPUT_REQUIRED противоречило ранее заказанному сворачиванию диагностики; тест теперь сначала проверяет скрытое состояние, раскрывает «Обоснование решения» и проверяет тот же код. Второй запуск начался до готовности QA API (ERR_EMPTY_RESPONSE); в локальном runner добавлен health-gate. Это не исправлялось ослаблением продуктовой проверки. Первичные и повторные логи сохранены в `photo-upload-e2e-desktop/`.

Артефакты: `reports/redesign-v2/photo-upload-review/baseline.json`, `before-desktop.png`, `manifest.json`, `empty-*.png`, `upload-error.png`, `uploaded-*.png`; baseline commit `65da2c3`. Дополнительно **passed** readonly sweep существующего :5174: 6 ширин + настоящий mobile/touch browser390, изменения данных 0, browser errors 0. `photo-upload-live/manifest.json` и последовательные viewport-снимки `executor-390-touch.png`, `executor-390-touch-bottom.png` с координатами. Desktop/mobile/error/uploaded снимки открыты и просмотрены. E2E: `photo-upload-e2e-desktop/run.log`, `photo-upload-e2e-mobile/run.log`, `checkpoints.jsonl` в обоих каталогах. Мутации выполнялись исключительно в disposable QA DB; рабочие демонстрационные задания не менялись.

**blocked** — физическая камера и настоящий системный файловый диалог мобильной ОС недоступны в headless Chromium. Файловый транспорт и touch-сценарий проверены; это не заменяет прежние ручные ограничения C16. Собственная QA среда удалена после проверки; :5174 и исходный локальный API оставлены работающими.

## Дизайн-итерация 07.11.2026: панель показателей с фоном ЖК

По запросу владельца панель PerformanceOverview получила декоративный монохромный вид жилого комплекса. Основные показатели разделены на три колонки, SLA и трудозатраты — на отдельную строку, экспорт — на нижнюю полосу. На узком доступном пространстве блоки перестраиваются в строки. Изображение приглушено ради читаемости; это сгенерированная архитектурная иллюстрация, а не документальная фотография конкретного объекта.

Файлы: `frontend/src/features/analyst/PerformanceOverview.tsx`, `performance-overview.css`, реэкспорт в `AnalystPanels.tsx`, `frontend/src/assets/residential-overview-v1.webp`, `tests/web/unit/features/PerformanceOverview.test.tsx`. Стиль ограничен `.fr-content-v2 .fr-property-*`. Protected shell и API не изменены. Серверные KPI, числитель/знаменатель SLA, подтверждённые единицы и отчёты сохранены. Пиковая нагрузка использует прежние три максимальных значения person-minutes / 60. Месяц по-прежнему применяется только к двум существующим XLSX URL; показатели объектов при его смене не пересчитываются.

Проверки: **passed** — TypeScript/production build; 4 новых теста KPI/нулей/отсутствия данных/ошибки/месяца экспорта и 2 существующих ScheduleMatrix/PlanApproval. **passed** — live Chromium, роль director, `/director` (раскрытая панель) и `/reports`, viewport 1440/1280/768/390/360/320, 12 screenshots: фон загружен, page overflow 0, browser errors 0, mutations 0. Проверено изменение месяца на 2027-02 и точные XLSX URL. Ключевые desktop/tablet/mobile снимки открыты и просмотрены. Полная ролевая регрессия C16 не повторялась; прежние ограничения приёмки сохраняются.

Артефакты: `reports/redesign-v2/property-overview-review/before-desktop.png`, `before.json` (исходный commit `f511972`), `manifest.json`, `director-1440.png`, `director-768.png`, `director-390.png`, `reports-320.png` и остальные ширины. Все screenshots получены из работающего приложения с локальным API. XLSX-файлы не скачивались заново: проверены ссылки и месяц; серверный экспорт не менялся.

### Происхождение фонового изображения

Режим: встроенный imagegen, новая генерация (generate), без reference images. Сохранённый asset: `frontend/src/assets/residential-overview-v1.webp`, 154294 bytes. Исходный PNG сохранён в каталоге generated_images; WebP — только перекодирование для доставки, без изменения композиции. Изображение загружается lazy, без анимации и blur.

Промпт:

> Use case: photorealistic-natural. Asset type: wide decorative background for a restrained dark B2B residential property operations dashboard. Primary request: a minimalist, photorealistic black-and-white architectural view of a contemporary residential apartment complex in Russia, with several clean mid-rise buildings and a few slender pine trees. Composition: panoramic landscape, architecture concentrated toward the right half and middle distance, broad quiet dark negative space on the left for interface content. Architectural photography, straight verticals, fine facade and window detail, calm overcast light and subtle atmospheric depth. Palette: true monochrome only, charcoal black and soft silver grey, subdued contrast, no bright white sky. Elegant, understated, realistic materials; no decorative effects. Entire image is a background asset, no UI, no lettering, no logos, no watermarks, no people, no cars. Wide 2:1 composition.

## Дизайн-итерация 07.11.2026: техническое обоснование прогноза

По просьбе владельца raw `AI_UNAVAILABLE: INSUFFICIENT_HISTORY…` убран из краткой карточки сравнения. В подробном результате исходные reasons доступны в закрытом по умолчанию «Обоснование решения». Статусы методов, объяснение недоступности AI, выбранная дата и предупреждение нарушения обязательного срока сохранены; API/исходные причины не менялись. TypeScript passed; live summary и раскрытие диагностики проверены, screenshot просмотрен, errors0/writes0. Артефакты `reports/redesign-v2/forecast-copy-review/`.

## Дизайн-итерация 07.11.2026: повторяющаяся стрелка select

Дефект воспроизведён в `/comparisons`: `.ops-register-tools>select` задавал `background` shorthand, сбрасывая no-repeat,15px size и правую позицию из Form.css. В покое image становился none; при hover правило Form.css возвращало только SVG image, который повторялся по всей площади. Одно свойство в этом конкретном selector заменено на background-color; новые глобальные правила и изменения protected shell не вводились.

Before/after computed styles и screenshot подтвердили repeat→no-repeat,auto→15px15px,0%0%→right/center для rest/hover/focus. Дополнительно102live состояния visible select проверены на1440/390 на7экранах (прогнозы, задания, календарь, оборудование, отчёты, обслуживание с редактором, сотрудники): image присутствует, no-repeat,size15px; errors0/API writes0. Ключевые screenshots лично просмотрены, production build passed. Артефакты `reports/redesign-v2/select-background-review/`; полный regression suite не повторялся.

## Дизайн-итерация 07.11.2026: крестик уведомления

По прямому запросу владельца выполнено узкое исправление защищённых уведомлений: позиция `.inbox-item-delete` теперь центрируется относительно `.inbox-item-side` через left50%/translateX(-50%) вместо right-8px. Ранее центр SVG был на4CSSpx правее непрочитанного кружка; после исправления deltaX=0/deltaY=0 при hover и keyboard focus на1440/390. Размеры/высота/обработчик удаления не менялись. На touch сохраняется прежнее разделение: постоянно видимая кнопка и отдельный индикатор непрочитанного ниже, теперь на одной вертикальной оси.

11MaintenanceInbox unit passed; live screenshots mouse/touch лично просмотрены, browser errors0. Проверки только читали уведомления, реальные записи не удалялись/не помечались прочитанными. Геометрия и snapshots до/после: `reports/redesign-v2/notification-alignment/`. Это согласованное исключение из исходного freeze protected shell; исторический baseline первоначального редизайна не подменён.

## Демо-данные 07.11.2026: оборудование и существующие задания

По отдельному запросу владельца изменены данные действующего локального объекта «ЖК „Сосновый парк“». Пять существующих synthetic_demo экземпляров уже имели названия, инвентарные номера, расположение, дату ввода и шесть привязок обслуживания, но117заданий не имели work_order_equipment. Новые несвязанные дубликаты не создавались. Связи восстановлены по точному schedule_entry.binding_id или maintenance_rule_id, дополнительно проверены устойчивые UUID seed и profile/data_origin.

`scripts/restore_presentation_equipment.py` работает только с известным presentation-v1 site UUID, по умолчанию выполняет preview; запись требует `--apply --site-id 7a01cd97-ef71-5768-ae5f-0688714eefa7` и DATABASE_URL. Неоднозначность/существующая другая связь прерывает транзакцию. Запись117relations и117audit_events выполнена одной транзакцией; fingerprint10таблиц фактов до/после совпал. Work_orders, версии, попытки, фотографии, решения, даты, назначения и прогнозы не переписывались. Повторный preview: existing117/missing0.

Перед записью сохранён приватный dump `var/backups/before-equipment-20261107.dump` (929336bytes, SHA256 d16c95e3dfda9a22340bbf98b7e5a085b79536a5eb1704c682c8d68183f4d09e). Dump содержит рабочие данные и исключён из Git; восстановление всего dump после дальнейших бизнес-событий нельзя применять как обычный откат UI.

Live проверки прошли под director/chief_engineer/engineer/executor: первые три роли видят5единиц/117заданий, исполнитель4единицы/37своих заданий. Нет задач с equipmentId=null. Принятая история: ИТП18, контроллер8, насос4, манометр4, контур4; это ранее существовавшие38принятых работ. У инженера assignment-context снова200 без EQUIPMENT_CONTEXT_INVALID. Реестр/паспорт/задание реально открыты, screenshots просмотрены, browser errors0. Артефакты: `reports/redesign-v2/equipment-restoration.json`, `equipment-demo-review/manifest.json`. Полная регрессия не повторялась: backend/API-код и роли не менялись, это разрешённая подготовка локальных демо-данных.

## Дизайн-итерация 07.11.2026: месячный календарь

Исправлен overflow длинных названий: CSS PhaseII ранее запрещал перенос внутри слова, оставляя полное название в узкой месячной колонке. Месячная запись теперь содержит отдельную строку кода/предупреждений и превью названия до3строк. Полный исходный текст остаётся в DOM, accessible name/title и существующем Drawer. Флаги !/? вынесены из обрезаемого текста; aria-label явно сообщает просрочку/уточнение. Еженедельная краткая запись сохраняет свою семантику.

У месячной сетки min-width1120px, собственная горизонтальная прокрутка, Tab-focus region и кнопки «Дни левее/правее» при узком content. Так колонки сохраняют читаемую ширину; весь документ не прокручивается горизонтально. Телефон использует прежнюю повестку с полными названиями. «Ещё…», количество и исходные CalendarOccurrence не менялись.

Проверки:5CalendarPage unit passed, build/TypeScript passed. Live director1440/1280/1024/768 и заполненная agenda390/360/320: события внутри своих ячеек, высота превью ≤101px, title≤3строк, page overflow0/errors0. Проверены полный заголовок Drawer, Enter на «Ещё…», прокрутка кнопками и ArrowRight; week/list также открыты. Ключевые screenshots лично просмотрены; `reports/redesign-v2/calendar-grid-review/manifest.json`. API mutations не выполнялись; полный исторический regression suite не повторялся.

## Дизайн-итерация 07.11.2026: обрезание сортировки

По screenshot пользователя воспроизведён дефект в «Все задания»: desktop select «Порядок» сжимался до189–196px, а его полезная ширина141–148px была меньше162.7px текста «По текущему приоритету». Выделена отдельная колонка не уже250px, добавлен промежуточный двухколоночный reflow; label имеет min-width0. Подписи сокращены до «По приоритету», «Ранние сроки», «Поздние сроки»; значения priority/oldest/newest и вычисление порядка не менялись.

TypeScript passed. Live18комбинаций (3значения ×1440/1280/768/390/360/320) и ещё3при text200 на320: canvas measurement подтверждает textWidth ≤ available, page overflow0, browser errors0. Все итоговые screenshots1440/1280/320/text200 лично просмотрены. API использовался только для чтения. Артефакты: `reports/redesign-v2/executor-filter-review/`; полный regression suite для CSS/подписей не повторялся.

## Дизайн-итерация 07.11.2026: отклик календаря

После сообщения о задержках выполнен сравнительный live Chromium замер на том же задании. Причины: повторное создание locale-formatters для всех дней при каждом вводе, построение закрытого диалога и повторная обработка сетки при изменении часов. `Intl.DateTimeFormat` переиспользуется; дни месяца кешируются; `CalendarGrid` отделён через memo со стабильными обработчиками. Закрытый диалог не строится. Только календарь использует явный `Modal instant`: без входной анимации и backdrop blur; defaults остальных диалогов сохранены.

При CPU throttle4 и ширине390 медиана event dispatch → второй animation frame: открытие175.7→50.2ms, месяц143.2→37.3ms, день135.3→32.3ms, ввод133.3→32.8ms, закрытие150.1→32.0ms. На1440 без замедления итоговые действия занимают около двух кадров (33ms). Это локальная проверка, не универсальная гарантия задержки на любом устройстве. Метод/выборки: `reports/redesign-v2/datefield-performance.mjs`, `datefield-review/performance-before.json`, `performance-memoized.json`. Данные стенда не записывались.

Повторены11целевых unit, 2общих Modal unit и live проверки пяти ширин: focus trap/возврат, Escape, отмена и локальная дата сохранены; page errors и mutating API requests отсутствуют. Production build/TypeScript passed. Общая историческая регрессия не повторялась.

## Дизайн-итерация 07.11.2026: ввод фактического времени

По обратной связи заменены браузерные `datetime-local` в `ExecutionProtocol`: общий `DateTimeField` открывает календарь FixRate AI с ручным вводом даты, часов и минут, клавиатурными стрелками и явным применением/отменой. Автоматической подстановки фактического времени нет. UI отдаёт прежнюю локальную строку; потребитель сохраняет прежнее преобразование в UTC ISO. Изменены также поля времени измерений; read-only представление осталось отдельным.

Норматив, состав и длительность собраны в компактную строку фактов, человеко-часы получили отдельную подпись единицы, даты обязательств форматируются через существующий date-only helper. Автор основания возврата показан отдельной строкой «Проверяющий: …». Стили принадлежат рабочему content и его диалогу; protected shell не менялся.

Проверки: 11 targeted unit passed, production build и TypeScript UI/E2E passed. Live React/API просмотр выполнен на 1440/768/390/360/320 px: page overflow0, console errors0, Tab trap/Escape/focus return, Cancel без изменений, локальная дата около полуночи сохранена. В тесте блокировались все mutating API-запросы после входа; записей не было. Артефакты: `reports/redesign-v2/datefield-review/`. Полный прежний regression suite ради этой итерации не повторялся; screen reader и физическая клавиатура телефона не проверялись.

Рабочая ветка `feat/frontend-redesign-v2` создана непосредственно от `frontend_polished` / `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Исходное дерево не изменяется. Реализация не означает прохождения полного C16; итоговые gates и ограничения приведены в FINAL_REPORT.md.

## Источник требований

Оригинал: `C:\Users\kran\Downloads\FixRateAI-phase2-visual-design-2026-11-06.zip`, SHA-256 `3bb8c395496581ce2e1727d2eaccb926698eac0ec9e91e0685b77fa7876a79ac`. Распакован без изменения файлов в `docs/redesign-v2/source/FixRateAI-phase2-visual-design-2026-11-06`. Большой исходный комплект исключён из Git; ZIP и evidence сохранены. Рабочие снимки и результаты находятся в `reports/redesign-v2`, согласно структуре из `docs/service/development.md`.

## Контрольные изменения

| Задача | Реализация и границы | Проверка |
|---|---|---|
| C00 | Настоящие маршруты, четыре реальные read-only сессии, исходные screenshots и карта контрактов | [Baseline](BASELINE.md); снимки не заменяют мутационные проверки |
| C01 | `ContentTheme`, локальный `content-theme.css`, существующие Card/Form/Button, явное opt-in владение Modal/Drawer. `/profile` исключён; shell не наследует тему | Первоначальный и финальный shared повтор: 32/32 exact pixel comparisons, 0 changed pixels |
| C02 | `presentation.ts`: подписи состояний, ответов и единиц; существующее различение date-only и timestamp сохранено; неизвестный task state не исчезает | 3 целевых unit-теста passed; поле deadlineBreached означает позднюю приёмку, а не текущую просрочку |
| C03 | `ExecutorPage`: «К выполнению» с прежним составом, поиск/период/порядок по загруженной истории, query-параметр очереди, компактный mobile spotlight | Live geometry, mobile и ролевой E2E; детали VISUAL_QA/REGRESSION |
| C04 | `ExecutorTaskPage`, `ExecutionProtocol`, `EvidenceComparison`: сохранённые значения текстом, одинаковая пара До/После, история внизу, инженерное поле документа недоступно исполнителю | Реальный E2E start/upload/submit/rework/new-attempt/accept; итоговые desktop/mobile результаты в REGRESSION |
| C05 | `QualityTaskPage`: заголовок до доказательств; старое решение вместо disabled-формы; обязательное основание перед обеими командами; реальные статусы документов; короткое AI и раскрываемый разбор | Mobile decision раньше baseline и доступен по прямой ссылке; FULL12tiles, ограничения общего C15 сохранены |
| C12 | `PhotoReviewCard`, `ForecastResultCard`, `ComparisonDetailPage`: ограничения доступны до раскрытия, подробные наблюдения и provenance отдельно, подтверждение прогноза после методов | 8 целевых presentation/photo-review passed; FULL anchor, ограничения/наблюдения сохранены |

Дополнительно реализованы C06/C07/C09/C11/C19: `CrewSelectionPanel`, `DispatcherPage`, `TaskDetailPage`, `TasksPage`, `EquipmentPage`, `EquipmentDetailPage`, `ReportsPage`, `AccessDeniedPage`, `NotFoundPage`. Назначение объясняет отсутствие оборудования, обзоры начинают с исключений, результат директора read-only, реестр имеет локальную пагинацию с явным scope. Подробности — [контрактный аудит](CONTRACT_AUDIT.md).

C08/C10/C13/C18: `CalendarPatternEditor`, `calendarPattern.ts`, `SectionForm`, `ServiceSettingsPage`, `CalendarPage`, `ScheduleMatrix`, `WorkforceSettingsPage`. Существующий редактор смен восстанавливает sparse server defaults, секции регламента сохраняют mounted fields и ввод; ошибки раскрывают раздел; календарь имеет mobile agenda и управляемую матрицу. Подробности — [редактор и календарь](SETTINGS_IMPLEMENTATION.md), [расследование смен](SHIFT_AUDIT.md).

C14/C15: scoped `background-color` сохраняет существующий chevron select; длинные подписи метрик переносятся; недельный переключатель перестраивает строки при увеличении текста; обычная anchor-ссылка ведёт к основанию решения на узком экране. Ни одно из исправлений не меняет protected shell или серверные проверки.

Контраст измерен на живых computed styles: исправлены полупрозрачные metadata checklist, placeholder и граница инструкции. На mobile E2E снимке найден raw ISO timestamp/front в `AttemptHistory`; применены существующие `useSiteDateTime` и `viewLabel`, источники истории и ссылки на оригиналы не менялись. Целевые6тестов прошли, mobile flow повторён после изменения.

Приёмка всех задач и ограничения C14–C16 — в [итоговом отчёте](FINAL_REPORT.md), выполненные проверки — в [регрессии](REGRESSION.md).

## Подтверждённые отклонения и ограничения

- C17: backend projection не теряет equipment. Presentation seed не создавал `work_order_equipment`. Исправляется создание новых seed-заданий; существующие записи автоматически не чинятся и по названию не сопоставляются.
- C18: sparse persisted CalendarPattern не имел массивов, требуемых UI. Нормализация использует серверные defaults, а не defaults формы создания. Неизвестный шаблон блокирует сохранение без преобразования в новый график.
- `deadlineBreached` вычисляется по времени инженерной приёмки. Его нельзя переопределить по красной плашке текущей просрочки. SLA и расчёт дат остаются прежними.
- DTO документа содержит kind/verified/url, но не сохранённое основание проверки. UI не придумывает это основание; итоговая причина решения и поле проверки документа остаются разными значениями.
- Дата ввода фактического времени использует существующий часовой пояс устройства и явно подписана. Просмотр timestamp использует часовой пояс объекта. Преобразование ввода в другую зону не вводилось как скрытый редизайн контракта.
- Локальный Python 3.11 не подходит исходному backend с синтаксисом Python 3.12. Проверки backend перенесены в изолированный Docker Python 3.12/PostgreSQL 18; основной стенд и его данные не меняются.

## История

`0aa9833` — scoped theme и baseline; `4e2bf86` — relation новых seed-заданий; `34e9aa6` — сохранённые смены и секционный редактор; `4c30324` — выполнение/приёмка, доказательства и календарь; `7943ca4` — обзоры, назначение, реестры. Последующие контрольные исправления и QA фиксируются отдельно. Push/deploy не выполняются.
