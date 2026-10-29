# FixRate AI — Каталог компетенций и навыков ML/CV (SKILLS.md)

**Проект:** FixRate AI — Интеллектуальное планирование ТО и ППР  
**Ветка:** `feat/ml-forecasting-photo-review`  
**Исполнитель:** Мухаммад (AI-прогноз и анализ фото)  

В этом документе систематизированы программные навыки, инструменты и инженерные компетенции (*Skills*), реализованные в рамках модуля машинного обучения и компьютерного зрения.

---

## 1. Обзор навыков (Skills Matrix)

| Skill ID | Название навыка | Назначение | Используемые библиотеки | Контракт / Артефакт |
| :--- | :--- | :--- | :--- | :--- |
| `SK-DATA-01` | **Synthetic Data Generator** | Генерация Набора B (`synthetic_demo`) с известным `observed_need_date` и историей наработки | `Python stdlib`, `random`, `uuid`, `datetime` | `ForecastSnapshot` |
| `SK-FE-01` | **Feature Extractor** | Преобразование графа объектов `ForecastSnapshot` в числовой вектор признаков | `numpy`, `zoneinfo` | `rf-features-v1` |
| `SK-ML-01` | **RandomForest Forecaster** | Обучение регрессионной модели и предсказание дней до потребности в ТО | `scikit-learn`, `numpy` | `ForecastResult(method="ai")` |
| `SK-ML-02` | **Tree Dispersion Estimator** | Оценка интервала неопределённости по квантилям деревьев ансамбля (10%–90%) | `numpy` | `Uncertainty(tree_dispersion)` |
| `SK-ML-03` | **Artifact Manifesting** | Хеширование датасета, модели и конфигурации; фиксация происхождения | `hashlib` (SHA-256), `json` | `artifact_manifest.json` |
| `SK-CV-01` | **Image Quality Guard** | Проверка резкости (дисперсия Лапласиана), контрастности, яркости и метаданных | `Pillow`, `numpy` | `verdict="uncertain"` |
| `SK-CV-02` | **CLIP Zero-Shot Reviewer** | Извлечение эмбеддингов фото и текстовых промптов, расчёт косинусного сходства | `transformers`, `torch` (`CLIP ViT-B/32`) | `scores: list[ImageLabelScore]` |
| `SK-CV-03` | **Visual Guardrail Policy** | Автоматическая изоляция скрытых и неизмеряемых визуально технологических операций | `Pydantic 2`, доменная таблица | `verdict="not_verifiable"` |
| `SK-QA-01` | **Hermetic Test Harness** | Изолированное тестирование модулей без внешних API и зависимостей от БД | `pytest` | Тесты S01–S15 |

---

## 2. Подробное описание навыков

### `SK-DATA-01`: Synthetic Data Generator (`synthetic_demo`)
* **Контекст:** График заказчика не содержит истории наработки и поломок. Для проверки архитектурного пайплайна генерируется изолированный набор данных.
* **Функционал:**
  - Создание цепочки оборудования (ИТП: теплообменники, насосы, грязевики).
  - Моделирование наработки: счётчик часов с монотонным ростом (`meter_epoch=1`).
  - Симуляция циклов обслуживания: принятые события (`AcceptedEvent`) с интервалами и метками времени.
  - Моделирование истинной потребности: генерация `observed_need_date`, относительно которой валидируется точность MAE.
  - Детерминизм: фиксированный `seed=42`, позволяющий воспроизводить результаты на любой машине.

---

### `SK-FE-01`: Feature Extractor (`rf-features-v1`)
* **Контекст:** Преобразование иерархического Pydantic-объекта `ForecastSnapshot` в плоский вектор для Scikit-learn.
* **Вектор признаков (6 измерений):**
  1. `equipment_type_hash`: категориальный хеш типа оборудования.
  2. `age_days`: количество дней с момента ввода в эксплуатацию (`commissioned_on`) до `as_of`.
  3. `days_since_last_service`: разница в днях между `as_of` и последним принятым `performed_at`.
  4. `runtime_hours_since_last_service`: наработка в часах с момента последнего обслуживания.
  5. `prior_service_count`: количество успешно принятых ТО в истории.
  6. `mean_prior_interval_days`: средний межсервисный интервал по историческим данным.
* **Защита от утечек:** Строго исключает любые события с `performed_at > as_of`.

