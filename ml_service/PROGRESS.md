# FixRate AI — Журнал разработки ML Service (PROGRESS.md)

**Проект:** FixRate AI — ML Service  
**Рабочая директория:** `ml_service/`  
**Основной исполнитель:** AI Coding Assistant & Архитектор ML Service  
**Дата старта:** 21 октября 2026 г.  

---

## 1. Общий прогресс разработки

- **Всего микрозадач в целевом плане:** 70
- **Выполнено (`DONE`):** 34 / 70 (48.6%) — *Фаза 1, 1.1 и задачи RAG Ingestion (ML-033, ML-035, ML-036) завершены*
- **Заменено (`SUPERSEDED`):** 1 / 70 (`ML-009`: заменена на фазу сбора датасета `ML-042`)
- **В работе (`IN_PROGRESS`):** 0 / 70
- **Заблокировано (`BLOCKED`):** 0 / 70
- **Ожидают выполнения (`TODO`):** 35 / 70 (50.0%) — *Фазы 2–7 (PII/Safety, гибридный RAG-поиск, обучение YOLO, боевой OCR, асинхронные воркеры)*

---

## 2. Хронологический журнал сессий

### Сессия 7: Индексация и загрузка нормативов в pgvector ({RAG} Ingestion Pipeline) (22.10.2026)

