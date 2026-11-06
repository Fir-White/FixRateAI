# Регламенты, календарь и смены: C08, C10, C13, C18

Рабочая ветка: `feat/frontend-redesign-v2`, база `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Документация следует [правилам разработки](../service/development.md): исходники в frontend, тесты в tests/web, результаты запусков в reports. Это отчёт о выполненном срезе, не замена финального C16.

## Изменения

| Пакет | Фактическая реализация | Файлы |
|---|---|---|
| C08 | Паспорт сохраняется отдельно и свёрнут при выборе существующего оборудования; другие регламенты сворачиваются при открытии редактора. Секции основного контекста, ресурсов, периодичности, методики, чек-листа и допусков; общий summary и прежнее сохранение. Все поля остаются mounted. Ошибка раскрывает секцию и переводит фокус к полю. Нет wizard, autosave и перехвата «Назад». | ServiceSettingsPage.tsx, features/settings/SectionForm.tsx, settings-workspace.css |
| C08/C13 | Тексты yearly_count различают существующие annual_policy `from_anchor` / `calendar_year`. Помощь в сменах описывает сотрудников, а не оборудование. Периодичности и basis не менялись. | CalendarPatternEditor.tsx |
| C10 | Календарь и матрица — явные локальные режимы. Предупреждение preview и существующее создание заданий стоят до длинного списка. Матрица имеет мобильный список обязательств, полное двумерное представление, управляемую прокрутку, заголовки и подписи исходных дат. Переносы не сливаются. Состояния версий плана локализованы; исходное право утверждения сохранено. | CalendarPage.tsx, calendar-v2.css, только функции ScheduleMatrix/PlanApproval в AnalystPanels.tsx |
| C13 | Независимые разделы сотрудников, бригад, видов допусков; скрытые формы сохраняют введённый черновик при переключении. Сведения о доступе читаемы, прежний disabled fieldset сохранён. Исключения и допуски раскрываются отдельно. Смена имеет summary, контекстную помощь и раскрываемые ограничения. | WorkforceSettingsPage.tsx; PersonalShiftsPage продолжает использовать read-only EmployeeCalendar |
| C18 | Адаптер сокращённого сохранённого pattern по серверным default; unknown/malformed правило не получает Save. Открытие смены не пишет данные. | [Подробный аудит](SHIFT_AUDIT.md), shared/lib/calendarPattern.ts |

CSS ограничен `.fr-content-v2`, использует существующие `--fr2-*`. Sidebar, профиль, уведомления, Back и их общие стили не редактировались. Rail появляется от 1040 px ширины контейнера; геометрия при 1134 px — 774 + 24 + 336. Высота определяется содержимым.

## Проверки кода и поведения

| Проверка | Статус | Результат |
|---|---|---|
| ServiceSettingsPage unit | passed | 9/9: все семь periodicity payload сохраняются при правке одного поля; hidden required error раскрывается/фокусируется; typing не закрывает секцию; separate save и after_accepted_completion сохранены |
| WorkforceSettingsPage unit | passed | 4/4: existing sparse shift edit/save/reopen, ID/revision/exclusions/overnight; неизвестное правило; конфликт не очищает ввод; смена раздела не теряет черновик |
| CalendarPattern boundary unit | passed | 19/19: серверные defaults, семь форматов, JSON round-trip, invalid/unknown отказ |
| ScheduleMatrix unit | passed | 2/2: два source dates с одним переносом остаются отдельными; у director нет утверждения/основания |
| Существующий CalendarPage suite | passed | 5/5 после изменения режима/preview; существующие API-вызовы и ограничения роли сохраняются |
| Серверные shift rules | passed | `tests/backend/test_shifts.py`: 4/4; алгоритм не изменён |
| Живой hidden required validation | passed | :5174, chief; очистка обязательной инструкции, закрытие секции, Save раскрывает поле и ставит фокус; после ввода секция остаётся открыта. Перехват запрещал любые maintenance mutations, записей/попыток записи 0 |
| Полный API save/reopen с persisted calendars | blocked | Выполняется отдельно на изолированном :18074; данный read-only прогон не подтверждает серверную запись |
| Полный C14/C15/C16, 200% текста/400% zoom | blocked | Частичная проверка ниже не закрывает общий gate |

Команды: `cd frontend; npm.cmd test -- ServiceSettingsPage.test.tsx WorkforceSettingsPage.test.tsx ScheduleMatrix.test.tsx CalendarPage.test.tsx calendarPattern.test.ts`. Отдельные локальные typecheck в процессе параллельной работы обнаруживали временные ошибки других изменяемых файлов; окончательная сборка фиксируется общим отчётом.

## Визуальная проверка живого приложения

Источник :5174 с действующей аутентификацией и API :8000. Вход chief_engineer; только чтение. Открыты реально существующие ИТП-01 / правило 1.1 и смена исполнителя. Учётные данные читались в памяти, в отчёты не записывались. API-ошибки после входа и `pageerror` отсутствуют; 401 `/auth/session` до входа — ожидаемая проверка отсутствующей сессии.

Артефакты: `reports/redesign-v2/settings-live-r2/manifest.json` (58 viewport captures), `matrix-live-r2/manifest.json` (12), `settings-keyboard/manifest.json` (6). Полные PNG не склеивались; шаг viewport минус 100 px. Проверены размеры документа: горизонтального overflow вне внутренней матрицы не обнаружено.

| Экран | Viewport | Просмотр | Статус |
|---|---|---|---|
| Существующий редактор обслуживания | 1440, 1280, 768, 390, 360, 320 | Получены tiles; лично просмотрены top/body/bottom на 1440/390, body/bottom на 320 | passed для просмотренных областей, остальное PARTIAL |
| Раскрытый чек-лист | 390 | Просмотр выбранного пункта и последующих компактных строк | passed, PARTIAL по полной высоте |
| Существующая смена | 1440, 390, 360, 320 | Top/body/bottom на 1440/390, bottom на 320 | passed для просмотренных областей, остальное PARTIAL |
| Мобильная матрица | 390 | Список операций, полная матрица, нижняя часть и горизонтальная прокрутка кнопкой с дней 1–2 к 5–6 | passed, PARTIAL по остальным ячейкам |

Примеры после изменений: `settings-live-r2/chief-service-1440-y800.png`, `chief-service-390-y2783.png`, `chief-shift-390-y1488.png`, `matrix-live-r2/chief-matrix-scrolled-390-y744.png`. Исходный baseline находится в `reports/redesign-v2/before/`.

После просмотра исправлены лишняя длина списка регламентов перед редактором, двойные вложенные рамки календарного правила, длинная открытая справка смены и слой закреплённой колонки матрицы. Полная высота default service fixture после исправлений: 2464 px desktop1440 / 3627 px mobile390. Это размеры данного состояния, не fixed-height и не обещание для всех данных.

Первый capture открытого checklist и первые два прогона matrix agenda поймали загрузку. Они не подтверждают готовое содержимое: для matrix итоговый источник — `matrix-live-r2`, для checklist — `settings-live-r2`. Файлы сохранены для прослеживаемости, не засчитаны как успешный визуальный просмотр.

Референсы реально просмотрены: chief desktop/mobile concepts; области evidence `125-equipment-settings__desktop` Y1340–2340, `076-calendar__mobile` Y1483–2460, `151-workforce-settings__desktop` Y1550–1900. Производные crops лежат в reports/redesign-v2/reference-regions; исходный архив/evidence не изменены.

## C15: полный просмотр опорного редактора

Лично просмотрены в original resolution **все** последовательные tiles живого chief_engineer, существующий ИТП-01 / регламент 1.1, состояние открытого редактора без изменения данных. Источник — [финальный manifest](../../reports/redesign-v2/after-final-shared/manifest.json), версия `frontend-redesign-v2-dirty-C14`, рабочая база указана выше. Это FULL только данного состояния; закрытые секции и другие периодичности не считаются просмотренными на этих кадрах.

- Desktop 1440×900, FULL: [Y0](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-1440-y0.png), [Y800](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-1440-y800.png), [Y1564](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-1440-y1564.png).
- Mobile 390×844, FULL: [Y0](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-390-y0.png), [Y744](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-390-y744.png), [Y1488](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-390-y1488.png), [Y2232](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-390-y2232.png), [Y2783](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-390-y2783.png).

Перекрытия последовательны; низ формы и сохранение просмотрены, повторов начала/blank/auth нет. Desktop shell свёрнут, как в соответствующем before. Сопоставлены реальные before [desktop Y1600](../../reports/redesign-v2/before/chief_engineer-anchor-1440-y1600.png), [mobile Y2976](../../reports/redesign-v2/before/chief_engineer-anchor-390-y2976.png), [mobile низ Y8504](../../reports/redesign-v2/before/chief_engineer-anchor-390-y8504.png) и обе схемы `concepts/chief-desktop.png`, `chief-mobile.png`. Before здесь просмотрен выборочно, PARTIAL; ему не выставляется новая оценка FULL.

Девять экспертных критериев, шкала 1–10, только просмотренный content; это не измерение accessibility и не функциональная приёмка:

| Критерий | Desktop / mobile | Обоснование |
|---|---|---|
| Композиция | 8 / 7 | Основное и периодичность открыты, остальные разделы компактны; desktop summary справа, mobile последовательно внизу, как в концепте |
| Типографика | 8 / 8 | Заголовки различимы, пояснения читаемы; полный заголовок операции переносится над однострочным полем |
| Информационная иерархия | 8 / 7 | Контекст оборудования и версии перед редактированием; остаётся длинный вводный участок до самой формы |
| Цветовая система | 8 / 8 | Графит и спокойный мятный CTA, вторичный текст различим; нет новых декоративных акцентов |
| Качество компонентов | 6 / 6 | Обнаружен дефект: у select отсутствует стрелка раскрытия, см. ниже |
| Плотность | 8 / 7 | Вместо постоянно раскрытого чек-листа — секции со сводками; mobile default высота 3627 px, сохранение ещё требует прокрутки |
| Согласованность | 8 / 8 | Единые control, границы и summary; отдельное сохранение паспорта не смешано с регламентом |
| Мобильная адаптация | not_applicable / 7 | Для desktop критерий неприменим; на mobile одна колонка, 16 px поля, кнопка сохранения читаема, наложений нет; выбранное длинное имя оборудования в native select целиком не видно |
| Профессиональная завершённость | 7 / 7 | Композиция заметно ближе к концепту, история/версии явно объяснены; требуется исправить affordance select |

**Finding C15-SET-01 — failed, P2:** scoped `.ui-control` задаёт `background`, сбрасывая `background-image` существующего select при `appearance:none`. На before стрелки есть; на after desktop Y800/Y1564 и mobile Y1488 отсутствуют. Передано владельцу общей DS; минимальное исправление — `background-color` вместо shorthand. До новой проверки исправленного control этот критерий не passed. Остальной просмотр композиции — passed в границах указанного состояния. Нижнее расположение mobile CTA соответствует концепту, но длина формы остаётся отмеченным ограничением, а не замалчивается.

Проверка Markdown-ссылок в новых `docs/redesign-v2/*.md` (без неизменяемого source): до добавления этого раздела проверены 33 локальные ссылки, отсутствующих целей нет. Проверка касается существования файлов, не всех heading anchors.

Повтор C15-SET-01 после исправления владельцем DS — **passed** для service/calendar. В `content-theme.css` shorthand заменён на `background-color`. На живом :5174 computed `backgroundImage` присутствует у всех 31 select открытого service editor (включая mounted закрытые секции) и у одного calendar select: [manifest](../../reports/redesign-v2/select-fix/manifest.json). Лично просмотрены новые [desktop1440](../../reports/redesign-v2/select-fix/chief-select-1440.png) и [mobile390](../../reports/redesign-v2/select-fix/chief-select-390.png): стрелки восстановлены. Первый mobile кадр был снят во время responsive transition sidebar; повтор с ожиданием завершения перехода заменил его. Проверка assignment control на live API8000 — **blocked**: нет доступного задания с equipmentId и состоянием, разрешающим подбор; данные не изменялись. Таблица выше сохраняет оценки первоначального FULL с дефектом, последующий просмотр точечный, PARTIAL; весь sweep повторно не объявляется выполненным.
