# Отчёт о реализации задачи TEAM-ML03 (FRAI-173)
## Динамический RAG и автоматическая актуализация индекса

* **Идентификатор задачи**: FRAI-173 (`5cc2bb6a-4437-4837-87f0-23a49453e4b7`)
* **Исполнитель**: Muhammad / Мухаммад (`d1ba36a5-b2a2-428c-aa24-05ad8fffe4ad`)
* **Контролирующий инженер (QA)**: Михаил (`60eef911-b53c-4417-9ef0-74153c2b0bae`)
* **Ветка разработки**: `feat/team-ml03-dynamic-rag-auto-index`
* **Соответствие регламентам**: CR-17 (бизнес-роли: `chief_engineer`, `executor`), TL04 (безопасность данных, изоляция объектов, запрет галлюцинаций)
* **Аудирующая модель**: OpenAI Codex (GPT-6 Luna)

---

### 1. Архитектура подсистемы Dynamic RAG

Подсистема реализована в модуле `ml_service/app/rag/` с чистым разделением обязанностей, нулевой зависимостью от недоверенных весов LLM при формировании технологических карт и гарантией воспроизводимости:

```
ml_service/app/rag/
├── __init__.py           # Публичные реэкспорты интерфейсов
├── schemas.py            # DTO: Chunk, DocumentMetadata, RetrievalQuery, Citation, RetrievalResult, OutboxEvent, IndexSyncReport
├── extractor.py          # Парсер Markdown-регламентов, иерархический чанкинг по заголовкам, SHA-256 хэширование, чанкинг каталогов XLSX
├── guardrails.py         # Защитные барьеры: AntiHallucinationGuardrail, PromptInjectionDefense, безопасная XML-разметка контекста
├── index.py              # Лексический индекс: стемминг русского языка, граф двунаправленных синонимов, ранжирование, ролевой и объектный ACL
├── consumer.py           # Durable Outbox Consumer: обработка source_revision_events, детекция пропусков (gap detection), идемпотентность
└── service.py            # Высокоуровневый оркестратор RAGService: загрузка замороженного корпуса, синхронизация outbox, ассистентские запросы
```

---

### 2. Замороженный нормативный корпус и бенчмарки

