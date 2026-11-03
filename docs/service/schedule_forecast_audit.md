# Аудит регламентного графика и двух прогнозов

Дата: 03.11.2026. Ветка: `qa/schedule-forecast-tests` (от `origin/feature/frontend-next`, `3e95724`).
Зависимости: QA03, ALG02, ALG03, ML03.

Цель — до интеграции проверить построение регламентного графика для шести исходных
операций, границы месяцев/кварталов, отсутствующие даты, пересчёт просрочек,
невозможное назначение, нормо-часы, а также контракт двух прогнозов и поведение
оркестратора при отсутствии или низкой уверенности AI.

Проверки выполняются чистыми функциями без БД и без реального RF/CLIP inference.
Это unit/contract-аудит: он доказывает соблюдение документированной политики и
воспроизводимость дефектов, но не заменяет PostgreSQL/HTTP и браузерный прогон.

## 1. Политика эталонных дат

Эталонные даты не являются предположением тестировщика. Для каждой операции
выбрана явная политика из `docs/service/planning.md` и фикстур предметной области.

| Операция | Политика | Эталон | Источник |
|---|---|---|---|
| 1.1–1.3, 1/день | `calendar_interval`, day/1, `fixed_calendar`, `allowed_lead_days=0` | 31 дата октября 2026 | planning.md, «Действие, история и обязательный срок»; TC-01 |
| 1.4, 5/год | `calendar_pattern` → `yearly_count`, `count_per_year=5`, anchor 2026-01-01 | 2026-01-01, 03-15, 05-27, 08-08, 10-20; в октябре — 10-20 | planning.md, «Эталонные календарные сценарии»; TC-04 |
| 1.5, 1/квартал | реальные календарные кварталы, `period_edge=end` | 2026-12-31 | planning.md; TC-02 |
| 1.6, 1/квартал | `month`/3 от `2026-07-04` (фаза исходного anchor) | 2026-10-04, 2027-01-04 | planning.md; TC-03 |
| 1.4, численность | `required_workers=2` | полная бригада из 2 человек | `tests/fixtures/domain/maintenance_operations.json` |

Дополнительно зафиксированы:

- `yearly_count` распределяет `floor(i * eligible_days / count_per_year)` по
  допустимым дням реального года; `anchor_date` — начало действия правила, даты
  до anchor не заполняются задним числом.
- `quarter` — реальный квартал, а не «каждые три месяца от даты»; `month/3` —
  именно интервал от anchor.
- короткий месяц: `short_month=skip` не создаёт дату, `last_day` переносит на
  последний день.
- `calendar_interval` day/1 требует `fixed_calendar` и нулевой lead; общий
  `CalendarPattern` использует явно заданный `allowed_lead_days` (planning.md,
  строка 39), поэтому ненулевой lead у `calendar_pattern` не считается дефектом.
- нормо-часы: `person_hour` — норма на человека, `elapsed_hour` — норма на
  бригаду; плановая трудоёмкость — `crew_size × duration_minutes`, а не норма.

## 2. Матрица проверок

Все команды запускаются из корня worktree:

```powershell
& 'C:\Users\admin52\Desktop\fixrate_ai\.venv\Scripts\python.exe' -m pytest tests/backend/test_schedule_audit.py -q
& 'C:\Users\admin52\Desktop\fixrate_ai\.venv\Scripts\python.exe' -m pytest tests/backend/test_assignment_audit.py -q
& 'C:\Users\admin52\Desktop\fixrate_ai\.venv\Scripts\python.exe' -m pytest tests/backend/test_forecast_audit.py -q
& 'C:\Users\admin52\Desktop\fixrate_ai\.venv\Scripts\python.exe' -m pytest tests/backend -q
```

Результат на 03.11.2026:

| Набор | Итог |
|---|---|
| `test_schedule_audit.py` | 21 passed, 1 xfailed (BUG-04) |
| `test_assignment_audit.py` | 7 passed |
| `test_forecast_audit.py` | 13 passed, 4 xfailed (BUG-01, BUG-02, BUG-03, BUG-05) |
| весь `tests/backend` | 305 passed, 129 skipped, 5 xfailed |

