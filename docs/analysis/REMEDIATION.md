# Исправление расхождений с аналитикой

Дата: 05.11.2026. Ветка: `dev`. Исходная версия: `1009c2f`.

Решения заказчика: по умолчанию квартал — +3 календарных месяца, выходной переносится на следующий рабочий день, 5/год отсчитывается от ввода. Каждому исходному ежедневному дню соответствует отдельное задание, даже если несколько дней перенесены на один понедельник. В эталоне TC02 30.09 +3 месяца = 30.12; 31.12 требует отдельной политики конца квартала. Исходники аналитика неизменяемы.

Публикуются только реальные настройки с полным комплектом обязательных нормативов. Неизвестные единицы, пределы и методики не заполняются демонстрационными значениями. Пункт 36 означает воспроизводимую загрузку исходных черновиков и проверку блокировки неполных настроек, а не выдуманный демонстрационный набор.

Статусы ниже означают фактическое состояние. «Запланировано» не является PASS. Ссылки на проверки добавляются после запуска.

| ID | Исправление | Состояние | Подтверждение |
|---|---|---|---|
| 01 | Четыре бизнес-роли | Реализовано; ПО проверено | Роли SQL/API и навигация; `test_four_business_roles_are_not_collapsed_into_administrator` |
| 02 | Права руководителя | Реализовано; ПО проверено | `test_executive_readonly_and_cross_site_overview_requires_membership` |
| 03 | Права главного инженера | Реализовано; ПО проверено | Публикация только chief; `test_real_norms_need_separate_chief_approval_and_templates_have_46_items` |
| 04 | Планирование и назначение инженером | Реализовано; ПО проверено | Реальный API назначения; `test_chief_handoff_keeps_the_original_attempt_and_releases_old_assignments` |
| 05 | Утверждение регламента и плана | Реализовано; ПО проверено | Версии/каталог; `test_background_calendar_uses_approved_catalog_and_is_restart_idempotent` |
| 06 | Обзор объектов руководителем | Реализовано; ПО проверено | Фильтр членства director; `test_executive_readonly_and_cross_site_overview_requires_membership` |
| 07 | Месячная матрица 1–31 | Реализовано; ПО проверено | 31 исходный день и переход месяца; `test_persisted_weekend_transfers_keep_all_source_dates_and_replay_without_duplicates` |
| 08 | Иерархия системы и оборудования | Реализовано; ПО проверено | API schedule-matrix и CalendarPage; браузерные settings/workspace-state |
| 09 | Связанные операции карточки | Реализовано; ПО проверено | Настройки M:N и EquipmentOperations; `tests/backend/test_management.py` |
| 10 | Ежедневное создание заданий | Реализовано; ПО проверено | Повтор/рестарт; `test_background_calendar_uses_approved_catalog_and_is_restart_idempotent` |
| 11 | Квартал и выходные | Реализовано; ПО проверено | `test_rolling_quarter_has_real_calendar_arithmetic_and_explicit_weekend_policy`; `test_accepted_completion_weekend_transfer_keeps_source_date_and_effective_deadline` |
| 12 | 5/год от ввода | Реализовано; ПО проверено | `test_five_per_year_starts_at_commissioning_and_crosses_new_year`; публикация требует реальной даты ввода |
| 13 | Окно ежедневной операции | Реализовано; ПО проверено | `test_early_start_rejected_before_new_report_is_created`; `test_daily_obligations_cannot_be_combined_or_made_rolling` |
| 14 | Уведомления и эскалации | Реализовано; ПО проверено | Собственные уведомления/403/404; `test_overdue_events_are_durable_and_late_acceptance_requires_chief` |
| 15 | История просрочек | Реализовано; ПО проверено | Один durable overdue audit; `test_overdue_events_are_durable_and_late_acceptance_requires_chief` |
| 16 | Разрешение поздней приёмки | Реализовано; ПО проверено | Разрешение конкретной попытки и неизменный deadline; `test_overdue_events_are_durable_and_late_acceptance_requires_chief` |
| 17 | Повторное открытие принятого | Реализовано; ПО проверено | `test_incident_execution_measurements_acts_acceptance_and_reopen_keep_history` |
| 18 | Переназначение в работе | Реализовано; ПО проверено | `test_chief_handoff_keeps_the_original_attempt_and_releases_old_assignments` |
| 19 | Фактическое время и трудозатраты | Реализовано; ПО проверено | Actual start/performed/person-hours; `test_incident_execution_measurements_acts_acceptance_and_reopen_keep_history` |
| 20 | Протокол измерений | Реализовано; ПО проверено | Число/единица/этап/оборудование; `test_incident_execution_measurements_acts_acceptance_and_reopen_keep_history` |
| 21 | Инструкция и нормы исполнителю | Реализовано; ПО проверено | Замороженная инструкция и нормы; `test_incident_execution_measurements_acts_acceptance_and_reopen_keep_history` |
| 22 | Аудит отказа назначения | Реализовано; ПО проверено | `test_failed_assignment_is_audited_without_creating_assignments` |
| 23 | Обращение по фото и тексту | Реализовано; ПО проверено | `test_incident_ai_unavailable_keeps_editable_draft_and_unknown_norms_block_task` |
| 24 | Редактор неполного AI-предложения | Реализовано; ПО проверено | Частичный результат и ручной binding; IncidentWorkspace, `test_incident_ai_unavailable_keeps_editable_draft_and_unknown_norms_block_task` |
| 25 | Диагностические данные прогноза | Реализовано; ПО проверено | ForecastSnapshot с cutoff; `tests/ml/test_aitunnel.py`, `tests/backend/test_orchestration.py` |
| 26 | Согласование раннего ТО | Реализовано; ПО проверено | `test_contract_stub_early_ai_requires_chief_and_keeps_original_obligation` (AI здесь явно контрактная фикстура) |
| 27 | Выбор решения инженером | Реализовано; ПО проверено | Тот же HTTP/SQL-сценарий: запрет поздней даты, исходное обязательство и идемпотентность |
| 28 | Показания и критерии фото | Реализовано; ПО проверено | OCR/protocol + item criteria; `tests/ml/test_local_vision.py`, реальный AN06 |
| 29 | Визуальные части 1.5/1.6 | Реализовано; ПО проверено | Видимые пункты 1.5/1.6; `tests/ml/test_local_vision.py`, реальные CASE-05/06 |
| 30 | Классификация фотоотчёта | Реализовано; ПО проверено | approved/manual_review/rejected; `backend/app/integration/photo_evidence.py`, AN06 9/9 |
| 31 | Качество снимка и ROI | Реализовано; ПО проверено | Нормализация/ROI/негативные фото; `tests/ml/test_local_vision.py`, реальные CASE-NEG-01..03 |
| 32 | Предпроверка и автоматический анализ | Реализовано; ПО проверено | Background/recovery/error persistence; `tests/backend/test_runtime_integration.py`, Compose с отключением ключа |
| 33 | Акты и инструментальные доказательства | Реализовано; ПО проверено | Загрузка/проверка/сохранение акта; `test_incident_execution_measurements_acts_acceptance_and_reopen_keep_history` |
| 34 | SLA и загрузка | Реализовано; ПО проверено | Точные actual/norm/SLA/load после HTTP-приёмки; `test_incident_execution_measurements_acts_acceptance_and_reopen_keep_history` |
| 35 | XLSX-экспорт | Реализовано; ПО проверено | HTTP XLSX двух видов и запрет executor; тот же lifecycle-тест + `test_xlsx_is_real_xml_workbook_and_formula_text_stays_text` |
| 36 | Реальные начальные настройки | Частично; реальные данные BLOCKED | Защита публикации PASS; реальные методики, единицы и пределы владельцем не утверждены |
| 37 | Девять AN06 и сквозная приёмка | Частично; приёмка заказчика BLOCKED | AN06 9/9 PASS; API/БД/два настоящих cloud-инструмента Compose PASS; полный E2E шести операций BLOCKED из-за п.36 |

