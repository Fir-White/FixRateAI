# Отчёт о реализации задачи TEAM-ML03 (FRAI-173)
## Динамический RAG и автоматическая актуализация индекса (Ревизия 6 / Финальный)

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
├── schemas.py            # DTO: Chunk, DocumentMetadata (статусы: active, stale, archived, deleted, pending, failed), RetrievalQuery, Citation, RetrievalResult, OutboxEvent, IndexSyncReport
├── extractor.py          # Иерархический парсер Markdown (H1 > H2 > H3), стабильные логические ID каталогов catalog-site-{site_id}, SHA-256
├── guardrails.py         # Защитные барьеры: AntiHallucinationGuardrail, PromptInjectionDefense, quoteattr для XML-атрибутов и escape для тела
├── index.py              # Лексический индекс: стемминг, синонимы, обобщенный фильтр неутвержденного оборудования, ролевой и объектный ACL, архив ревизий, revoke/delete_document с вытеснением из активного поиска
├── consumer.py           # Durable Outbox Consumer: вложенные savepoints (begin_nested), резолвинг source_imports по session, проверка статуса БД (durable deduplication), резолвинг catalog-site-{site_id} при revoked/deleted
└── service.py            # Оркестратор RAGService: канонический SHA-256 манифеста, rebuild_from_storage, авто-инициализация при старте (lifespan), синглтон
```

Серверная интеграция:
- Роут `GET /api/v1/maintenance/rag/search` в `backend/app/integration/ml.py` с автоматическим извлечением `v.principal.site_id` и `v.principal.role`, а также передачей `v.session` в сервис для автоматической актуализации.
- Lifespan приложения в `backend/app/main.py`: автоматический прогрев и `rebuild_from_storage` динамического RAG-индекса при старте сервера из сессии БД.
- Инструмент ассистента `rag_search` в `backend/app/assistant/capabilities.py`, покрытие 180 инструментов в `contracts/assistant-tools.json`.
- Воркер очереди `backend/app/integration/source_revision_worker.py`: автоматический вызов `consumer.process_single_db_event` в savepoint при публикации событий, пропуск `index_source_rows` для `revoked`/`deleted`.

---

### 2. Устранение замечаний аудита SHA `f64bc5c`

| № | Замечание аудита | Критичность | Внедрённое исправление | Статус |
|:---:|:---|:---:|:---|:---:|
| 8 | **DocumentMetadata.status**: отсутствие литерала `deleted` в схеме Pydantic | **medium** | В `schemas.py` в поле `DocumentMetadata.status` добавлен литерал `"deleted"`: `Literal["active", "stale", "archived", "deleted", "pending", "failed"]`. Теперь сериализация/десериализация `DocumentMetadata.model_validate(meta.model_dump())` для удалённых объектов проходит без ошибок валидации. | **RESOLVED** |
| 9 | **Тестовое покрытие**: отсутствовал тест Pydantic round-trip для удалённых метаданных | **medium** | В `tests/ml/test_team_ml03_dynamic_rag.py` добавлены проверки round-trip сериализации/валидации через Pydantic: в тесте `test_source_import_worker_to_consumer_deleted_removes_from_active_search` (для свежих и восстановленных метаданных), а также отдельный модульный тест `test_document_metadata_deleted_status_pydantic_roundtrip`. Общее число тестов ML03 увеличено до 47. | **RESOLVED** |

---

### 3. Сводная таблица соответствия всем критериям аудита

| № | Область проверки | Реализация в ветке | Статус |
|:---:|:---|:---|:---:|
| 1 | **Corpus / canonical hash / extraction** | SHA-256 манифеста `d13e...15c8`, канонический payload hash `af531...0427`. Сверка физических хэшей всех 5 файлов. Breadcrumbs `H1 > H2 > H3` и ревизионные `chunk_id`. Защита от подмены ACL. | **PASS** |
| 2 | **BM-RAG-01 / BM-RAG-02** | 6 бенчмарков с перефразированием: манометры 1.5–6.0 бар и фильтры >0.3 бар с точным извлечением нормативов и ссылок. | **PASS** |
| 3 | **Zero hallucination / Fail-closed** | Защита от подмены паспортов общими совпадениями. Неутвержденные бренды (KSB, Wilo, Grundfos, Danfoss) и типы оборудования (котлы, горелки, чиллеры) возвращают `DOCUMENT_NOT_FOUND`, пустые цитаты и `is_hallucination_blocked=True`. | **PASS** |
| 4 | **Server Principal / ACL / capability** | Роут `/api/v1/maintenance/rag/search` берет `site_id` и `user_role` строго из `v.principal`. Зарегистрирован capability `rag_search`, покрыто 180 инструментов (100%), 0 неучтенных роутов. | **PASS** |
| 5 | **Revision archive / auto-rebuild** | Стабильный логический `catalog-site-{site_id}` гарантирует архивацию устаревших ревизий каталога с `is_stale=True`. Автоматический `rebuild_from_storage` при запуске в `lifespan(app)` и в роуте поиска. Запрос архива выдает предупреждение со ссылкой на активную ревизию. | **PASS** |
| 6 | **Prompt-injection / XML** | Атрибуты XML тегов `<source_evidence>` экранируются через `xml.sax.saxutils.quoteattr`, тело — через `escape`. Валидность проверена через `xml.etree.ElementTree`. | **PASS** |
| 7 | **CR-17: опрессовка** | Опрессовка коллектора 8.0 бар (`doc-stp-manifold-05`) ограничена ролью `chief_engineer`. Роль `executor` получает `ACCESS_DENIED`. | **PASS** |
| 8 | **Durable Outbox / revoked & deleted** | При `revoked`/`deleted` событиях `source_import` consumer разрешает целевой документ как `catalog-site-{event.site_id}`, переводит метаданные в `is_archived=True, is_stale=True, status='stale'/'deleted'`, удаляет чанки из активного словаря `chunks`, блокируя выдачу в поиск. Схема `DocumentMetadata` включает `"deleted"`, Pydantic round-trip валидируется без ошибок. Воркер корректно переводит событие в `published`. | **PASS** |
| 9 | **Тестовое покрытие** | 47/47 тестов ML03 успешно пройдены (1.48 с). 307/307 тестов ML-пакета пройдены. Все репозиторные верификаторы зеленые. | **PASS** |

---

### 4. Результаты контрольного тестирования

* **Целевой набор тестов TEAM-ML03**: `tests/ml/test_team_ml03_dynamic_rag.py` — **47 из 47 успешно пройден** (1.48 с).
* **Полный тестовый набор подсистемы ML**: `tests/ml` — **307 пройден без единого сбоя** (49.88 с).
* **Репозиторные верификаторы**:
  - `scripts/verify_photo_manifest.py`: SUCCESS (PASS, 14 фото, 0 реальных клиентов).
  - `scripts/verify_split_leakage.py -v`: SUCCESS (PASS, 0 утечек).
  - `scripts/validate_artifacts.py`: OK.
  - `scripts/assistant_capabilities.py`: 180 инструментов, 100% покрытие API без неучтенных роутов.
  - `tests/backend/test_assistant_capabilities.py`: PASS.