`xfail(strict=True)` — намеренно падающий тест, фиксирующий дефект. Если дефект
исправят, тест начнёт проходить и strict-xfail станет ошибкой: это заставит
обновить отчёт, а не потерять регрессию.

### 2.1. `tests/backend/test_schedule_audit.py` (ALG02)

| Проверка | Что доказывает |
|---|---|
| `test_six_source_operations_have_reproducible_dates` | 1.1–1.3 дают 31 дату октября; 1.4 — 10-20; 1.5 — 12-31; 1.6 — 10-04; численность 1.4 равна 2; при неизвестной норме итоги не выдумываются |
| `test_1_4_yearly_count_uses_the_documented_even_distribution` | ровно 5 дат за 2026 год, интервалы отличаются не более чем на день |
| `test_1_4_requires_two_workers_in_the_operation_contract` | контракт операции 1.4: `5/год`, 2 работника, норма 60.0 |
| `test_quarter_boundaries_are_real_calendar_quarters` | конец и начало реальных кварталов, включая 2027-03-31 |
| `test_month_interval_three_keeps_phase_across_the_year_boundary` | `month/3` сохраняет фазу 4-го числа через границу года |
| `test_yearly_count_anchor_is_a_rule_start_and_is_not_backfilled` | до anchor даты отсекаются, следующий полный год снова даёт 5 |
| `test_explicit_annual_dates_do_not_leak_into_the_next_year` | 2027 без явных дат → `YEAR_DATES_MISSING`, без вхождений и часов |
| `test_yearly_count_reports_unsatisfiable_season_instead_of_reducing_count` | невозможный сезон → `CALENDAR_PATTERN_UNSATISFIABLE`, count не уменьшается молча |
| `test_short_month_skip_is_explicit_and_does_not_create_a_date` | февраль при `short_month=skip` не получает дату |
| `test_empty_month_reports_missing_norm_inputs_instead_of_zero_values` | пустой месяц сохраняет диагностики `NORM_UNIT_UNCONFIRMED` и `DURATION_UNCONFIRMED` |
| `test_empty_month_does_not_report_zero_when_norm_is_unknown` | **xfail BUG-04**: пустой месяц не должен давать 0 часов при неизвестной норме |
| `test_deadline_passed_is_recalculated_at_local_midnight_without_new_ids` | просрочка пересчитывается на локальной полуночи, ID вхождений стабильны |
| `test_overdue_rolling_obligation_requires_review_and_is_not_rescheduled` | `after_accepted_completion`: просроченный срок → `manual_review`/`OVERDUE_REQUIRES_REVIEW`, без переноса |
| `test_1_4_norm_hours_use_the_declared_unit_and_crew_size` | `person_hour` → 60.0, `elapsed_hour` → 120.0 для бригады из 2 |
| `test_1_4_planning_minutes_are_crew_size_times_duration` | 2 × 90 = 180 чел.-мин, при этом нормо-часы остаются `None` |
| `test_daily_norm_hours_sum_all_occurrences_without_merging_ids` | 31 × 1.0 = 31.0, 31 уникальный ID |

### 2.2. `tests/backend/test_assignment_audit.py` (ALG03)

| Проверка | Что доказывает |
|---|---|
| `test_operation_1_4_contract_requires_two_workers` | 1.4 требует 2 работников; команда содержит ровно двух; 120 чел.-мин |
| `test_one_worker_cannot_be_doubled_for_operation_1_4` | один работник не превращается в бригаду: `INSUFFICIENT_CAPACITY`, команды нет |
| `test_two_workers_without_a_common_interval_do_not_form_a_team` | разные интервалы без пересечения не образуют полную бригаду |
| `test_unqualified_or_expired_member_blocks_the_complete_team` | отсутствующая и просроченная квалификация дают явные причины, команды нет |
| `test_passed_deadline_requires_manual_review_without_a_partial_command` | прошедший срок → `manual_review`/`DEADLINE_EXCEEDED`, без частичной команды |
| `test_unknown_duration_does_not_turn_norm_hours_into_a_duration` | неизвестная длительность → `needs_input`/`DURATION_UNCONFIRMED`, не подменяется нормой |
| `test_requested_two_person_team_is_revalidated_without_substitution` | запрошенная бригада перепроверяется, но не заменяется третьим работником |

### 2.3. `tests/backend/test_forecast_audit.py` (ML03/ALG04)

