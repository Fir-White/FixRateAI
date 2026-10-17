# FixRate_AI

## Архитектура базы данных

В проекте FixRate AI используется PostgreSQL с расширением
pgvector для хранения реляционных данных и векторного поиска.

База данных включает 18 таблиц, охватывающих заявки,
дефекты, AI-анализ, нормативные справочники и сметы.

### ER-диаграмма (Crow's Foot)

![ER-диаграмма базы данных FixRate AI](docs/database/erd.svg)

**Документация:**

- [Открыть ER-диаграмму в SVG](docs/database/erd.svg)
- [Редактировать диаграмму в draw.io](docs/database/erd.drawio)
- [Спецификация базы данных](docs/database/specification.md)
- [Сценарии тестирования](docs/database/test_scenarios.md)