# Отчёт о реализации задачи TEAM-ML03 (FRAI-173)
## Динамический RAG и автоматическая актуализация индекса (Ревизия 3 / Финальный)

* **Идентификатор задачи**: FRAI-173 (`5cc2bb6a-4437-4837-87f0-23a49453e4b7`)
* **Исполнитель**: Muhammad / Мухаммад (`d1ba36a5-b2a2-428c-aa24-05ad8fffe4ad`)
* **Контролирующий инженер (QA)**: Михаил (`60eef911-b53c-4417-9ef0-74153c2b0bae`)
* **Ветка разработки**: `feat/team-ml03-dynamic-rag-auto-index`
* **Соответствие регламентам**: CR-17 (бизнес-роли: `chief_engineer`, `executor`), TL04 (безопасность данных, изоляция объектов, строгий запрет галлюцинаций)
* **Аудирующие модели**: OpenAI Codex (GPT-6 Luna) & GPT-5.6 Terra

---

### 1. Архитектура подсистемы Dynamic RAG

Подсистема реализована в модуле `ml_service/app/rag/` с чистым разделением обязанностей, аутентифицированным серверным роутом, защитой от инъекций и персистентной интеграцией с очередью PostgreSQL:

```
ml_service/app/rag/
├── __init__.py           # Публичные интерфейсы, get_rag_service и reset_rag_service
├── schemas.py            # DTO: Chunk, DocumentMetadata, RetrievalQuery, Citation, RetrievalResult, OutboxEvent, IndexSyncReport
├── extractor.py          # Иерархический парсер Markdown (H1 > H2 > H3), коллизионно-стойкие chunk_id, SHA-256, санитизация текста
├── guardrails.py         # Защитные барьеры: AntiHallucinationGuardrail, PromptInjectionDefense, quoteattr для XML-атрибутов и escape для тела
├── index.py              # Лексический индекс: стемминг, синонимы, обобщенный фильтр неутвержденного оборудования и брендов, ролевой и объектный ACL, архив ревизий
├── consumer.py           # Durable Outbox Consumer: вложенные savepoints (begin_nested), резолвинг source_imports по session, персистентная идемпотентность
└── service.py            # Оркестратор RAGService: канонический SHA-256 манифеста, rebuild_from_storage, синглтон get_rag_service, ассистентские запросы
```

Серверная интеграция:
- Роут `GET /api/v1/maintenance/rag/search` в `backend/app/integration/ml.py` с автоматическим извлечением `v.principal.site_id` и `v.principal.role`.
- Инструмент ассистента `rag_search` в `backend/app/assistant/capabilities.py`, покрытие 180 инструментов в `contracts/assistant-tools.json`.
- Воркер очереди `backend/app/integration/source_revision_worker.py`: автоматический вызов `consumer.process_single_db_event` в savepoint при публикации событий.

---

### 2. Устранение замечаний повторного аудита GPT-6 Luna (SHA `6f4d7bb`)

