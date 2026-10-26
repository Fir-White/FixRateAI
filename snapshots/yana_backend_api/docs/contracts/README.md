# Контракты интеграции FixRate AI

Канонический контракт находится в [fixrate-contracts.json](fixrate-contracts.json), формат
JSON Schema Draft 2020-12. Примеры находятся в [examples.json](examples.json).

## Общие правила

- `schema_version` — версия формата (`1.0`); `pipeline_version` — версия реализации
  пайплайна и не заменяет версию контракта.
- `request_id` идентифицирует пользовательскую заявку, `job_id` — конкретный запуск.
  Оба идентификатора сохраняются во всех промежуточных и итоговых ответах.
- Для каждого значения сохраняется `provenance.source`: `photo`, `text`, `object` или
  `user` для входа и тип модуля (`cv`, `nlp`, `rag`, `calc`) для производного значения.
- Физические единицы ограничены `mm`, `m`, `m2`, `m3`, `pcs`, `kg`. Неподдерживаемая
  единица — `failed` с кодом `INVALID_UNIT`, а не неявное преобразование.
- Отсутствующий масштаб, норматив или цена не заменяются предположением: возвращается
  `needs_clarification` или `not_found`.
- `EstimateItem` содержит единый набор полей: `item_id`, `work_type`, `quantity`, `unit`,
  `rate_code`, `price`, `source_id`, `formula`, `validation_status`, `warnings`.
- Ошибка модуля имеет отдельный статус `failed`; `not_found` означает корректно
  отработавший поиск без подходящего результата.

## Границы модулей

| Модуль | Вход | Выход |
|---|---|---|
| Backend | `JobRequest` | `JobResponse` или `ErrorResponse` |
| CV | фото из `JobRequest.photos` | `CVResult` |
| NLP/OCR | текст и извлечённые страницы | `NLPResult` |
| RAG | нормализованный дефект и измерения | `RateSearchResult` |
| Валидатор | результаты CV/NLP/RAG | статусы, `validation_status`, предупреждения |
| Расчётный движок | подтверждённые измерения и расценка | `EstimateItem`, `total_cost` |

## Совместимость

Текущие DTO ML Service (`JobRequestDTO`, `JobResponseDTO`) сохраняют обратную
совместимость с работающим `/api/v1/process`. При интеграции Backend использует
этот документ как внешний контракт и выполняет явное отображение legacy-полей
(`work_name`, `base_price`, `source_ref`, `formula_id`) в канонические поля.
Расширение до `schema_version=1.1` выполняется отдельной задачей с миграцией
обоих потребителей.

Для проверки примеров:

```powershell
cd ml_service
python -m pytest -q tests/test_contract_examples.py
```