| Проверка | Что доказывает |
|---|---|
| `test_both_forecasts_share_snapshot_hash_run_and_due_date_without_mutation` | одинаковые snapshot ID/hash/run_id/срок; snapshot не мутирует; result_id разные |
| `test_ai_unavailable_and_low_confidence_fall_back_to_the_confirmed_rule` | AI unavailable/needs_input → `fallback` на регламент |
| `test_calibrated_early_ai_date_is_selected_on_customer_data` | калиброванный интервал с верхней границей раньше регламента → `selected` |
| `test_uncalibrated_early_ai_date_falls_back_on_customer_data` | tree dispersion без калибровки не является доказательством |
| `test_ai_after_the_mandatory_due_date_is_kept_but_not_selected` | допустимый ответ AI сохраняется, но не выбирается; `fallback` |
| `test_ai_before_the_window_is_not_selected` | дата до окна → `fallback` |
| `test_foreign_snapshot_identity_is_a_terminal_ai_failure` | чужой snapshot → `AI_SNAPSHOT_MISMATCH`, затем `fallback` |
| `test_ai_cannot_replace_the_mandatory_due_date` | подмена срока → `AI_SNAPSHOT_MISMATCH` |
| `test_snapshot_hash_is_rechecked_before_any_calculation` | подмена hash → `ValueError` до расчёта |
| `test_synthetic_demo_early_date_is_selected_with_an_explicit_demo_reason` | synthetic_demo ранняя дата разрешена с `DEMO_EARLY_DATE` |
| `test_missing_confirmed_rule_requires_input_and_ai_cannot_replace_it` | неподтверждённое правило → `needs_input`, AI не заменяет |
| `test_passed_deadline_requires_manual_review_even_with_a_valid_ai_date` | прошедший срок → `manual_review` |
| `test_mismatched_result_identity_requires_manual_review` | разные идентичности результатов → `manual_review` |
| `test_unknown_uncertainty_is_not_early_evidence` | **xfail BUG-01** |
| `test_tampered_earlier_algorithmic_date_is_not_trusted` | **xfail BUG-02** |
| `test_ai_overdue_flag_is_recomputed_from_the_snapshot` | **xfail BUG-03** |
| `test_synthetic_demo_early_date_is_allowed_with_unknown_uncertainty` | **xfail BUG-05** |

## 3. Найденные дефекты

### BUG-01. Неизвестная уверенность принимается как доказательство раннего срока

- **Тест:** `test_forecast_audit.py::test_unknown_uncertainty_is_not_early_evidence` (xfail strict).
- **Политика:** planning.md, строки 403–405: неизвестная уверенность и разброс деревьев не являются калиброванной оценкой.
- **Шаги воспроизведения:**
  1. Собрать snapshot с `data_origin="customer"`, сроком 2026-11-10, as_of 2026-11-01.
  2. Вернуть AI-результат с `recommended_date=2026-11-05` и `Uncertainty(kind="unknown", lower_date=upper_date=2026-11-05, calibrated=True)`.
  3. Вызвать `bounded_ai` и `decide`.
- **Фактически:** `bounded_ai` принимает результат, `decide` возвращает `selected` с датой 2026-11-05 и причиной `AI_EARLY_EVIDENCE`.
- **Ожидалось:** `fallback` на 2026-11-10 с `AI_EARLY_UNSUPPORTED`.
- **Root cause:** `backend/app/orchestrator/decision.py`, строки 43–47: условие `supported` проверяет только `calibrated` и границы, но не `kind`. Схема `Uncertainty` запрещает `tree_dispersion + calibrated`, однако `unknown + calibrated` проходит.
- **Влияние:** заказчику можно выбрать более раннюю дату без валидного доказательства; это нарушает ключевое правило безопасности.
- **Предлагаемое исправление:** требовать `evidence.kind == "deterministic"` для `supported`; `unknown` и `tree_dispersion` не должны попадать в ветку доказательства. Дополнительно запретить `calibrated=True` для `unknown` в схеме.

### BUG-02. Оркестратор доверяет подменённой ранней дате алгоритмического результата

