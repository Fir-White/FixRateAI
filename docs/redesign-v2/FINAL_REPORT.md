# Редизайн FixRate AI v2 — результат

Дизайн-итерации после первоначального отчёта и их отдельные проверки: [журнал реализации](IMPLEMENTATION_LOG.md). В частности, 07.11.2026 добавлен собственный выбор даты/времени и обновлена форма фактического выполнения; исторические итоговые counts ниже относятся к первоначальной регрессии.

Реализован доступный frontend-объём C00–C19 в отдельном worktree `.worktrees/frontend-redesign-v2`, ветка `feat/frontend-redesign-v2`. Основа строго `frontend_polished` / `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Исходная ветка, рабочие данные и protected shell сохранены. Push и deploy не выполнялись.

**Полная готовность по обязательному gate C16 пока blocked.** Основной код реализован, но screen reader, реальная экранная клавиатура, полный ручной keyboard workflow и некоторые визуальные состояния не проверены в доступном окружении. Нельзя выдавать автоматизированный Chromium sweep за эту приёмку. Существующий presentation seed также содержит исторические задания без equipment relation; исправление распространяется на новые seed-задания, старые строки не менялись.

## Что изменилось

Сохранённые попытки показывают значения вместо disabled-форм; пары фотографий и оригиналы доступны, история перенесена после текущей работы. Инженер видит доказательства и собственное основание решения, AI-ограничения предшествуют подробностям. Директор получает компактные метрики и исключения, обычное задание остаётся read-only. Регламент разделён на раскрываемые секции с переходом к ошибке, сохранён существующий редактор смен. Календарь получил mobile agenda, реестры — явный охват и локальную пагинацию. Тема изолирована в изменяемом content и его portals.

## Статусы заданий

`passed` ниже означает указанный проверенный объём; не распространяется на отдельные общие gates C14–C16.

| Задача | Статус | Результат / ограничение |
|---|---|---|
| C00 | passed | Ветка/SHA, карта маршрутов/контрактов, live baseline и известные исходные ошибки |
| C01 | passed | Scoped tokens, owned portals, protected exact32/32; полнота accessibility отдельно в C14 |
| C02 | passed | Состояния/даты/единицы, zero/unknown; расчёты и enum не переименованы |
| C03 | passed | Очередь исполнителя и фильтры истории, URL-state, реальная навигация |
| C04 | passed | Выполнение/сдача/возврат/новая попытка, текстовый read-only и парные доказательства; E2E отдельно в регрессии |
| C05 | passed | Обязательное авторское основание до обеих CTA, документы отдельно, сохранённое решение читается; mobile shortcut |
| C06 | passed | Реальный подбор/сохранение бригады и planning→assignment в изолированных E2E; на старом стенде задания без equipment relation остаются blocked |
| C07 | passed | Технический обзор с исключениями, связями на конфигурацию и качество |
| C08 | passed | Секционный редактор, раскрытие ошибки, payload семи периодичностей, сохранение/reopen в QA |
| C09 | passed | Обзор и read-only результат директора, frontend/server запреты; подробный E2E в регрессии |
| C10 | passed | Calendar agenda/matrix, source obligations, keyboard region, preview scope |
| C11 | passed | Реестры/паспорт/отчётность, компактные строки, полный scope экспорта не изменён |
| C12 | passed | AI summary, limitations/cannot-confirm, раскрываемый rationale/provenance, forecast actions после методов |
| C13 | passed | Секции сотрудников/бригад/допусков, сохранение mounted drafts и permissions |
| C14 | blocked | 24 geometry и4text200 состояния, keyboard disclosures/Drawer прошли; полный ручной путь, OS keyboard, screen reader и фактический browser zoom не подтверждены |
| C15 | blocked | FULL просмотр четырёх anchor desktop/mobile, исправления и protected32/32; не все loading/error/empty/overlay имеют before/after FULL |
| C16 | blocked | Изолированные тесты прошли по [регрессии](REGRESSION.md); строгий release gate не закрыт из-за перечисленных обязательных пробелов |
| C17 | passed | Причина доказана: seed не создавал relation. Исправлены только новые записи, backend-тесты; исторические данные отдельно blocked |
| C18 | passed | Server-default адаптер sparse pattern, неизвестный формат не сохраняется; UI edit/reopen того же ID с revision+1 и неизменными интервалами |
| C19 | passed | Общие access/404 states понятнее, auth/protected без редизайна; роли/навигация проверены |

## Доказательства

- Frontend unit: **433 passed / 40 files**, default timeout сохранён, последовательный worker; `reports/redesign-v2/unit-final.log`.
- Полный backend/ML: **727 passed**,0failed/0skipped, Python3.12/PostgreSQL18; `reports/redesign-v2/c16-python-full.log`. До этого258целевых passed.
- Desktop E2E: **31 passed**, свежая изолированная БД; `reports/redesign-v2/e2e-final.log`.
- Mobile390: **1 passed** после последней правки истории, три реальные роли, source c5d4c65; `reports/redesign-v2/e2e-mobile-final.log`. Финальная сборка и TypeScript тестов passed.
- Protected: **32/32**, **0 changed pixels**; `reports/redesign-v2/protected-after-final-shared.json`.
- Archive: **1933/1933** файла идентичны ZIP, исходный SHA-256 `3bb8c395496581ce2e1727d2eaccb926698eac0ec9e91e0685b77fa7876a79ac`.
- Итоговые build/browser/mobile результаты — [REGRESSION](REGRESSION.md). [Визуальная матрица](VISUAL_QA.md), [реальные файлы и решения](IMPLEMENTATION_LOG.md), [контракты](CONTRACT_AUDIT.md), [настройки](SETTINGS_IMPLEMENTATION.md).

## История изменений

| Коммит | Содержание |
|---|---|
| `0aa9833` | Baseline и scoped theme |
| `4e2bf86` | Equipment relation новых seed-заданий |
| `34e9aa6` | Сохранённые смены и секционный регламент |
| `4c30324` | Выполнение/приёмка, доказательства/AI и календарь |
| `7943ca4` | Обзоры, назначение и read-only реестры |
| `715c591` | Select, text200 reflow, mobile переход к решению |
| `e44f033` | Измеренный контраст пояснений чек-листа |
| `d8a1fa8` | Контраст placeholder и границы инструкции |
| `c5d4c65` | История попыток: даты в часовом поясе объекта и подпись ракурса |
| `233323d` | Тест проверяет сохранение точного ID ответа повторного фотоанализа |
| `5aa8966` | Изолированные QA runners, mobile workflow и сохранённая смена |

QA runners, расширенные браузерные проверки и отчёты сохранены отдельными финальными commits; полный список: `git log --oneline frontend_polished..feat/frontend-redesign-v2`.

## Локальный запуск и безопасный возврат

Открыть `.worktrees/frontend-redesign-v2`. С установленными зависимостями из `frontend` выполнить `$env:VITE_DEMO_MODE='false'; npm.cmd run dev -- --host 127.0.0.1 --port 5174`. Vite использует существующий API proxy :8000. Это просмотр новой ветки поверх существующих данных, а не автоматическое развёртывание. Изолированные mutating проверки запускаются только через QA scripts, описанные в [REGRESSION](REGRESSION.md).

Возврат к стабильной версии не требует reset или удаления worktree: остановить только новый Vite и открыть прежний работающий :8000 либо исходное дерево `frontend_polished`. Read-only проверка прежнего `/api/health` после изменений вернула `status=ok,database=ready`; исходное дерево clean, merge-base совпал с исходным SHA. Для самостоятельной сборки старой версии использовать отдельный worktree от SHA `422eacf94aadf0fc75e29ef8b1ee110abce78bd2`. Не сбрасывать текущие незакоммиченные файлы, не восстанавливать старую БД поверх новых бизнес-событий. Код не требует новой миграции; пользовательские приёмки, фото и история кодовым откатом не отменяются.

Перед демонстрацией нового редизайна нужен выбор валидной equipment-linked fixture для назначения и ручная приёмка оставшихся обязательных сценариев доступности. Старый демонстрационный стенд сохраняется как доступная стабильная версия.
