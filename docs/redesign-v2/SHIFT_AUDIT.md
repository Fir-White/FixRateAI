# C18 — совместимость сохранённых смен

Исходная версия: `frontend_polished`, `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Изменения выполнены в `feat/frontend-redesign-v2`. Правила документации: [разработка](../service/development.md). Задание: [C18](source/FixRateAI-phase2-visual-design-2026-11-06/08_CODEX_TASKS/C18.md).

## Причина

В [presentation.py](../../backend/app/integration/presentation.py) демонстрационная смена сохраняется с сокращённым `calendar_pattern`: `frequency`, `anchor_date`, `interval`, `weekend_policy`. Это допустимый формат серверного [CalendarPattern](../../backend/app/schemas/maintenance.py): остальные поля имеют значения по умолчанию. Планировщик [shifts.py](../../backend/app/scheduling/shifts.py) валидирует JSON через эту схему и получает массивы.

[workforce_view](../../backend/app/integration/management.py) возвращает `r.calendar_pattern` без нормализации. [ShiftEditor](../../frontend/src/pages/WorkforceSettingsPage.tsx) раньше передавал этот JSON непосредственно в [CalendarPatternEditor](../../frontend/src/features/settings/CalendarPatternEditor.tsx). При отсутствии `excluded_dates` дочерний DateList обращается к `values.map`. У недельных/годовых вариантов аналогичный риск у `weekdays.includes`, `months.includes`, `month_days.join`. TypeScript-интерфейс описывал полные массивы, но не проверял сетевое значение.

Нельзя исправить это общим `patternDefaults`: для новой недельной смены он выбирает Пн–Пт. Серверный default сохранённого правила — пустой список, который означает день недели опорной даты. Такое использование изменило бы расписание.

## Исправление

[readCalendarPattern](../../frontend/src/shared/lib/calendarPattern.ts) заполняет только отсутствующие поля по существующей серверной схеме, проверяет формат и допустимые сочетания. Неизвестные поля/версии, неверные даты, массивы и значения отклоняются. Неизвестные данные не удаляются и не превращаются в пустой график. Нормализация создаёт новые массивы и не меняет исходный ответ.

Редактор существующей смены применяет адаптер при открытии. При ошибке показывает название смены, причину и закрытие; кнопки сохранения нет. Открытие не выполняет запись. Для поддержанного правила сохраняются ID, expected_revision, даты действия, часы, статус и исключения. API, SQL, алгоритм развёртывания смен, защищённая оболочка и данные стенда не менялись.

## Проверки

| Проверка | Результат | Доказательство / ограничение |
|---|---|---|
| TypeScript production | passed | `cd frontend; npm.cmd run typecheck` |
| Sparse seed/defaults, семь периодичностей, JSON round-trip, malformed/unknown | passed | [calendarPattern.test.ts](../../tests/web/unit/shared/lib/calendarPattern.test.ts), 19 тестов |
| Existing shift open/edit/save/reopen, ID/revision/exclusions/ночные часы | passed | [WorkforceSettingsPage.test.tsx](../../tests/web/unit/pages/WorkforceSettingsPage.test.tsx), mocked API |
| Неизвестное правило не сохраняется; конфликт сохраняет ввод; role fieldset отключён | passed | Тот же UI suite, всего 3 теста; вместе с helper 22/22 |
| Исходные серверные правила смен | passed | `PYTHONPATH=backend python -m pytest tests/backend/test_shifts.py -q`: 4/4; ISO parity, overnight, DST, employment clipping |
| Live existing edit desktop/mobile | passed | :5174 → :8000, chief_engineer: существующая sparse смена открыта на 1440/390/360/320. `reports/redesign-v2/settings-live-r2`; top/body/bottom 1440/390 лично просмотрены, без pageerror |
| Live isolated save/reopen и эквивалентность календаря после записи | blocked | Нужна изолированная API fixture; реальные смены ради теста не менялись |

Текущий статус C18: исправление реализовано, локальные проверки и живое открытие пройдены; полная приёмка остаётся blocked до живой проверки сохранения. Последующие C08/C10/C13 описаны в [отчёте реализации](SETTINGS_IMPLEMENTATION.md).