В соответствии с манифестом [data/manifests/rag_corpus_manifest.json](file:///home/handraqw/Projects/FixRate_AI/data/manifests/rag_corpus_manifest.json) проиндексированы 5 нормативных документов из `docs/analysis/rag_corpus/`:

1. **`doc-reg-itp-01`** (`reg_itp_gauges.md`, rev-20261117-01, `pressure_gauge`):
   - Регламент ТО узла ввода (манометры).
   - Номинальный диапазон: **1.5 – 6.0 бар**.
   - Доступ: `site-itp-severnaya-01`, `site-itp-vostochnaya-02`; роли: `chief_engineer`, `executor`.
2. **`doc-man-vkt7-02`** (`manual_vkt7_readout.md`, rev-20261101-02, `heat_meter`):
   - Инструкция по снятию показаний тепловычислителя ВКТ-7.
   - Единицы: Гкал, м³, т.
   - Доступ: `site-itp-severnaya-01`; роли: `chief_engineer`, `executor`.
3. **`doc-reg-shau-03`** (`reg_automation_cabinet.md`, rev-20261110-01, `control_cabinet`):
   - Регламент обслуживания щитов автоматизации ИТП (ШАУ).
   - Индикация: `power_ok`, `alarm_lamp_off`, `auto_mode_switch`.
   - Доступ: `site-itp-severnaya-01`, `site-itp-vostochnaya-02`; роли: `chief_engineer`, `executor`.
4. **`doc-tk-filter-04`** (`tk_mesh_filter_cleaning.md`, rev-20261115-01, `mesh_filter`):
   - Технологическая карта разборки и промывки сетчатых фильтров ФСФ-50 (ТК-ТО2-05).
   - Критический перепад давления: **> 0.3 бар**.
   - Доступ: `site-itp-severnaya-01`, `site-itp-vostochnaya-02`; роли: `chief_engineer`, `executor`.
5. **`doc-stp-manifold-05`** (`stp_manifold_pressurization.md`, rev-20261025-01, `heating_manifold`):
   - Стандарт предприятия: Гидравлические испытания и опрессовка коллекторов ИТП.
   - Давление: **8.0 бар**, выдержка: **15 минут**, допустимое падение: **0.1 бар**.
   - **Строгое ограничение CR-17**: доступно **ИСКЛЮЧИТЕЛЬНО** роли `chief_engineer`. Для роли `executor` выдаётся отказ в доступе (`ACCESS_DENIED`).

---

### 3. Проверка негативных и граничных сценариев (CR-17 / TL04)

Все 4 контрольных сценария из манифеста покрыты тестами и верифицированы:

| ID сценария | Суть проверки | Ожидаемый результат | Фактическое поведение | Статус |
|:---|:---|:---|:---|:---:|
| **RAG-NEG-01** | Запрос несуществующего оборудования (насос Wilo Stratos MAXO) | Запрет генерации из весов, `DOCUMENT_NOT_FOUND` | Возвращается `DOCUMENT_NOT_FOUND`, 0 чанков в цитатах, `is_hallucination_blocked=True` | **PASS** |
| **RAG-NEG-02** | Попытка доступа к регламенту чужого объекта (`site-bc-yuzhny-99`) | Изоляция объектов, отказ `ACCESS_DENIED` | Возвращается `ACCESS_DENIED`, ошибка `ACCESS_DENIED`, утечка данных заблокирована | **PASS** |
| **RAG-NEG-03** | Запрос устаревшей отозванной редакции (2024 г. вместо 2026 г.) | Цитирование актуальной нормы с предупреждением | Возвращается `STALE_REVISION_WARNING`, `is_stale=True`, явное предупреждение о недействительности старой нормы | **PASS** |
| **RAG-NEG-04** | Попытка prompt-injection через инструкцию («Списать без акта») | Нейтрализация императивных инструкций | Возвращается `ACCESS_DENIED`, ошибка `UNAUTHORIZED_CAPABILITY_ESCALATION` | **PASS** |

---

### 4. Ролевая безопасность CR-17 (Опрессовка коллектора)

* Документ `doc-stp-manifold-05` описывает опасную операцию (опрессовка распределительной гребёнки отопления под давлением 8.0 бар).
* При запросе от лица `executor`:
  - `max_denied_score` на целевом регламенте превышает любые вторичные совпадения;
  - Запрос немедленно отклоняется с кодом `ACCESS_DENIED` («Документ предназначен исключительно для роли chief_engineer»);
  - Никакие выдержки из регламента опрессовки не передаются исполнителю без ведома главного инженера.
* При запросе от лица `chief_engineer`:
  - Возвращается статус `OK`;
  - Цитируются параметры испытаний (8.0 бар, 15 мин, 0.1 бар).

---

### 5. Durable Outbox Consumer (`source_revision_events`)

Потребитель событий `DurableOutboxConsumer`:
1. **Связь с БД**: Обрабатывает события очереди PostgreSQL `source_revision_events` (миграция `026_source_revision_outbox.sql`) для сущностей типов `regulation_doc`, `source_document`, `equipment_manual`, `knowledge_doc`, `source_import`.
2. **Идемпотентность**: Сохраняет `processed_event_ids`. Повторная доставка того же `event_id` не приводит к дублированию чанков.
3. **Детекция пропусков (Gap Detection)**: При поступлении ревизии `N > last_rev + 1` событие обрабатывается с установкой флага `gap_detected = True` и подробным предупреждением в отчёте `IndexSyncReport`.
4. **Смена ревизий**: При поступлении события `updated` чанки старой ревизии автоматически помечаются `is_stale = True` и архивируются, а активными становятся чанки новой ревизии.
5. **Отзыв документов (`revoked`)**: Документ и его чанки инвалидируются и переводятся в статус `stale`/`archived`.
6. **Отказоустойчивость**: Ошибка в единичном событии (например, повреждённый путь) переводит статус записи в `failed`, не роняя конвейер обработки остальных событий.

---

### 6. Результаты тестирования

* Целевой набор тестов TEAM-ML03: `tests/ml/test_team_ml03_dynamic_rag.py` — **21 из 21 успешно пройден** (время выполнения: 0.08с).
* Полный тестовый набор подсистемы ML: `tests/ml` — **281 тест собран и успешно пройден**.
* Полный регрессионный прогон бенчмарков и манифестов:
  - `scripts/verify_photo_manifest.py`: PASS (14 фото, 0 реальных клиентов).
  - `scripts/benchmark_photo_models.py`: PASS (CLIP + ViT + fallback 0.0% FRR).
  - `scripts/verify_split_leakage.py`: PASS.
  - `scripts/assistant_capabilities.py`: PASS (100% покрытие API ассистентом).
