# Журнал реализации редизайна v2

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
