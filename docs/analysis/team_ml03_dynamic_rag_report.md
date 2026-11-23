# Отчёт о реализации задачи TEAM-ML03 (FRAI-173)
## Динамический RAG и автоматическая актуализация индекса (Ревизия 4 / Финальный)

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
├── extractor.py          # Иерархический парсер Markdown (H1 > H2 > H3), стабильные логические ID каталогов catalog-site-{site_id}, SHA-256
├── guardrails.py         # Защитные барьеры: AntiHallucinationGuardrail, PromptInjectionDefense, quoteattr для XML-атрибутов и escape для тела
├── index.py              # Лексический индекс: стемминг, синонимы, обобщенный фильтр неутвержденного оборудования, ролевой и объектный ACL, архив ревизий
├── consumer.py           # Durable Outbox Consumer: вложенные savepoints (begin_nested), резолвинг source_imports по session, проверка статуса БД (durable deduplication)
└── service.py            # Оркестратор RAGService: канонический SHA-256 манифеста, rebuild_from_storage, авто-инициализация при старте (lifespan), синглтон
```

Серверная интеграция:
- Роут `GET /api/v1/maintenance/rag/search` в `backend/app/integration/ml.py` с автоматическим извлечением `v.principal.site_id` и `v.principal.role`, а также передачей `v.session` в сервис для автоматической актуализации.
- Lifespan приложения в `backend/app/main.py`: автоматический прогрев и `rebuild_from_storage` динамического RAG-индекса при старте сервера из сессии БД.
- Инструмент ассистента `rag_search` в `backend/app/assistant/capabilities.py`, покрытие 180 инструментов в `contracts/assistant-tools.json`.
- Воркер очереди `backend/app/integration/source_revision_worker.py`: автоматический вызов `consumer.process_single_db_event` в savepoint при публикации событий.

---

### 2. Устранение замечаний аудита SHA `5bda4dd`

| № | Замечание аудита | Критичность | Внедрённое исправление | Статус |
|:---:|:---|:---:|:---|:---:|
| 5 | **Revision archive / restart rebuild**: генерация разных `document_id` (`catalog-import-rev1`, `catalog-import-rev2`) исключала архивацию старой редакции как версии того же документа; отсутствовал авто-rebuild при старте приложения | **critical** | 1) В `extractor.py` и `consumer.py` логический идентификатор документа каталога стандартизирован как стабильный `catalog-site-{site_id}` (независимо от номера ревизии). При импорте новой редакции `RAGIndex.add_document` корректно определяет обновление документа, архивирует чанки предыдущей редакции в `archived_chunks` с `is_stale=True`, удаляет их из активного индекса и возвращает актуальные нормативы новой ревизии.<br>2) В `backend/app/main.py` в обработчик `lifespan(app)` встроен вызов `get_rag_service(session=rag_init_session)`, который автоматически выполняет `rebuild_from_storage` при запуске приложения.<br>3) В `backend/app/integration/ml.py` роут `/api/v1/maintenance/rag/search` передает сессию БД в `get_rag_service(session=session)` для гарантированного fallback-восстановления при первом обращении. | **RESOLVED** |
| 8 | **Durable Outbox / deduplication**: проверка дедупликации только по in-memory множеству `processed_event_ids` приводила к потере защиты при рестарте сервиса | **medium** | В `consumer.process_single_db_event` добавлена проверка статуса события непосредственно в базе данных: если `row.get("status") == "published"` и флаг `is_rebuild=False`, событие признается уже опубликованным и повторная обработка сбрасывается (`dropped`), гарантируя персистентную дедупликацию даже после очистки оперативной памяти. | **RESOLVED** |
| 9 | **Тестовое покрытие**: отсутствовали тесты последовательных ревизий каталога с вытеснением в архив, автоматического старта из lifespan и персистентной дедупликации | **medium** | В `tests/ml/test_team_ml03_dynamic_rag.py` добавлены 3 сквозных теста:<br>1) `test_sequential_source_import_revisions_archive_old_revision`: проверка вытеснения ревизии 1 ревизией 2, исключение старых чанков из поиска, генерация `STALE_REVISION_WARNING` при запросе архива и `DOCUMENT_NOT_FOUND` для несуществующей ревизии.<br>2) `test_automatic_app_startup_rebuild_from_published_outbox`: проверка автоматического восстановления индекса при старте.<br>3) `test_durable_deduplication_drops_already_published_events`: проверка персистентного отсечения повторов при очистке RAM. Общее число тестов ML03 увеличено до 44. | **RESOLVED** |

---

### 3. Сводная таблица соответствия всем критериям аудита

| № | Область проверки | Реализация в ветке | Статус |
|:---:|:---|:---|:---:|
| 1 | **Corpus / canonical hash / extraction** | SHA-256 манифеста `d13e...15c8`, канонический payload hash `af531...0427`. Сверка физических хэшей всех 5 файлов. Breadcrumbs `H1 > H2 > H3` и ревизионные `chunk_id`. Защита от подмены ACL. | **PASS** |
| 2 | **BM-RAG-01 / BM-RAG-02** | 6 бенчмарков с перефразированием: манометры 1.5–6.0 бар и фильтры >0.3 бар с точным извлечением нормативов и ссылок. | **PASS** |
| 3 | **Zero hallucination / Fail-closed** | Защита от подмены паспортов общими совпадениями. Неутвержденные бренды (KSB, Wilo, Grundfos, Danfoss) и типы оборудования (котлы, горелки, чиллеры) возвращают `DOCUMENT_NOT_FOUND`, пустые цитаты и `is_hallucination_blocked=True`. | **PASS** |
| 4 | **Server Principal / ACL / capability** | Роут `/api/v1/maintenance/rag/search` берет `site_id` и `user_role` строго из `v.principal`. Зарегистрирован capability `rag_search`, покрыто 180 инструментов (100%), 0 неучтенных роутов. | **PASS** |
| 5 | **Revision archive / restart rebuild** | Стабильный логический `catalog-site-{site_id}` гарантирует архивацию устаревших ревизий каталога с `is_stale=True`. Автоматический `rebuild_from_storage` при запуске в `lifespan(app)` и в роуте поиска. Запрос архива выдает предупреждение со ссылкой на активную ревизию. | **PASS** |
| 6 | **Prompt-injection / XML** | Атрибуты XML тегов `<source_evidence>` экранируются через `xml.sax.saxutils.quoteattr`, тело — через `escape`. Валидность проверена через `xml.etree.ElementTree`. | **PASS** |
| 7 | **CR-17: опрессовка** | Опрессовка коллектора 8.0 бар (`doc-stp-manifold-05`) ограничена ролью `chief_engineer`. Роль `executor` получает `ACCESS_DENIED`. | **PASS** |
| 8 | **Durable Outbox / worker** | `consumer.process_single_db_event` вызывается во вложенном savepoint воркера, загружает строки из `source_imports` по сессии, персистентно отсекает дубликаты опубликованных событий по статусу в БД. | **PASS** |
| 9 | **Тестовое покрытие** | 44/44 тестов ML03 успешно пройдены (1.52 с). 304/304 теста ML-пакета пройдены. Все репозиторные верификаторы зеленые. | **PASS** |

---

### 4. Результаты контрольного тестирования

* **Целевой набор тестов TEAM-ML03**: `tests/ml/test_team_ml03_dynamic_rag.py` — **44 из 44 успешно пройден** (1.52 с).
* **Полный тестовый набор подсистемы ML**: `tests/ml` — **304 пройден без единого сбоя** (51.31 с).
* **Репозиторные верификаторы**:
  - `scripts/verify_photo_manifest.py`: SUCCESS (PASS, 14 фото, 0 реальных клиентов).
  - `scripts/verify_split_leakage.py -v`: SUCCESS (PASS, 0 утечек).
  - `scripts/validate_artifacts.py`: OK.
  - `scripts/assistant_capabilities.py`: 180 инструментов, 100% покрытие API без неучтенных роутов.
  - `tests/backend/test_assistant_capabilities.py`: PASS.
