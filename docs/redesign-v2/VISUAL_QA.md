# Визуальные проверки

## Панель показателей, 07.11.2026

**passed**: live director на `/director` и `/reports`, 1440/1280/768/390/360/320. Монохромный фон загружен на всех ширинах, текст и экспорт помещаются, document overflow 0; browser errors/mutations 0. Просмотрены desktop, tablet, mobile390 и mobile320. До/после и координаты проверки: `reports/redesign-v2/property-overview-review/manifest.json`, `before-desktop.png`, `director-1440.png`, `director-768.png`, `director-390.png`, `reports-320.png`. На мобильном фоне сильнее затемнение и показатели расположены строками. Иллюстрация не является фотографией реального ЖК. Проверка не заменяет полную C15/C16 приёмку.

## До изменений, 06.11.2026

Источник — настоящие сессии локального приложения, исходный код `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`; снимки: `reports/redesign-v2/before/manifest.json`. Файлы запусков не добавляются в Git. PNG архива Phase II не подменяют эти снимки.

Лично просмотрены:

| Роль / экран | Файл в before | Результат просмотра |
|---|---|---|
| Executor queue, раскрытый sidebar | `executor-home-1440-y0.png` | passed: полное имя, приоритет и следующее задание, узнаваемая оболочка |
| Executor submitted | `executor-anchor-390-y0.png` | passed: живой mobile; история над названием, оборудование «Не указано» |
| Engineer submitted | `engineer-anchor-1440-y0.png` | passed: валидный рабочий экран вместо исторического auth capture; документ расположен перед названием |
| Engineer submitted, низ | `engineer-anchor-390-y6812.png` | passed: причина и обе кнопки доступны в конце, но слишком далеко после AI |
| Chief service editor | `chief_engineer-anchor-1440-y1600.png` | passed: реальный existing rule, периодичность и значения |
| Chief service editor, низ | `chief_engineer-anchor-390-y8504.png` | passed: сохранены обе операции сохранения/закрытия, содержание не повторяет верх |
| Director overview | `director-anchor-1440-y0.png` | passed: сводка и экспорт до h1, рабочая полоса метрик |
| Director overview, низ | `director-anchor-390-y2694.png` | passed: отсутствие AI-результата и причина доступны |

`passed` здесь относится к получению и просмотру конкретного кадра, не к приёмке целевого дизайна. Страницы остаются PARTIAL, поскольку каждый промежуточный tile лично не просмотрен. Функциональные проверки не выводятся из PNG.

## После изменений

Пока blocked: реализация и повторные снимки не закончены. Требуются сравнение четырёх anchor, protected shell, 1440/1280/768/390/360/320, 200% text/400% zoom, клавиатура, ошибки и диалоги. Начальный capture не закрывает C14–C16.

### C01: промежуточная проверка protected shell

После внедрения scoped ContentTheme выполнен повторный живой capture на Vite `http://127.0.0.1:5174`, с теми же реальными сессиями/backend и reduced motion. Артефакты — `reports/redesign-v2/after-foundation/`. Это промежуточное рабочее дерево, не финальная поставка.

`scripts/redesign_compare_protected.py` сравнил 32 области для четырёх ролей: раскрытый sidebar, свёрнутый sidebar, desktop topbar, верхняя часть и содержимое панели уведомлений, полный первый viewport профиля 1440/390, mobile topbar с Back. **32 passed, 0 failed; изменённых пикселей 0 во всех сравниваемых областях.** Результат — `reports/redesign-v2/protected-foundation.json`. Маскирования защищённых элементов нет; сравнительные области заданы явно в скрипте. Панель уведомлений и профиль также лично просмотрены.

Эта проверка подтверждает отсутствие видимого влияния первоначальных scoped стилей на снятые состояния оболочки. Она не заменяет финальную проверку всех состояний, анимаций, keyboard focus и поведения Back после остальных изменений.

### C04/C05: промежуточные ролевые снимки

`reports/redesign-v2/after-role/` содержит live executor/engineer anchor 1440/390 на Vite с настоящими сессиями и неизменённой презентационной БД. В обоих проходах `pageerror=0`. Лично просмотрены desktop Y0 и mobile Y0/Y2232/нижний tile (executor Y4240, engineer Y4777).