---

### `SK-ML-01` & `SK-ML-02`: RandomForest Forecaster & Tree Dispersion
* **Контекст:** Предсказание остаточных дней до ТО с оценкой разброса.
* **Реализация:**
  - Модель: `RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42)`.
  - Предсказание: среднее предсказание ансамбля округляется до целых суток: $\Delta_{days} = \text{round}(\hat{y})$.
  - Рекомендуемая дата: $\text{as\_of\_date} + \Delta_{days}$.
  - Расчёт разброса: сбор индивидуальных предсказаний каждого из 100 деревьев ансамбля:
    $$\text{lower\_bound} = \text{percentile}(preds, 10), \quad \text{upper\_bound} = \text{percentile}(preds, 90)$$
  - Формирование объекта [`Uncertainty`](file:///home/handraqw/Projects/FixRate_AI/backend/app/schemas/maintenance.py#L188-L204):
    ```python
    Uncertainty(
        kind="tree_dispersion",
        lower_date=as_of_date + timedelta(days=lower_bound),
        upper_date=as_of_date + timedelta(days=upper_bound),
        calibrated=False,
        note="Разброс 10-90 перцентилей деревьев RandomForest на синтетике."
    )
    ```

---

### `SK-CV-01`: Image Quality Guard
* **Контекст:** Оценка пригодности загруженного кадра перед отправкой в тяжелую нейросеть.
* **Проверки:**
  1. **Формат и размер:** MIME (`image/jpeg`, `image/png`, `image/webp`), размер $\le 10$ МБ, разрешение $\le 20$ Мпикс.
  2. **Оценка резкости:** Свертка изображения с оператором Лапласа и вычисление дисперсии ($\sigma^2_{Laplace}$). При $\sigma^2 < 100.0$ кадр классифицируется как смазанный (`blur`).
  3. **Оценка контрастности и яркости:** Вычисление средней яркости по шкале серого. Кадры с пересветом ($>245$) или экстремальной темнотой ($<15$) отсекаются.
  4. **Совпадение ракурса:** Сверка поля `view_key` у пары фото.
* **Результат при сбое проверок:** Возврат `verdict="uncertain"` с указанием причины в `observation` (например, `"Изображение смазано (Laplacian variance 42.1 < 100.0)"`).

---

### `SK-CV-02`: CLIP Zero-Shot Reviewer
* **Контекст:** Сопоставление пары фото «до» и «после» с текстовыми описаниями состояния оборудования.
* **Модель:** `openai/clip-vit-base-patch32` (локальный инференс через Hugging Face `transformers`).
* **Промпт-сет (`prompt_set_version="demo-clean-pairs-v1"`):**
  - Класс 0 (загрязнённость): `"a dirty, dusty, clogged industrial equipment surface"`
  - Класс 1 (чистота): `"a clean, serviced, shiny industrial equipment surface"`
* **Логика сопоставления:**
  1. Вычисляется вероятность принадлежности к классу чистоты для фото «до»: $P_{clean}(before)$.
  2. Вычисляется вероятность для фото «после»: $P_{clean}(after)$.
  3. Если $P_{clean}(after) - P_{clean}(before) \ge \Delta_{threshold}$ (по умолчанию $0.25$) $\to$ `verdict="visible_change"`.
  4. Если разница меньше порога $\to$ `verdict="no_visible_change"`.

---

### `SK-CV-03`: Visual Guardrail Policy (Скрытые работы)
* **Контекст:** Защита от необоснованных выводов ИИ о скрытых физических процессах.
* **Спецификация операций:**
  - Операция **1.4** («Чистка узлов и агрегатов») $\to$ `visual_verifiability="visible"` $\to$ подлежит полной оценке через CLIP.
  - Операция **1.5** («Проверка точности приборов») $\to$ `visual_verifiability="not_verifiable"` $\to$ **принудительно** вердикт `not_verifiable`.
  - Операция **1.6** («Выпуск воздуха из системы») $\to$ `visual_verifiability="not_verifiable"` $\to$ **принудительно** вердикт `not_verifiable`.
* **Правило:** Даже если разница скоров CLIP высока, для пунктов с флагом `not_verifiable` в отчёт пишется:
  `"Операция скрытого характера или приборный замер: фотофиксация не доказывает калибровку/отсутствие воздуха"`.
