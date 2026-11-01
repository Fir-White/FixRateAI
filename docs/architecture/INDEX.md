# Контракты и архитектурные артефакты

Описание реализации находится в [общей архитектуре](../ARCHITECTURE.md), деталей API — в [service/api](../service/api.md), хранения — в [service/data](../service/data.md).

- [Канонические runtime DTO](../../backend/app/schemas/maintenance.py) и [контрактная копия](contracts/maintenance_contracts.py).
- [JSON Schema](contracts/maintenance.schema.json) и [исполняемые примеры](contracts/examples.json).
- [Компонентная схема](system_architecture.md), [Mermaid](diagrams/system_architecture.mmd), [draw.io](diagrams/system_architecture.drawio).
- [Матрица S01–S15 и исходная проверка 26.10.2026](architecture_validation.md) — исторический архитектурный разбор, не текущая сводка тестов.
- [Валидатор артефактов](validate_artifacts.py): `python -B docs/architecture/validate_artifacts.py`.

Два Markdown-пути схемы и матрицы используются существующим валидатором. Источники схем, примеры и скрипт сохраняются рядом; полное описание продукта здесь не дублируется.
