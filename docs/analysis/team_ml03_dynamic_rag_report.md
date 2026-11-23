# Отчёт о реализации задачи TEAM-ML03 (FRAI-173)
## Динамический RAG и автоматическая актуализация индекса (Ревизия 2 / Пост-аудит)

* **Идентификатор задачи**: FRAI-173 (`5cc2bb6a-4437-4837-87f0-23a49453e4b7`)
* **Исполнитель**: Muhammad / Мухаммад (`d1ba36a5-b2a2-428c-aa24-05ad8fffe4ad`)
* **Контролирующий инженер (QA)**: Михаил (`60eef911-b53c-4417-9ef0-74153c2b0bae`)
* **Ветка разработки**: `feat/team-ml03-dynamic-rag-auto-index`
* **Соответствие регламентам**: CR-17 (бизнес-роли: `chief_engineer`, `executor`), TL04 (безопасность данных, изоляция объектов, запрет галлюцинаций)
* **Аудирующие модели**: OpenAI Codex (GPT-6 Luna) & GPT-5.6 Terra

---

### 1. Архитектура подсистемы Dynamic RAG

Подсистема реализована в модуле `ml_service/app/rag/` с чистым разделением обязанностей, аутентифицированным серверным роутом и защитой от инъекций:

```
ml_service/app/rag/
├── __init__.py           # Публичные реэкспорты интерфейсов и get_rag_service
├── schemas.py            # DTO: Chunk (с breadcrumb и chunk_index), DocumentMetadata, RetrievalQuery, Citation, RetrievalResult, OutboxEvent (все типы change_type), IndexSyncReport
├── extractor.py          # Иерархический парсер Markdown (H1 > H2 > H3), коллизионно-стойкие chunk_id, SHA-256, санитизация текста
├── guardrails.py         # Защитные барьеры: AntiHallucinationGuardrail, PromptInjectionDefense, полное XML-экранирование контекста <source_evidence>
├── index.py              # Лексический индекс: стемминг, синонимы, блэклист неутвержденного оборудования, ролевой и объектный ACL, архив ревизий
├── consumer.py           # Durable Outbox Consumer: вложенные savepoints (begin_nested), сверка SHA, обработка source_revision/text_change/deleted
└── service.py            # Оркестратор RAGService: проверка хэшей манифеста и файлов, синглтон get_rag_service, ассистентские запросы
```

Серверная интеграция:
- Роут `GET /api/v1/maintenance/rag/search` в `backend/app/integration/ml.py` с автоматическим извлечением `v.principal.site_id` и `v.principal.role`.
- Инструмент ассистента `rag_search` в `backend/app/assistant/capabilities.py`, покрытие 180 инструментов в `contracts/assistant-tools.json`.

---

### 2. Исправления по замечаниям аудитов GPT-6 Luna и GPT-5.6 Terra

| Замечание аудита | Критичность | Внедрённое исправление | Статус |
|:---|:---:|:---|:---:|
| **Не сверялись хэши манифеста и документов** | critical | В `rag_corpus_manifest.json` добавлены точные SHA-256 для всех 5 документов. В `RAGService.load_frozen_corpus` встроена валидация `verify_manifest_integrity()`. При расхождении хэша выбрасывается `ValueError`. | **RESOLVED** |
| **Коллизии chunk_id и потеря контекста заголовков** | critical | Формат `chunk_id`: `{doc_id}:{revision}#{sec_slug}#{chunk_index}`. Введена иерархическая строка `section_path` (хлебные крошки: `H1 > H2 > H3`), включаемая в `clean_text` для поиска. | **RESOLVED** |
| **«Дай инструкцию по Wilo» возвращал OK** | critical | Введён блэклист неутверждённых брендов (`wilo`, `grundfos`, `danfoss` и др.) и разделение поисковых токенов на специфические и общие. Если специфические токены отсутствуют в документе, совпадение по общим словам (`инструкция`, `то`) даёт score 0, вызывая `DOCUMENT_NOT_FOUND`. | **RESOLVED** |
| **ACL задавался параметром, а не аутентификацией** | critical | Создан серверный эндпоинт `GET /api/v1/maintenance/rag/search`, где `site_id` и `user_role` извлекаются исключительно из серверного объекта `v.principal`. Зарегистрирован capability ассистента `rag_search`. | **RESOLVED** |
| **Запрос любой старой редакции ставил warning** | high | Хранится реестр зарегистрированных ревизий `document_revisions[doc_id]`. Запрос несуществующей ревизии возвращает `DOCUMENT_NOT_FOUND`. Запрос известной superseded-ревизии возвращает `STALE_REVISION_WARNING`. | **RESOLVED** |
| **Prompt Injection через недоверенный чанк / теги** | critical | В `format_safe_context` внедрено экранирование `xml.sax.saxutils.escape` для всех атрибутов и тела чанка. Текст очищается `sanitize_untrusted_text` от тегов `<script>`, `<system>` и закрывающих `</source_evidence>`. | **RESOLVED** |
| **Durable Outbox: транзакция падала на ошибке** | critical | В `process_db_events` каждая запись обрабатывается во вложенной транзакции `with session.begin_nested():`. При ошибке savepoint откатывается, а статус обновляется на `failed` без поломки внешней транзакции. | **RESOLVED** |
| **Контракт change_type не принимал source_revision** | critical | В DTO `OutboxEvent` расширен `change_type`, поддержаны `source_revision`, `text_change`, `created`, `updated`, `revoked`, `deleted`. Добавлена проверка `source_sha256`. | **RESOLVED** |

---

### 3. Результаты контрольного тестирования

* Целевой набор тестов TEAM-ML03: `tests/ml/test_team_ml03_dynamic_rag.py` — **31 из 31 успешно пройден** (1.24с).
* Полный тестовый набор подсистемы ML: `tests/ml` — **291 тест собран и успешно пройден**.
* Полный регрессионный прогон бенчмарков и манифестов:
  - `scripts/verify_photo_manifest.py`: SUCCESS (PASS, 14 фото, 0 реальных клиентов).
  - `scripts/verify_split_leakage.py -v`: SUCCESS (PASS, 0 утечек).
  - `scripts/validate_artifacts.py`: OK.
  - `scripts/assistant_capabilities.py`: OK (180 инструментов, 0 неучтенных роутов).
  - `tests/backend/test_assistant_capabilities.py`: PASS.
