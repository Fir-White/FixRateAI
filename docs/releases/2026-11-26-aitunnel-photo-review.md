# Фотоанализ через AI Tunnel, удаление CLIP и контроль обязательных фото (26.11.2026)

Ветка `feat/aitunnel-photo-review` (поверх `dev` `f395879`). Реализует блоки MVP-07, MVP-08, MVP-11, MVP-12 и MVP-14 (требования AT-08…AT-12, AT-16, AN06, AN07).

## Что изменено

1. **Удаление CLIP из пользовательского и сборочного путей:**
   - Удалены CLIP-модули и скрипты (`ml_service/app/cv/classifier.py`, `ml_service/app/cv/service.py`, `ml_service/inspect_pairs.py`, `scripts/prepare_clip.py`, `compose.ml.yaml`), а также поля `clip_*` из `MLConfig` и зависимости `torch`/`transformers`/`tokenizers` из `requirements.txt`.
   - Основным провайдером фотоанализа стал `aitunnel` с vision-моделью `qwen3.7-flash` по умолчанию (`backend/app/config.py`, `deploy/compose.yaml`, `.env.example`), явной альтернативой остаётся локальный `ollama`. Контролируемая недоступность провайдера возвращает `unavailable`/`failed` без fallback на CLIP или эвристику.
   - Устаревший `build_bundled_image.py` переведён на упаковку RF-модели без CLIP-кэша; `scripts/verify_compose.py`, `scripts/start_local.py` и `tests/backend/test_model_bundle.py` приведены в соответствие.

2. **Фотоанализ для инженера и фотоагент в чате ассистента:**
   - В `QualityTaskPage` и `PhotoReviewCard` на экране приёмки инженер видит краткие наблюдения на русском языке без внутренних кодов и процентов уверенности, одно напоминание «Проверьте фотографии самостоятельно.» и возможность повторно запустить анализ даже при существующем заключении; исторические CLIP-заключения помечаются как результат прежней модели.
   - Добавлен специализированный инструмент `call_photo_agent` и подтверждаемое предложение `propose_photo_review` в `backend/app/assistant/tool_agent_tools.py` с системным промптом [photo.md](../../backend/app/assistant/prompts/photo.md).
   - `model_catalog.model_supports_vision` и `tool_agent.run_loop` проверяют поддержку изображений у выбранной чат-модели и не передают сырые пиксели в текстовые модели напрямую, направляя осмотр через `call_photo_agent`.

3. **Обязательность фото по каждому пункту чек-листа и привязка оборудования:**
   - Логика сдачи `validate_submission_evidence` в [photo_evidence.py](../../backend/app/integration/photo_evidence.py) и [main.py](../../backend/app/main.py) требует пару «до/после» одного ракурса (`view_key`) и одной единицы оборудования (`equipment_id`) только для пунктов с `photoRequired=true`; при `photoRequired=false` сдача проходит без фото.
   - `projections.report_view` включает `equipmentId` в проекцию `execution.photos`, а проверка готовности в ассистенте [task_execution.py](../../backend/app/assistant/task_execution.py) сверяет совпадение `equipmentId` пары и принадлежность оборудования текущему наряду.

## Пользовательские сценарии и ограничения

- **Исполнитель:** видит обязательность фото на уровне конкретного пункта чек-листа; сдача без обязательной пары, с разными ракурсами или с кадрами от разного оборудования отклоняется с HTTP 422 и поясняется в чате.
- **Инженер:** получает краткий разбор фото на странице задания (после сдачи и по кнопке анализа/обновления) или через чат ассистента (`call_photo_agent` и карточка подтверждения `propose_photo_review`). ИИ не принимает работу автоматически.
- **Совместимость:** SQL-миграции не менялись; сохранённые ранее CLIP-заключения в `ai_quality_checks` остаются читаемыми.

## Проверки и оставшиеся ограничения

См. фактические результаты прогонов в [журнале проверок](../service/verification.md#26112026--удаление-clip-и-переход-на-ai-tunnel-для-фотоанализа). В данном окружении отсутствуют живая PostgreSQL, собранный локальный Compose/Docker-образ и приватный ключ AI Tunnel, поэтому интеграционные тесты БД (`tests/backend/`), живой прогон облачного API (`verify_compose.py --cloud-ai`) и браузерный E2E Playwright в этот прогон не входили и требуют запуска на стенде с PostgreSQL/ключом.
