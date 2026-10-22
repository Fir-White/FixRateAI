# FRAI — единые JSON-контракты модулей

**Статус:** DONE (контракт `1.0`)  
**Зона:** Backend / ML Service  
**Назначение:** зафиксировать обмен до подключения реальных CV/NLP/RAG-моделей.

## Результат

- [JSON Schema](../contracts/fixrate-contracts.json) Draft 2020-12 — канонические
  входы/выходы Backend, CV, NLP/OCR, RAG, валидатора и расчётного движка.
- [Примеры](../contracts/examples.json) — успешный, неполный, ошибочная единица
  и отсутствие масштаба.
- [Правила интеграции](../contracts/README.md) — идентификаторы, версии,
  provenance, единицы, статусы и отображение legacy DTO.
- `ml_service/app/schemas/request.py` и `response.py` теперь явно передают
  `schema_version: "1.0"` в рабочем API.

## Ключевые решения

1. `request_id` — идентификатор заявки, `job_id` — идентификатор конкретного
   запуска. Оба значения проходят через все результаты.
2. Источник каждого значения хранится в `provenance.source`; допустимы
   `photo`, `text`, `object`, `user` и источники модулей.
3. Неизвестные масштаб, норматив или цена не заменяются оценкой: используются
   `needs_clarification`/`not_found`. Поломка модуля — `failed`.
4. Каноническая позиция содержит `item_id`, `work_type`, `quantity`, `unit`,
   `rate_code`, `price`, `source_id`, `formula`, `validation_status`, `warnings`.
5. Текущий `/api/v1/process` сохранён совместимым. Backend при сохранении
   результата делает явное отображение legacy-полей ML (`work_name`,
   `base_price`, `source_ref`, `formula_id`) в канонические поля.

## Проверка

Из корня репозитория в PowerShell:

```powershell
cd ml_service
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_contract_examples.py
python -m pytest -q
```

Тест `test_contract_examples.py` машинно валидирует пять примеров JSON и
отдельно проверяет отклонение неподдерживаемой единицы `meters`.
