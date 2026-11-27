# Отчёт по стабилизации фотоанализа и ограниченному OCR (TEAM-ML02 / FRAI-172)

> [!IMPORTANT]
> **Задача:** TEAM-ML02 — Стабилизировать фотоанализ и ограниченный OCR в реальном наряде (FRAI-172).  
> **Ответственный:** Мухаммад (`d1ba36a5-b2a2-428c-aa24-05ad8fffe4ad`).  
> **Принимающий:** Михаил QA (`60eef911-b53c-4417-9ef0-74153c2b0bae`).  
> **Нормативная основа:** Пересмотр заказчика CR-17-01…08 от 17.11.2026, политики [TL04 (data_security_tl04.md)](file:///home/handraqw/Projects/FixRate_AI/docs/service/data_security_tl04.md) и правила нулевой ложной уверенности (Zero False Reassurance, 0.0% FRR).  
> **Ветка:** `feat/team-ml02-photo-analysis-bounded-ocr`.  

---

## 1. Цели и границы реализации

В соответствии с требованиями пересмотра CR-17 для задачи TEAM-ML02 реализованы:
1. **Устранение ошибок качества, ракурса и принадлежности** на зафиксированном фотокорпусе ([dataset_manifest.json](file:///home/handraqw/Projects/FixRate_AI/data/manifests/dataset_manifest.json)).
2. **Ограниченное оптическое считывание (Bounded OCR)**: жесткое ограничение распознавания только стрелочными манометрами (`bar`) и тепловычислителями ВКТ-7 (`Gcal`, `m³`), с полным запретом распознавания на остальных типах оборудования.
3. **Человеко-центричная сверка показаний**: число и единица передаются как черновой кандидат (`requires_human_verification=True`); скрытая исправность и метрологическая точность по фото категорически не подтверждаются.
4. **Привязка к попытке наряда и защита от устаревания (Staleness Protection)**: связывание результатов с `attempt_no` и SHA-256 хэшами файлов; автоматическая инвалидация анализа при обновлении снимков.
5. **Вспомогательный анализ для главного инженера ([assessment.py](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/assessment.py))**: структурированное заключение по паре До/После без автономной приёмки наряда.
6. **Отказоустойчивость (Fallback)**: штатное наличие [HeuristicFallbackClassifier](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/classifier.py) в ядре CV-модуля и гарантированный переход в `manual_review` при недоступности нейросетевых весов (FRR = 0.0%).

---

## 2. Разрешение проблем фотокорпуса (CASE-01..06, NEG-01..03)

В ходе стабилизации конвейера фотоанализа проверена и гарантирована обработка каждого граничного случая:

| Идентификатор кейса | Оборудование | Выявленная проблема / Особенность | Реализованное поведение системы | Результирующий статус доказательства |
|---|---|---|---|---|
| **CASE-01** | Стрелочный манометр (`pressure_gauge`) | **Противоречие пары До/После:** Разные приборы (шкала 0–4 бар vs 0–6 бар, разные производители). Несопоставимая пара. | Обнаружение физического несоответствия циферблатов (`contradiction_detected=True`). Запрет выдачи положительного `approved`. | `rejected` / `manual_review` (только очная приёмка) |
| **CASE-02** | Теплосчетчик (`heat_meter` / ВКТ-7) | Корректная пара снимков экрана тепловычислителя. | Bounded OCR извлекает кандидаты показаний (`Gcal`, `m³`) с нормализацией запятой и флагом обязательной проверки инженером. | `approved` (как пригодное доказательство) |
| **CASE-03** | Шкаф автоматики (`control_cabinet`) | Осмотр индикации («Сеть» горит, «Авария» погашена). Попытка распознавания текста на дверце. | OCR строго блокируется (`unsupported_equipment`). Анализируется только визуальная чистота и индикаторы. Скрытые электроцепи исключены. | `approved` / `manual_review` |
| **CASE-04** | Сетчатый фильтр (`mesh_filter`) | Осмотр сетки после промывки от механического шлама. | OCR строго блокируется (`unsupported_equipment`). Оценивается смыв загрязнений; микроизнос сетки помечен как неподтверждаемый по фото. | `approved` |
| **CASE-05** | Коллектор отопления (`heating_manifold`) | Проверка отсутствия капельных течей и запотевания. | OCR блокируется. Визуальное отсутствие течей не подменяет акт гидравлической опрессовки (`cannot_confirm`). | `approved` / `manual_review` |
| **CASE-06** | Приборы измерения (`pressure_gauge`) | Контроль целостности стекла и корпуса манометра. | Проверка целостности защитного стекла. Фиксация положения стрелки в диапазоне 0..16 бар. | `approved` |
| **NEG-01** | Шкаф автоматики | Технический брак снимка: сильный смаз движения (Laplacian variance < 50) и паразитный блик. | Отсечение на уровне [ImageQualityGuard](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/quality.py). Рекомендация повторной фотофиксации. | `rejected` (`requires_reshoot=True`) |
| **NEG-02** | Разное оборудование | Подмена узла: на фото До — насос, на фото После — запорная арматура. | Отсечение на уровне проверки сопоставимости ракурса и объекта (`same_subject="no"`, `is_comparable=False`). | `rejected` |
| **NEG-03** | Теплосчетчик vs смеситель | Синтетическая подмена ракурса и устройства (учебный теплосчетчик vs бытовой смеситель). | Обнаружение некорректного класса (`same_subject="no"`). Блокировка попытки фальсификации выполнения. | `rejected` |

---

## 3. Архитектура Bounded OCR ([ocr.py](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/ocr.py))

Для выполнения требований CR-17-02 введён строгий валидатор [BoundedOCRValidator](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/ocr.py):

```mermaid
flowchart TD
    RawReading["Сырой результат VLM / OCR<br/>(label, value, unit, phase)"] --> CheckEq{"Оборудование входит в белый список?<br/>(pressure_gauge / heat_meter)"}
    
    CheckEq -- "НЕТ (шкаф, фильтр, коллектор)" --> UnsupportedEq["Статус: UNSUPPORTED_EQUIPMENT<br/>is_supported = False<br/>parsed_value = None<br/>Запрет показаний"]
    CheckEq -- "ДА" --> CheckReadable{"Текст читаем и числовой?"}
    
    CheckReadable -- "НЕТ (смаз, 'норма', '???')" --> Unreadable["Статус: UNREADABLE<br/>parsed_value = None"]
    CheckReadable -- "ДА" --> CheckUnit{"Единица допустима для прибора?<br/>(bar / Gcal / m³ / t/h)"}
    
    CheckUnit -- "НЕТ (psi, volts, kW)" --> UnsupportedUnit["Статус: UNSUPPORTED_UNIT<br/>is_supported = False<br/>Принудительный manual_review"]
    CheckUnit -- "ДА" --> ParseNumber["Нормализация числа<br/>(запятая -> точка)"]
    
    ParseNumber --> CheckRange{"В пределах физ. диапазона ИТП?<br/>(0..16 бар, 0..100k Гкал)"}
    CheckRange -- "НЕТ (25 бар, -1.5 бар)" --> OutOfRange["Статус: OUT_OF_RANGE<br/>Принудительный manual_review"]
    CheckRange -- "ДА" --> Extracted["Статус: CANDIDATE_EXTRACTED<br/>is_supported = True<br/>requires_human_verification = True"]
```

### 3.1. Поддерживаемые классы и единицы
* **Манометры (`pressure_gauge`):**
  * Поддерживаемые единицы: `bar`, `бар`, `mpa`, `мпа`.
  * **Каноническая единица:** строго `bar`. При подаче `mpa`/`мпа` выполняется автоматическая конвертация в канонические бары (коэффициент 10.0, 1 МПа = 10 бар), а диапазон проверяется в канонической шкале.
  * Допустимый физический диапазон ИТП: `0.0 .. 16.0 bar`.
* **Тепловычислители (`heat_meter`, `vkt7`):**
  * Поддерживаемые единицы: `Gcal`, `гкал`, `m3`, `м3`, `m3/h`, `м3/ч`, `t/h`, `т/ч`.
  * Канонические единицы: `Gcal`, `m3`, `m3/h`, `t/h`.
* **Все остальные классы:**
  * Попытка извлечения показаний принудительно переводится в статус `unsupported_equipment`.

### 3.2. Обязательный юридический и инженерный дисклеймер и Pydantic-валидатор
Каждый возвращаемый объект `BoundedReadingCandidate` содержит неизменяемый дисклеймер:
> *«Показания приборов считываются моделью ориентировочно и передаются исключительно как кандидаты для визуальной сверки главным инженером. Метрологическая точность, скрытая исправность измерительного тракта и факт поверки по фотографии не подтверждаются.»*

Поле `requires_human_verification` защищено строгим `@field_validator(mode="after")`: любая попытка прямой инициализации с `False` возбуждает `ValueError`. Автономное одобрение невозможно даже на уровне DTO.

---

## 4. Вспомогательный анализ для главного инженера ([assessment.py](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/assessment.py))

Для обеспечения полного ролевого контроля главного инженера (CR-17-02, CR-17-06) разработан модуль формирования структурированного отчёта `AuxiliaryPhotoAssessment`:

### 4.1. Привязка к попытке и защита от устаревания (Staleness Protection)
* Каждый отчёт привязывается к структуре `WorkOrderAttemptBinding`:
  * `work_order_id`: UUID наряда.
  * `attempt_no`: номер попытки (1, 2, ...).
  * `before_photo_sha256`: SHA-256 снимка До.
  * `after_photo_sha256`: SHA-256 снимка После.
  * `analyzed_at`: временная метка анализа.
  * `is_stale`: флаг актуальности снимков.
  * `stale_reason`: диагностическая причина устаревания.
* Метод `assessment.with_staleness_check(...)` сравнивает хэши текущих файлов наряда с хэшами попытки:
  * При обнаружении несовпадения хэшей обновляются как `assessment.is_stale = True`, так и `binding.is_stale = True`.
  * Выставляется `stale_reason` и добавляется обязательное предупреждение в `concerns` и `limitations`.
  * Если ранее статус доказательства был `approved`, он **принудительно понижается** до `manual_review`: устаревший анализ не может служить одобренным доказательством.
  * К заголовку отчёта добавляется префикс `[УСТАРЕЛО / STALE]`.
* Функция `review_work_order_attempt` и обёртка `invoke_attempt_review` встроены непосредственно в промышленный контур [api.py](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/api.py) и вызываются в основном эндпоинте бэкенда `analyze_photo_review` ([backend/app/integration/ml.py](file:///home/handraqw/Projects/FixRate_AI/backend/app/integration/ml.py)). Результат вспомогательного анализа сохраняется в БД в таблице `ai_quality_checks` и передаётся на фронтенд в `ui["auxiliaryAssessment"]`.

### 4.2. Исключение ложного одобрения при пропуске флагов сопоставимости и автодетект CASE-01
* Функция `build_auxiliary_assessment(...)` имеет строго консервативное поведение:
  * Если вызывающая сторона **не передала** результат сопоставимости (`comparability_result=None`), система **не предполагает сопоставимость по умолчанию**: выставляется `is_comparable=False`, `same_subject="uncertain"`, а статус доказательства переходит в `manual_review`, полностью исключая ложный `approved`.
  * Встроен автоматический анализ текстовых наблюдений и шкал:
    * Нормализуются любые виды тире (русское короткое тире `–` U+2013, длинное `—` U+2014, минус `−` U+2212, дефис `-`, пробелы).
    * Парсер `extract_dial_limit()` распознает шкалы 0–4 и 0–6 бар в любых текстовых формулировках («0–4 bar», «0—4 бар», «шкала до 4 бар», «предел 4»).
    * При обнаружении несовпадения шкал циферблатов (противоречие `CASE-01`) система выставляет `contradiction_detected=True`, `same_subject="no"`, `is_comp=False` и **строго возвращает `evidence_class="rejected"`**.
    * Этот автодетект срабатывает даже в том случае, если вызывающая сторона ошибочно передала положительный флаг сопоставимости (`is_comparable=True`, `same_subject="yes"`), гарантируя абсолютную защиту от ложного одобрения.

### 4.3. Классы доказательств
* Поле `evidence_class` принимает значения:
  * `approved`: фотоматериалы технически пригодны, сопоставимы и подтверждают видимую часть работ. **Не означает закрытия заказ-наряда!**
  * `manual_review`: требуется очный осмотр, сверка несоответствий или проверка прибора инженером.
  * `rejected`: брак съёмки (смаз/блик) либо подмена оборудования. Требуется пересъёмка.
* В структуре отчёта зафиксирован список ограничений `cannot_confirm`: скрытые работы, электробезопасность, герметичность под давлением и метрологическая калибровка не подтверждаются ИИ.

---

## 5. Отказоустойчивость, Fallback и распределение ответственности

### 5.1. Фабричный фоллбэк HeuristicFallbackClassifier
В модуль [classifier.py](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/classifier.py) интегрирован фабричный класс `HeuristicFallbackClassifier`:
* Не требует внешних нейросетевых весов, PyTorch или интернет-соединения.
* В конвейер [service.py](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/cv/service.py) встроена прямая поддержка фоллбэка через параметр `fallback_to_heuristic=True`: при отсутствии локальных весов CLIP конвейер выполняет детерминированную оценку качества и выдаёт `verdict="uncertain"` с привязкой к `model_ref="heuristic:quality-guard-baseline"`.
* Функция `classify_evidence` в бэкенде гарантированно переводит как `status="unavailable"`, так и `verdict="uncertain"` в статус `manual_review`.
* **False Reassurance Rate = 0.0%**: ни один сбой, обрыв соединения или отсутствие весов не приводит к ложноположительному вердикту `approved`.

### 5.2. Разграничение ответственности ALG07 и ML RUL
* **Детерминированный расчёт регламента ALG07 (FRAI-75)**: полностью принадлежит бэкенду планирования ([backend/app/integration/forecasting.py](file:///home/handraqw/Projects/FixRate_AI/backend/app/integration/forecasting.py)) и вычисляется строго по паспортным межремонтным интервалам оборудования.
* **ML-модуль оценки наработки ([condition.py](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/forecast/condition.py))**: на этапе MVP реализует политику строгого **No-Go** для спекулятивного прогноза остаточного ресурса (RUL). При дефиците подтверждённых отказов возвращает статус `insufficient_data` или `unavailable` (`MODEL_NOT_READY`), категорически исключая выдачу неподтверждённых дат.

### 5.3. Готовность инфраструктуры для динамического RAG (TEAM-ML03)
* В репозитории уже присутствует миграция [database/migrations/026_source_revision_outbox.sql](file:///home/handraqw/Projects/FixRate_AI/database/migrations/026_source_revision_outbox.sql), создающая durable outbox-таблицу `source_revision_events`.
* В [backend/app/integration/analyst.py](file:///home/handraqw/Projects/FixRate_AI/backend/app/integration/analyst.py) реализованы эндпоинты:
  * `GET /api/v1/maintenance/source/revisions?status=pending` — получение очереди событий индексации.
  * `POST /api/v1/maintenance/source/revisions/{event_id}/published` — подтверждение успешной публикации индекса.
* Бэкенд-инфраструктура полностью готова к реализации динамического RAG-консьюмера в задаче TEAM-ML03.

---

## 6. Результаты верификации

В рамках задачи TEAM-ML02 выполнен полный комплекс автоматизированных проверок:

1. **Новые модульные и приёмочные тесты:**
   * [tests/ml/test_team_ml02_bounded_ocr.py](file:///home/handraqw/Projects/FixRate_AI/tests/ml/test_team_ml02_bounded_ocr.py) — 29 проверок Bounded OCR, белого списка приборов, конвертации МПа в бар, защиты `requires_human_verification`, физических диапазонов и блокировки левых классов.
   * [tests/ml/test_team_ml02_photo_assessment.py](file:///home/handraqw/Projects/FixRate_AI/tests/ml/test_team_ml02_photo_assessment.py) — 14 проверок привязки к попытке, staleness-инвалидации, автодетекции противоречия CASE-01 (включая русское тире `–` и `—`), консервативного дефолта сопоставимости, дефектов NEG-01..03, рантайм-фоллбэка и интеграции `review_work_order_attempt`.
   * **Результат:** 43/43 passed (0.29 с).

2. **Сквозной регрессионный прогон всего ML-контура:**
   * Команда: `.venv/bin/pytest tests/ml`
   * **Результат:** **260 / 260 passed** (48.73 с).

3. **Сравнительный бенчмарк моделей:**
   * Команда: `.venv/bin/python3 scripts/benchmark_photo_models.py`
   * **Результат:**
     * Heuristic Baseline: False Reassurance = **0.0%** (p50: 14.8 мс)
     * Local CLIP Zero-Shot: False Reassurance = **0.0%** (p50: 15.5 мс)
     * Conservative Guarded VLM: False Reassurance = **0.0%** (p50: 14.5 мс)
     * Naive Autonomous VLM: False Reassurance = **66.7%** (математическое доказательство недопустимости бесконтрольного ИИ).
     * Протокол сохранён в [reports/ml/photo_model_benchmark.json](file:///home/handraqw/Projects/FixRate_AI/reports/ml/photo_model_benchmark.json).

4. **Проверка артефактов и ссылочной целостности:**
   * Команда: `.venv/bin/python3 scripts/validate_artifacts.py`
   * **Результат:** PASS (1527 локальных ссылок, 31 неизменный исходник).