Подтверждено: контекст перед доказательствами, сохранённые ответы обычным текстом, До → После, история в конце, отдельное основание документа и основание решения. Engineer desktop rail читается отдельно от доказательств. Executor desktop остаётся одноколоночным при доступной рабочей ширине около 1028 px, ниже установленного порога 1040.

Остаточное замечание: engineer mobile решение начинается примерно Y4400 вместо прежних ~6900; ориентир спецификации ≤2600 ещё не достигнут. Длинные checklist/photo/AI-пояснения сохраняют большую высоту. Это промежуточный результат, не финальная визуальная приёмка C15.

## Финальная сверка C14/C15

`reports/redesign-v2/after-final-shared/manifest.json` содержит роль, маршрут, viewport, Y и версию. Все перечисленные ниже последовательные tiles лично просмотрены в читаемом масштабе, с перекрытием; FULL относится к конкретному состоянию, а не ко всем состояниям страницы.

| Anchor | Desktop1440 Y | Mobile390 Y | Просмотр |
|---|---|---|---|
| Executor submitted | 0,800,1600,2400,2832 | 0,744,1488,2232,2976,3720,4420 | FULL, 12 tiles; сохранённые ответы/фото/комментарий/AI/история |
| Engineer submitted | 0,800,1600,2126 | 0,744,1488,2232,2976,3720,4464,4830 | FULL, 12 tiles; документы/факты/checklist/пара фото/AI/решение |
| Chief existing service | 0,800,1564 | 0,744,1488,2232,2783 | FULL, 8 tiles; [сверка и исправление select](SETTINGS_IMPLEMENTATION.md) |
| Director overview | 0,800,1017 | 0,744,1488,2232,2740 | FULL, 8 anchor tiles; ещё 3 home1440; [9 критериев](CONTRACT_AUDIT.md) |

Сопоставление «До / После» использует одинаковые role/fixture/routes из `before/manifest.json` и `after-final-shared/manifest.json`. Исходный `e856be90…` остаётся submitted, его данные не менялись. Для быстрого открытия: [исполнитель до](../../reports/redesign-v2/before/executor-anchor-390-y0.png) / [после](../../reports/redesign-v2/after-final-shared/executor-anchor-390-y0.png), [инженер до](../../reports/redesign-v2/before/engineer-anchor-1440-y0.png) / [после](../../reports/redesign-v2/after-final-shared/engineer-anchor-1440-y0.png), [chief после](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-1440-y0.png), [director после](../../reports/redesign-v2/after-final-shared/director-anchor-390-y0.png). Артефакты локальные, Git их не включает.

| Критерий | Результат и предел |
|---|---|
| Иерархия | passed: название и текущая попытка до деталей, история после; engineer rail рядом с доказательствами на широкой рабочей области |
| Геометрия | passed: content breakpoint1040, rail336/gap24; executor на1440 имеет контент1028 и обоснованно остаётся одноколоночным |
| Плотность/поверхности | passed: сохранённые ответы и checklist — строки, AI detail раскрывается; обязательные факты не удалены |
| Типографика/подписи | passed на просмотренных tiles: длинные названия переносятся, zero/units сохранены; UUID фото скрыт только в доступные реквизиты |
| Контраст всех состояний | blocked: полный измерительный аудит hover/focus/disabled/overlay не выполнен; visual palette не выдаётся за WCAG compliance |
| Статусы/AI | passed: отправлено/попытка/срок и ограничения раздельны; uncertain не превращён в успешную приёмку |
| Доступность действия | passed для tested shortcut: mobile engineer переход к решению ставит rail на88px ниже protected header; абсолютный Y решения всё ещё больше концептуального ориентира2600 |
| Адаптивность | passed: 4 anchors×6widths, 320CSS reflow, text200 и точечный повтор исправлений; реальная экранная клавиатура и screen reader blocked |
| Protected shell | passed: `protected-after-final-shared.json`,32/32,0 changed pixels; после этого менялись только owned controls/overview/shortcut |