- **Тест:** `test_forecast_audit.py::test_tampered_earlier_algorithmic_date_is_not_trusted` (xfail strict).
- **Политика:** planning.md, строки 386–390 и 399–402: алгоритмический метод вызывает настоящий ALG02 и не использует сохранённую дату как замену расчёту; при недоступном AI выбирается подтверждённый регламент.
- **Шаги воспроизведения:**
  1. Получить корректный `algorithmic_forecast` с датой 2026-11-10.
  2. Заменить `recommended_date` на 2026-11-05 (внутри окна, но раньше регламента).
  3. Передать AI-результат `unavailable`.
  4. Вызвать `decide`.
- **Фактически:** `decide` возвращает `fallback` с датой 2026-11-05.
- **Ожидалось:** использовать реальную регламентную дату 2026-11-10 либо отклонить результат как несоответствующий расчёту.
- **Root cause:** `decision.py`, строки 31–33 проверяют только `day > due`, `day < today` и `day < earliest`. Идентичность результата проверяется, но не его происхождение/соответствие генератору. `algorithmic_forecast` сам по себе корректен; дефект проявляется при повреждённом или подменённом DTO.
- **Влияние:** defense-in-depth: при ошибке сериализации, кэша или интеграции можно выбрать дату, которую ALG02 не выдавал.
- **Предлагаемое исправление:** в `decide` (или перед ним) перепроверять `recommended_date` по `generate_month` для этого snapshot, либо включить в результат проверяемый `method_version` + digest входа и сверять его. Как минимум не принимать algorithmic-дату, если она не совпадает с повторным расчётом.

### BUG-03. `bounded_ai` доверяет полю `overdue` от AI

- **Тест:** `test_forecast_audit.py::test_ai_overdue_flag_is_recomputed_from_the_snapshot` (xfail strict).
- **Политика:** planning.md, строки 392–395: JSON и идентичность входа проверяются на границе; просрочка определяется по сроку и as_of, а не заявлением модели.
- **Шаги воспроизведения:**
  1. Snapshot: срок 2026-11-10, as_of 2026-11-01 (срок в будущем).
  2. Вернуть AI-результат с `overdue=True`.
  3. Вызвать `bounded_ai`.
- **Фактически:** результат принимается со статусом `ok` и `overdue=True`.
- **Ожидалось:** `overdue=False` (пересчёт из snapshot) или отклонение `AI_SNAPSHOT_MISMATCH`.
- **Root cause:** `backend/app/orchestrator/forecast.py`, строки 80–86: проверяются method/snapshot/hash/binding/equipment/as_of/origin/due, но `overdue` и `recommended_date` не сверяются с snapshot.
- **Влияние:** ложная просрочка может запустить ручной разбор или неверную приоритизацию; ложное `False` может скрыть просрочку.
- **Предлагаемое исправление:** после валидации пересчитывать `overdue` из `snapshot.mandatory_due_date` и локальной даты `as_of`, не доверяя полю провайдера.

### BUG-04. Пустой месяц возвращает 0 часов при неизвестной норме/длительности

- **Тест:** `test_schedule_audit.py::test_empty_month_does_not_report_zero_when_norm_is_unknown` (xfail strict).
- **Политика:** planning.md, строки 109–113: норма без подтверждённой единицы не становится ни минутами, ни часами; отсутствующие данные не выдумываются.
- **Шаги воспроизведения:**
  1. Взять операцию 1.4 с `norm_unit="unconfirmed"`, `planning_duration_minutes=null`.
  2. Запросить месяц без вхождений, например ноябрь 2026 для `yearly_count` с датами в другие месяцы.
  3. Прочитать `total_person_hours` и `total_planning_person_minutes`.
- **Фактически:** `Decimal("0")` и `0`, хотя в warnings есть `NORM_UNIT_UNCONFIRMED` и `DURATION_UNCONFIRMED`.
- **Ожидалось:** `None` для обоих итогов, как в непустом месяце с неизвестной нормой.
- **Root cause:** `backend/app/scheduling/generator.py`, строки 66–79: `all(...)` по пустому списку истинно, поэтому `sum([])` даёт 0. Условие не требует наличия хотя бы одного вхождения.
- **Влияние:** 0 выглядит как подтверждённый расчёт и может быть просуммирован в отчётах, хотя данных нет.
- **Предлагаемое исправление:** требовать `entries` перед суммированием: `if known_dates and entries and all(...)`, иначе `None`.