| № | Замечание повторного аудита | Критичность | Внедрённое исправление | Статус |
|:---:|:---|:---:|:---|:---:|
| 1 | **Манифест: не проверялся канонический хэш самого манифеста** | **critical** | В `verify_manifest_integrity` добавлена каноническая сериализация `json.dumps(payload, sort_keys=True)` без ключа `checksum` и сверка SHA-256 с объявленным полем `checksum`. Подмена полей ACL, путей или самого хэша немедленно вызывает ошибку валидации. Покрыто тестом `test_manifest_tampering_detected`. | **RESOLVED** |
| 2 | **Запрос по насосу KSB возвращал регламент ШАУ** | **critical** | В `RAGIndex` реализован обобщенный барьер против неутвержденного оборудования (`насос`, `котел`, `теплообменник`, `горелка`, `чиллер` и др.): если в запросе есть стебли неутвержденного оборудования без явных маркеров шкафа автоматизации (`шау`, `шкаф`), поиск немедленно завершается fail-closed (`DOCUMENT_NOT_FOUND`, `is_hallucination_blocked=True`). Для латинских маркеров бренда (KSB, Wilo, Grundfos и др.) внедрена проверка точного совпадения маркера в кандидатах. Покрыто `test_unapproved_ksb_pump_and_arbitrary_equipment_rejected`. | **RESOLVED** |
| 3 | **XML-атрибуты: инъекция через двойные кавычки (отсутствовал quoteattr)** | **critical** | В `AntiHallucinationGuardrail.format_safe_context` атрибуты `id`, `revision`, `section`, `source_ref` оборачиваются через `xml.sax.saxutils.quoteattr`, а тело — через `escape`. Значение `document_id='doc" injected="yes'` экранируется в безопасный литерал, исключая образование новых атрибутов. Покрыто тестом `test_xml_attribute_quoteattr_injection_prevented` с верификацией через `xml.etree.ElementTree`. | **RESOLVED** |
| 4 | **Durable Outbox: разрыв producer/worker, payload только row_count, потеря состояния при рестарте** | **critical** | 1) В `source_revision_worker.publish_event` встроен вызов `consumer.process_single_db_event` внутри транзакционного savepoint.<br>2) В `DurableOutboxConsumer.process_single_event` добавлен резолвинг `source_rows` из таблицы `source_imports` через `session`, когда в payload события передается только `{"row_count": ...}`.<br>3) В `RAGService` реализован метод `rebuild_from_storage(session)`, который при старте восстанавливает индекс из проверенного манифеста и всех опубликованных событий `source_revision_events`.<br>4) Обеспечена персистентная идемпотентность. Покрыто тестом `test_producer_worker_rag_pipeline_and_restart`. | **RESOLVED** |

---

### 3. Результаты контрольного тестирования

* **Целевой набор тестов TEAM-ML03**: `tests/ml/test_team_ml03_dynamic_rag.py` — **41 из 41 успешно пройден** (1.42 с):
  - `TestCorpusLoadingAndExtraction`: 4 теста (загрузка 5 документов, проверка манифеста, детекция подмены манифеста, хлебные крошки и chunk_id).
  - `TestParaphrasedBenchmarks`: 6 тестов (BM-RAG-01 и BM-RAG-02 с извлечением 1.5–6.0 бар и >0.3 бар).
  - `TestNegativeAndBoundaryCases`: 15 тестов (бренды Wilo, Grundfos, Danfoss, KSB, котлы, горелки, чиллеры; изоляция объектов; устаревшие редакции; prompt injection; экранирование XML-атрибутов через `quoteattr`).
  - `TestRoleAclRestrictions`: 2 теста (CR-17: опрессовка 8.0 бар запрещена для `executor` и разрешена для `chief_engineer`).
  - `TestDurableOutboxConsumer`: 7 тестов (жизненный цикл событий, сверка SHA, gap detection, обработка сбоев, извлечение строк каталога, реальный пайплайн producer→worker→RAG и рестарт через `rebuild_from_storage`).
  - `TestAuthenticatedBackendRAGRoute`: 3 теста (проверка серверного Principal, ролевой блокировки и fail-closed для нерелевантного бренда).
* **Полный тестовый набор подсистемы ML**: `tests/ml` — **301 пройден без единого сбоя** (47.99 с).
* **Репозиторные верификаторы**:
  - `scripts/verify_photo_manifest.py`: SUCCESS (PASS, 14 фото, 0 реальных клиентов).
  - `scripts/verify_split_leakage.py -v`: SUCCESS (PASS, 0 утечек).
  - `scripts/validate_artifacts.py`: OK.
  - `scripts/assistant_capabilities.py`: 180 инструментов, 100% покрытие API без неучтенных роутов.
  - `tests/backend/test_assistant_capabilities.py`: PASS.
