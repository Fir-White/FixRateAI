# FixRate AI — Журнал разработки ML Service (PROGRESS.md)

**Проект:** FixRate AI — ML Service  
**Рабочая директория:** `ml_service/`  
**Основной исполнитель:** AI Coding Assistant & Архитектор ML Service  
**Дата старта:** 21 октября 2026 г.  

---

## 1. Общий прогресс разработки

- **Всего микрозадач в плане:** 28
- **Выполнено (`DONE`):** 27 / 28 (96.4%)
- **В работе (`IN_PROGRESS`):** 0 / 28
- **Заблокировано (`BLOCKED`):** 1 / 28 (`ML-009`: реальное обучение YOLO строительным дефектам до предоставления размеченного датасета)
- **Ожидают выполнения (`TODO`):** 0 / 28

---

## 2. Хронологический журнал сессий

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