Исправления C15: select потерял стрелку из-за background shorthand — восстановлен background-color,31 service +1calendar controls проверены и просмотрены (`select-fix/`). При text200 labels метрик и недели пересекались — добавлены переносы и перестроение недельных ячеек; повтор390 normal/text200 просмотрен. `accessibility/` хранит актуальные geometry/keyboard результаты и screenshots. Полный Tab/submit/review ручной сценарий, OS keyboard и screen reader не подменяются частичными Enter/Tab/Escape проверками.

Снимки иных состояний, не перечисленные как FULL, остаются PARTIAL. Не все error/loading/empty/overlay кадры имеют сопоставимые before/after: полный C15 gate остаётся blocked, несмотря на завершённый просмотр четырёх опорных состояний. Текущий live legacy seed без оборудования — известное ограничение данных C17, не ложная подпись оборудования.

Финальные измерения контраста выявили и закрыли ещё три конкретных дефекта: metadata checklist4.30→7.35:1, placeholder3.58→7.90:1, instruction border1.43→3.89:1. Выборка30состояний4anchors и2photo modals описана в [CONTRACT_AUDIT](CONTRACT_AUDIT.md). Это точечное подтверждение, а не снятие ограничения полного аудита. Сравнение chief: [до](../../reports/redesign-v2/before/chief_engineer-anchor-1440-y0.png) / [после](../../reports/redesign-v2/after-final-shared/chief_engineer-anchor-1440-y0.png); director: [до](../../reports/redesign-v2/before/director-anchor-390-y0.png) / [после](../../reports/redesign-v2/after-final-shared/director-anchor-390-y0.png).

### C14/C15: адаптивность и исправления

Скрипт `scripts/redesign_accessibility.mjs`, результаты `reports/redesign-v2/accessibility/results.json`: 24 комбинации четырёх опорных экранов × 1440/1280/768/390/360/320 — passed по отсутствию горизонтального переполнения документа, `pageerror=0`. Ширина 320 проверяет reflow, эквивалентный 400% масштабу исходных 1280 CSS px; это не утверждение о реальном управлении масштабом Chrome.

Увеличение всех computed font-size/line-height в изменяемой content-области до 200% проверено на 390. Найдено два визуальных дефекта director при отсутствии document overflow: наложение подписей метрик и тесные ячейки недельной полосы. После scoped исправлений переносов и reflow недельной полосы повтор `fix-results.json` прошёл; новые top/middle снимки лично просмотрены. Сохранены все надписи и действия. Защищённые области тестовым увеличением не затрагивались.

Клавиатура: Enter раскрывает details всех четырёх ролей; drawer календаря получает фокус, удерживает его при 12 последовательных Tab, Escape закрывает drawer и возвращает фокус trigger — passed. Отдельная ссылка engineer «Перейти к основанию решения» на 390 переводит rail к Y88, ниже protected header; проверена без отправки решения (`engineer-decision-jump-top.png`, `engineer-decision-jump-target.png`).

Первый C14 capture обнаружил race восстановления scroll: файл director с именем top показывал низ страницы. Исправлен только capture: реальное wheel-событие отменяет сохранённый scroll, manifest записывает actualY, повторные top имеют Y0. Это capture-дефект, не CSS-дефект приложения.

Повтор protected после последних shared Badge/Callout/Drawer изменений: `protected-after-final-shared.json`, 32/32 passed, нулевой pixel diff. Полные последовательные anchor tiles — `after-final-shared/`, исходники эквивалентны коммиту `7943ca4` до локальных C15 fixes; затронутые fixes проверены отдельно. Это не полная WCAG сертификация: screen reader, реальная OS экранная клавиатура, все contrast/hover пары и физическое управление zoom остаются blocked в данной среде.

Финальный live mobile E2E после локализации истории:1/1 passed, source c5d4c65. Лично просмотрен `e2e-mobile-final/director-history-390-y2853.png`: обе попытки, даты в timezone объекта и подпись «Спереди». Остальные актуальные viewport checkpoints перечислены в `e2e-mobile-final/checkpoints.jsonl`; это PARTIAL состояния тестового workflow, не FULL длинных страниц. Synthetic изображения явно подписаны; они не являются доказательством реального обслуживания.