## Фактические проверки

Полная регрессия `verify-20261105-231334-9adba336`: 29/29 этапов, 713 Python / 301 UI / 31 browser E2E, npm audit 0. Временная PostgreSQL 18.6: чистая 001–009, заполненный upgrade и сохранение истории. Не используются ключи облака и рабочая БД.

Контейнерный прогон `compose-20261105-231641-f9b63626`: 92/92 проверок, настоящий AI Tunnel/Qwen3.7 Flash для обоих инструментов, controlled unavailable при отключённом ключе, fallback, повтор, приёмка и восстановление после restart. Это изолированные TEST-настройки, не утверждённые нормативы шести операций.

Фото AN06 `20261105T175820Z`: 9/9 по явно пересмотренной консервативной политике. Исходные ожидания и MATCH/DIFF сохранены; CASE-01 содержит разные приборы. [Опубликованная сводка](../../reports/analyst_photos.md).

Основные программные проверки: [аналитические workflows](../../tests/backend/test_analyst_workflows.py), [назначения](../../tests/backend/test_assignment_save.py), [календарь](../../tests/backend/test_scheduling.py), [роли](../../tests/backend/test_roles_contracts.py), [AI Tunnel](../../tests/ml/test_aitunnel.py). [Вердикт приёмки](../../reports/final_acceptance.md).

Пункты 36–37 нельзя объявлять завершёнными: пользователь явно подтвердил, что реальные методики и нормативы не утверждены. Код не заполняет их демонстрационными значениями. Для полного customer E2E нужны утверждённые исходные настройки и реальные доказательства по ним.

## Уточнение проверки ролей, 06.11.2026

Повторный разбор выявил пробелы п.01/03: прежние браузерные проверки прямых URL не обнаруживали отсутствующие ссылки новых ролей; наследование dispatcher разрешало engineer менять оборудование/структуру. Меню переведено на SECTION_ROLES; независимые ожидаемые наборы ссылок проверяются unit-тестами и реальным браузером. Изменение каталога проверяет точную роль, включая повторную проверку членства под блокировкой; новый HTTP/PostgreSQL-тест запрещает engineer создание/правку и разрешает chief_engineer. Это исправление прежнего покрытия, а не утверждение, что эти условия уже проверялись 05.11.