### BUG-05. synthetic_demo ранняя дата отклоняется при `uncertainty.kind="unknown"`

- **Тест:** `test_forecast_audit.py::test_synthetic_demo_early_date_is_allowed_with_unknown_uncertainty` (xfail strict).
- **Политика:** planning.md, строки 406–407: для `synthetic_demo` ранний срок внутри окна допускается с явным объяснением, что это демонстрация и точность на заказчике не установлена. Ограничение про неизвестную уверенность в строках 403–405 относится к данным заказчика.
- **Шаги воспроизведения:**
  1. Собрать snapshot с `data_origin="synthetic_demo"`, сроком 2026-11-10.
  2. Вернуть AI-результат `status="ok"`, `recommended_date=2026-11-05` без явной `uncertainty` (по умолчанию `forecast_result` ставит `kind="unknown"`).
  3. Вызвать `bounded_ai` и `decide`.
- **Фактически:** `fallback` на 2026-11-10 с `AI_EARLY_UNSUPPORTED`.
- **Ожидалось:** `selected` с 2026-11-05 и `DEMO_EARLY_DATE`, поскольку демо-ветка не опирается на калиброванное доказательство.
- **Root cause:** `decision.py`, строка 46: `demo = snapshot.data_origin == "synthetic_demo" and evidence.kind != "unknown"`. Условие `kind != "unknown"` ошибочно применено и к демо-ветке.
- **Влияние:** демонстрационный сценарий не воспроизводит документированное поведение, если провайдер не прислал явную уверенность. Это также скрывает разницу между «нет доказательства» и «демо-режим».
- **Предлагаемое исправление:** для `synthetic_demo` разрешать раннюю дату независимо от `kind`, оставив проверку окна и явную причину `DEMO_EARLY_DATE`. Для `customer` оставить строгую проверку калиброванного интервала и отдельно запретить `unknown`.

## 4. Что дефектом не является

- `calendar_pattern` с `frequency="day"` и ненулевым `allowed_lead_days` разрешён политикой (planning.md, строка 39). Отдельный суточный guard относится только к исходному `calendar_interval` day/1.
- `isOverdue=False` у draft-вхождений preview согласован с существующим тестом `test_runtime_integration.py`; просрочка задания считается по сохранённому сроку, а не по черновику.
- `quarter` с anchor в середине квартала начинает с первого активного квартала — это соответствует политике, а не ошибке.
- 129 skipped в полном прогоне — отсутствие PostgreSQL и ML-артефактов, а не падения.

## 5. Ограничения аудита

- Проверялись чистые функции `generate_month`, `select_crew`, `algorithmic_forecast`, `bounded_ai`, `decide`; HTTP-адаптеры, БД, блокировки, CSRF, роли и сохранение в `work_orders`/`schedule_entries` не входят в этот набор.
- Реальный RF/CLIP inference не запускался: тесты проверяют протокол и политику, а не качество модели на данных заказчика.
- Эталонные даты привязаны к выбранной документированной политике. Для 1.6 возможна и альтернативная политика реальных кварталов; она проверяется отдельно, и тесты не выводят одну политику из другой.
- `BUG-02` — дефект доверия к DTO, а не ошибка самого ALG02. Он важен для защиты от повреждённых/кэшированных результатов, но не проявляется при штатном вызове `compare_forecasts`.
- `BUG-05` — расхождение реализации с политикой для демо-режима; если продукт сознательно требует явную `uncertainty` даже в демо, политику нужно уточнить в planning.md, а тест — переклассифицировать.

## 6. Воспроизведение

```powershell
cd C:\Users\admin52\Desktop\fixrate_ai_alg
& 'C:\Users\admin52\Desktop\fixrate_ai\.venv\Scripts\python.exe' -m pytest `
  tests/backend/test_schedule_audit.py `
  tests/backend/test_assignment_audit.py `
  tests/backend/test_forecast_audit.py -q
```

Ожидаемый итог: 41 passed, 5 xfailed. Полный прогон `tests/backend` — 305 passed,
129 skipped, 5 xfailed. Пять xfailed соответствуют BUG-01…BUG-05 и не маскируются:
strict-режим превратит их в ошибку после исправления, требуя обновить отчёт.