#### Что сделано:
1. **Реализация провайдера векторных эмбеддингов (`ML-033`):**
   - В [`app/rag/embeddings.py`](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/rag/embeddings.py) реализован [`GigaChatEmbeddingsProvider`](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/rag/embeddings.py#L86) (модель `Embeddings` Сбера размерности 1024) с пакетной обработкой, безопасным fallback и поддержкой асинхронных вызовов `aembeddings()`.
   - Реализован [`MockEmbeddingsProvider`](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/rag/embeddings.py#L42) с детерминированной L2-нормализацией и морфологическим стеммингом русского языка для герметичных тестов без внешних API.
2. **Семантический чанкер нормативной документации (`ML-035`):**
   - В [`app/rag/chunker.py`](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/rag/chunker.py) создан [`NormativeChunker`](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/rag/chunker.py#L52), разбирающий нормативные документы на пункты/статьи с формированием `source_locator`, `metadata`, определением признаков аварийности (`hazard_level="structural_hazard"`) и расчетом SHA-256 хеша.
3. **Ingestion Pipeline и CLI-индексатор (`ML-036`):**
   - В [`app/rag/ingestion.py`](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/rag/ingestion.py) реализован [`NormativeIngestionPipeline`](file:///home/handraqw/Projects/FixRate_AI/ml_service/app/rag/ingestion.py#L41) с пакетной загрузкой в таблицу `normative_chunks` PostgreSQL `pgvector`, связыванием `rate_id` и экспортом готового SQL seed-файла [`data/seed_normative_chunks.sql`](file:///home/handraqw/Projects/FixRate_AI/ml_service/data/seed_normative_chunks.sql).
   - Создана консольная утилита [`scripts/ingest_normatives.py`](file:///home/handraqw/Projects/FixRate_AI/ml_service/scripts/ingest_normatives.py) с поддержкой режимов `--apply`, `--dry-run` и `--export-sql`.
4. **Корпус нормативных документов:**
   - Подготовлены 4 регламента в [`data/normatives/`](file:///home/handraqw/Projects/FixRate_AI/ml_service/data/normatives/): СП 71.13330 (фасады), ГОСТ 31937 (аварийные трещины), СП 29.13330 (полы и плитка), СП 250.1325800 (гидроизоляция паркингов).
   - Выполнена боевая индексация: 16 чанков успешно сохранены в PostgreSQL контейнера `fixrate_postgres` и проверены векторным поиском (`<=>`) и полнотекстовым поиском (`tsvector`).
5. **Тестирование:**
   - Написаны 17 новых модульных тестов (`test_rag_chunker.py`, `test_rag_embeddings.py`, `test_rag_ingestion.py`).
   - Итог по тестам ML Service: **120 passed** (100% герметичны).

---

### Сессия 6: Исправление замечаний аудита ядра и ревизия бэклога v3.0 (22.10.2026)

#### Что сделано:
1. **Устранение 4 дефектов ядра в коде (коммит `ba16fd4`):**
   - **`ML-028a`:** Удалена фиктивная генерация серого квадрата (`Image.new("RGB", (640, 480), "gray")`) в `orchestrator.py`. Пустые запросы без файлов и описаний теперь корректно возвращают статус `failed` без вызова CV-модели.
   - **`ML-028b`:** Модуль `DocumentParser` (OCR) подключен в рабочий контур `PipelineOrchestrator`. Документы парсятся с сохранением номеров страниц и передаются в слияние дефектов с `SourceType.OCR`.
   - **`ML-028c`:** На этапе `QA_AUDIT` включен обязательный вызов `EstimateAuditor.audit_item()`. Аномальные объемы (>5000 м²) или отрицательные цены переводят статус в `NEEDS_REVIEW`.
   - **`ML-028d`:** Реализована защита от ложного статуса `COMPLETED` при невозможности рассчитать ни одной сметной позиции (возврат `failed` или `needs_review`). В ответ добавлена явная диагностика `llm_fallback_used`.
2. **Ревизия архитектурной дорожной карты и бэклога (версия 3.0):**
   - Бэклог перестроен на 70 задач в 7 последовательных фазах с устранением всех замечаний независимого аудита.
   - **Фаза 2 (P0):** Задачи защиты ПДн (`ML-029` маскирование PII перед отправкой в LLM) и безопасности (`ML-030` Safety Guardrail подозрительных трещин $\ge 2$ мм) вынесены в немедленный приоритет до масштабирования RAG и CV.
   - **Таксономия (`ML-031`):** Строго разделены уровни абстракции — визуальные классы нейросети (`crack`, `chip`, `stain_wet`) и сметно-доменные коды ремонта (`facade_crack`, `tile_chip`, `parking_leak`).
   - **Фиксация технологий:** Зафиксированы провайдер эмбеддингов Сбера `Embeddings` 1024d (`ML-033`), OCR-движок `PaddleOCR` с fallback на Tesseract (`ML-053`), и асинхронный воркер `Redis + ARQ` (`ML-061`), совместимый с Python 3.14.
   - **Согласование с командой:** Задачи изменения compose (`ML-064`) и сквозных e2e-тестов с Backend (`ML-065`) явно маркированы как `[SHARED: Team]`.
3. **Статус тестов:**
   - Написаны 4 новых автотеста в `tests/unit/test_orchestrator.py`.
   - Тесты `ml_service/tests/`: **103 passed** (100% герметичны, без платных API).
   - Тесты `backend/tests/`: **24 passed, 10 skipped**.

---

### Сессия 5: Полная декомпозиция целевой архитектуры ML Pipeline (22.10.2026)

#### Что сделано:
1. **Декомпозиция спецификации `ML_PIPELINE.md`:**
   - Произведен глубокий аудит всех 18 разделов целевой архитектуры (950 строк) и сформирован исчерпывающий реестр из 65 микрозадач (`ML-001` — `ML-065`).
   - Разработаны спецификации для Фазы 2 (Боевой RAG на PostgreSQL `pgvector` + `GigaChatEmbeddings` 1024 dims + сметный парсер ГЭСН/ФЕР + реранкинг + цитаты СП/ГОСТ).
   - Разработаны спецификации для Фазы 3 (Обучение детектора и сегментации YOLOv8-det/seg, метрическая калибровка физического масштаба по маркерам, дедупликация серии фото, tiled inference 4K).
   - Разработаны спецификации для Фазы 4 (Боевой движок PaddleOCR/EasyOCR, распознавание структуры таблиц дефектных актов, многостраничный PDF-парсер).
   - Разработаны спецификации для Фазы 5 (Сметные комплексы сопутствующих работ, индексы Минстроя РФ, детектор аварийности несущих конструкций `needs_review`, маскирование ПДн PII).
   - Разработаны спецификации для Фазы 6 (Асинхронные воркеры Celery/Redis с машиной состояний из 13 статусов, S3 MinIO хранилище, вебхуки, полный `docker-compose.yml`, сквозные e2e и нагрузочные тесты Locust).
2. **Синхронизация документов:**
   - Обновлен [TASKS.md](file:///home/handraqw/Projects/FixRate_AI/ml_service/TASKS.md) с полными описаниями, файлами, критериями приемки и командами проверок.
   - Обновлены [PLAN.md](file:///home/handraqw/Projects/FixRate_AI/ml_service/PLAN.md) и [PRODUCT.md](file:///home/handraqw/Projects/FixRate_AI/ml_service/PRODUCT.md).
3. **Статус тестов:**
   - Тесты `ml_service/tests/`: **99 passed** (100% hermetic).
   - Тесты `backend/tests/`: **24 passed, 10 skipped**.

---

### Сессия 4: Закрытие критичных замечаний аудита (21.10.2026)

#### Что сделано:
1. **Anti-hallucination (`ML-012`, `ML-014`):**
   - В `NormalizedDefectDescription` добавлен allowlist `ALLOWED_MEASUREMENT_KEYS`: финансовые и произвольные ключи (`price`, `cost`, `coefficient`) отклоняются, значения обязаны быть положительными конечными числами.
   - `LLMGateway` повторно валидирует вывод провайдера; при попытке протащить запрещённое поле выполняется fallback на эвристику.
2. **Эвристический парсер (`ML-013`):**
   - Исправлен `RE_DIRECT_M`: «6.2 м2» больше не извлекается одновременно как `area_m2` и `length_m`.
3. **Слияние данных (`ML-022`):**
   - Явные `known_measurements` применяются к совместимым типам дефектов, а не ко всем.
   - Тип дефекта выводится из однозначных параметров (`count` → `tile_chip`, `leak_area_m2` → `parking_leak`); неоднозначная `area_m2` без типа больше не угадывается.
   - Единицы измерения определяются по имени параметра (`depth_m` → m, `area_m2` → m2).
   - Provenance и приоритет USER-измерений зафиксированы тестами.
4. **E2E-покрытие (`ML-023`, `ML-026`):**
   - Добавлены ветки `needs_clarification` для `tile_chip` (`MISSING_TILE_COUNT`) и `parking_leak` (`MISSING_LEAK_AREA`) с последующим успешным расчётом.
5. **Новые тесты:**
   - `tests/unit/test_merge.py` — 6 тестов слияния/provenance.
   - `tests/unit/test_llm_gateway.py` — 4 теста anti-hallucination и fallback.
   - `tests/integration/test_demo_scenarios.py` — 2 e2e-теста веток уточнения.

#### Итоги проверок и тестов:
- Тесты `ml_service/tests/`: **99 passed** (0 failed), было 87.

---

### Сессия 3: Ужесточение RAG-подсистемы (21.10.2026)

#### Что сделано:
1. **Синхронизация каталога с БД (`ML-015`):**
   - Добавлен автотест `test_catalog_matches_seed_sql`, который парсит `db/002_seed_demo.sql` и сверяет с `data/demo_rates.json` источник, `rate_id`, коды, наименования, описания, единицы, множитель, цены, валюту и области применения.
2. **Качество векторного поиска (`ML-017`):**
   - Эмбеддинги переведены с hash-bit подписи (64 измерения, коллизии искажали сходство) на разреженный хешированный bag-of-stems размерности 4096 с нормализацией BM25-стеммером. Словоформы («трещина»/«трещины») теперь попадают в один признак.
   - Добавлен порог `min_similarity` (по умолчанию `0.05`), отсекающий нерелевантных кандидатов вместо возврата всего каталога.
   - Усилены тесты: `related > unrelated`, `top-1` для всех 3 пилотных сценариев, отсечение нерелевантного запроса, переопределение порога.
3. **Верификация RAG:**
   - Подтверждено, что `HybridRAGSearchEngine` реально используется в `app/pipeline/orchestrator.py` (этап `RAG_RETRIEVAL`).

#### Итоги проверок и тестов:
- Тесты `ml_service/tests/`: **87 passed** (0 failed), было 83.

---

### Сессия 2: Синхронизация с master (DDL v3.1 + ORM) и интеграция GigaChat (21.10.2026)

#### Что сделано:
1. **Синхронизация с `master`:**
   - Влиты наработки Карточки №2 команды: каноническая DDL-схема PostgreSQL 16 (`db/001_init.sql`, `002_seed_demo.sql`) и 18 SQLAlchemy 2.0 ORM-моделей в `backend/app/models/`.
   - Ветка `ai/ml-service` обновлена без единого конфликта, установлена зависимость `pgvector`.
   - Все тесты бэкенда с живой БД проходят (34 passed).
2. **Реализация `ML-028: Интеграция провайдера GigaChat (Сбер)`:**
   - Добавлен официальный SDK `gigachat>=0.2.0` в `requirements.txt`.
   - Реализован `GigaChatProvider` (`app/llm/gigachat_provider.py`) с поддержкой `chat_parse` и прямым извлечением JSON.
   - Системный промпт с Few-Shot классификацией (`facade_crack`, `tile_chip`, `parking_leak`), извлечением геометрии и строгим anti-hallucination запретом на цены.
   - Поддержка переключения моделей: `GigaChat-Pro`, `GigaChat-Lite`, `GigaChat-Max`.
   - Обновлен `LLMGateway` с безопасным fallback на эвристический парсер при сбоях сети или отсутствии ключа.
   - Обновлены конфигурация `app/core/config.py` и `.env.example`.
   - Написаны 6 юнит-тестов в `tests/unit/test_gigachat_provider.py`.
   - Создан вспомогательный скрипт `scratch_test_gigachat.py` для тестирования боевого ключа.

#### Итоги проверок и тестов:
- Тесты `ml_service/tests/`: **83 passed** (0 failed).
- Тесты `backend/tests/`: **34 passed** (0 failed).
- Итого по проекту: **117 passed**.

---

### Сессия 1: Полный аудит, архитектурная фиксация и реализация ядра (21.10.2026)

#### Что сделано:
1. **Аудит репозитория (Этап A):**
   - Исследован статус ветки `ai/ml-service` и наработок команды в `origin/kran_dev` (SQL DDL `001_init.sql`, DEMO seed `002_seed_demo.sql`, модели SQLAlchemy).
   - Зафиксировано исходное состояние: в `ml_service/` находился только файл целевой архитектуры `ML_PIPELINE.md`.
2. **Архитектурная и проектная документация (Этап B):**
   - [PLAN.md](PLAN.md) — детальный архитектурный план, граф зависимостей, границы ответственности с Backend, требования к окружению.
   - [PRODUCT.md](PRODUCT.md) — продуктовые требования, сценарии сметчика, спецификация 3 пилотных сценариев (`facade_crack`, `tile_chip`, `parking_leak`), нефункциональные требования и антигаллюцинационные ограничения.
   - [TASKS.md](TASKS.md) — полный реестр из 27 атомарных микрозадач (C1–C9) с критериями приёмки.
   - [PROGRESS.md](PROGRESS.md) — оперативный журнал разработки.
3. **Реализация всех доступных компонентов (Этап D):**
   - **C1. Основа сервиса:**
     - `ML-001`: Окружение, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.env.example`.
     - `ML-002`: Централизованная конфигурация `app/core/config.py`, канонический формат ошибок `app/core/errors.py`, логирование `app/core/logging.py`.
     - `ML-003`: Pydantic v2 контракты `ExtractedField[T]`, `SourceType`, `PipelineStatus`, `JobRequestDTO`, `JobResponseDTO`.
     - `ML-004`: Каркас FastAPI `app/main.py` с `RequestIdMiddleware` и `GET /health`.
   - **C8. Детерминированный расчёт:**
     - `ML-019`: Библиотека строительных формул `app/calculation/formulas.py` на `Decimal` (`ROUND_HALF_UP`).
     - `ML-020`: Движок `CalculationEngine` (`app/calculation/engine.py`) с пошаговой трассировкой вычислений.
     - `ML-021`: Аудитор сметных расчётов `EstimateAuditor` (`app/calculation/audit.py`).
   - **C6. RAG и нормативно-справочная база:**
     - `ML-015`: Эталонный DEMO-каталог расценок `data/demo_rates.json` (синхронизированный с `002_seed_demo.sql`) и класс `RatesCatalog`.
     - `ML-016`: Лексический поиск Okapi BM25 с токенизацией русского языка `app/rag/lexical_search.py`.
     - `ML-017`: Векторный семантический поиск по косинусному сходству `app/rag/vector_search.py`.
     - `ML-018`: Гибридный поиск RRF и валидатор применимости `app/rag/hybrid.py`, `app/rag/applicability.py`.
   - **C2. Компьютерное зрение (CV YOLO):**
     - `ML-005`: Безопасное открытие изображений (Pillow), защита от декомпрессионных бомб и коррекция EXIF `app/cv/image_io.py`.
     - `ML-006`: Схемы детекций `BoundingBox`, `DetectionDTO`, `CVInferenceResult` с нормализацией в диапазон 0.0..1.0.
     - `ML-007`: Протокол детектора `BaseDetectorProtocol`, детерминированный `MockYoloDetector` и адаптер `UltralyticsYoloDetector`.
     - `ML-008`: Фасад `CVService` в `app/cv/service.py` с фильтрацией по порогу уверенности и замером времени.
   - **C4. OCR и документы:**
     - `ML-010`, `ML-011`: Схемы извлечения и парсер документов `app/ocr/document_parser.py` с привязкой к страницам.
   - **C5. LLM Gateway:**
     - `ML-012`, `ML-013`, `ML-014`: Структурированная схема нормализации текста без полей цен `app/llm/schemas.py`, эвристический `MockLLMProvider` и фасад `LLMGateway` с безопасным fallback.
   - **C7. Оркестратор:**
     - `ML-022`: Модуль слияния признаков с сохранением Provenance (`app/pipeline/merge.py`).
     - `ML-023`: Валидатор полноты параметров и генератор `needs_clarification` (`app/pipeline/validation.py`).
     - `ML-024`: Сквозной координатор пайплайна `PipelineOrchestrator` (`app/pipeline/orchestrator.py`).
   - **C9. Интеграция:**
     - `ML-025`: Эндпоинт `POST /api/v1/process` в `app/api/v1/process.py`.
     - `ML-026`: Сквозные тесты 3 пилотных сценариев `tests/integration/test_demo_scenarios.py`.
     - `ML-027`: Контейнеризация `Dockerfile` и документация `ml_service/README.md`.

#### Итоги проверок и тестов:
- Всего запущено тестов в `ml_service/tests/`: **77 тестов** (10 интеграционных + 67 модульных).
- Результат: **77 passed**, 0 failed.
- Проверка тестов backend (`backend/tests/`): **13 passed**, регрессий нет.

#### Заблокированные задачи:
- `ML-009`: Обучение весов строительных дефектов заблокировано до предоставления размеченного датасета. В текущей реализации архитектура полностью подготовлена: реализован протокол `BaseDetectorProtocol`, реальный адаптер `UltralyticsYoloDetector` корректно сообщает о статусе `unavailable` при отсутствии весов, а тесты воспроизводимо работают через детерминированный `MockYoloDetector`.

#### Рекомендации команде:
1. Согласовать лицензию на YOLO (`ultralytics` лицензирован под AGPL-3.0). Если AGPL-3.0 неприемлем, использовать экспорт в ONNX Runtime.
2. Предоставить размеченный датасет строительных дефектов для обучения целевых весов модели.
3. В модуле backend подключить вызов `ml_service` по URL `http://localhost:8001/api/v1/process` (зарезервированная переменная `ML_BASE_URL` в `backend/app/core/config.py`).
