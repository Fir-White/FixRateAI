# Материалы аналитика

[Архитектура](../ARCHITECTURE.md) · [Разработка](../service/development.md) · [Планирование](../service/planning.md) · [Проверки](../service/verification.md).

## Передача Анастасии от 04.11.2026

В `dev` принят полный пакет `FixRate_AI_Analyst_Nastya_Complete_Handoff.zip`: **31 исходный файл — 10 Markdown, 7 JSON, 14 JPEG**. Предметные материалы и AN06, проект AN07 переданы как работа аналитика Анастасии (Насти). Обложка и вложенный обзор интеграции имеют отдельное происхождение: обзор обозначен в пакете как работа ассистента, его нельзя приписывать аналитику.

Исходные файлы сохранены побайтово. В их тексте пути `docs/...` и `tests/fixtures/...` отсчитываются от `docs/analysis/nastya-2026-11-04/source/`, сохранённого корня передачи. Они не заменяют действующие DTO, SQL, seed и исполняемые фикстуры проекта.

[Сопоставление с текущим dev и открытые вопросы](INTEGRATION.md) — рабочая точка передачи разработчикам. [Реестр происхождения](nastya-2026-11-04/provenance.json) содержит SHA-256 архива, исходный путь, путь в репозитории, размер и хеш каждого файла. База сверки реализации — `862dfc9428f7ad4c77cba18125e7226c654fde77`.

## Что уже подготовлено

| Работа аналитика | Материал | Следующий потребитель |
|---|---|---|
| Границы продукта | [Scope](nastya-2026-11-04/source/docs/domain/scope.md) | Тимлид: учесть ограничения и согласовать противоречия In/Out of Scope |
| Четыре предметные роли и доступ | [Роли](nastya-2026-11-04/source/docs/domain/roles.md), [пользовательские сценарии](nastya-2026-11-04/source/docs/domain/user_flows.md) | Backend/frontend/QA: сценарии с явным mapping действующего RBAC |
| ER-модель, словарь и M:N без копирования операций | [Словарь данных](nastya-2026-11-04/source/docs/domain/data_dictionary.md) | Тимлид/backend: связать с существующими SQL/ORM |
| Шесть операций и вопросы по нормам | [Регламенты пилота](nastya-2026-11-04/source/docs/domain/pilot_regulations.md) | ALG/backend: сохранить исходные значения и неизвестные единицы |
| Календарные TC-01–TC-05 | [Ожидаемый график](nastya-2026-11-04/source/docs/domain/expected_schedule.md) | ALG/QA: использовать входы; ожидания связывать с политикой из карты интеграции |
| AN06: шесть основных и три негативных кейса | [Критерии фотоотчёта](nastya-2026-11-04/source/docs/domain/inspection_criteria.md), [манифест v1.2](nastya-2026-11-04/source/tests/fixtures/evidence_manifest.json) | ML/frontend/QA: различать видимые признаки, чек-лист, акт и приёмку инженера |
| AN07 / FRAI-73 | [Проект протокола приёмки](nastya-2026-11-04/source/docs/acceptance/demo_acceptance.md) | QA: адаптировать роли, ID, статусы и API до сквозного прогона |
| Сопроводительные сведения | [Обложка и хеши](nastya-2026-11-04/source/HANDOFF_README.md), [исходный обзор ассистента](nastya-2026-11-04/source/docs/acceptance/INTEGRATION_REVIEW.md) | Все: учитывать происхождение, ограничения CASE-05/06 и ожидаемых AI-метрик |

Описания предметных сущностей и сценариев уже переданы. При изменении требований разработчик ссылается на конкретный документ/кейс, записывает отличие и основание решения. Составлять словарь, роли или эти кейсы заново не требуется. Наличие документа подтверждает передачу анализа; программный критерий подтверждается отдельным фактическим запуском в журнале проверок.

## Все JSON-примеры предметной модели

- [maintenance_cases.json](nastya-2026-11-04/source/docs/domain/examples/maintenance_cases.json)
- [maintenance_operations.json](nastya-2026-11-04/source/docs/domain/examples/maintenance_operations.json)
- [maintenance_task.json](nastya-2026-11-04/source/docs/domain/examples/maintenance_task.json)
- [operation_template.json](nastya-2026-11-04/source/docs/domain/examples/operation_template.json)
- [operation_to_equipment_links.json](nastya-2026-11-04/source/docs/domain/examples/operation_to_equipment_links.json)
- [regulation.json](nastya-2026-11-04/source/docs/domain/examples/regulation.json)

## Фотографии и ожидаемые сценарии AN06

Файлы передачи — демонстрационные изображения, включая синтетические изменения. Ожидаемые вердикты взяты из манифеста и не являются результатами инференса. Исходник не содержит точных URL и индивидуальных разрешений на изображения: заявления о лицензиях не считаются проверенными. Для внешнего повторного использования основания необходимо подтвердить у владельца материалов; сведения о ретуши сохраняются.

| Кейс / операция | До | После | Ожидание | Ограничение |
|---|---|---|---|---|
| CASE-01 / 1.1 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_01_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/case_01_after.jpg) | approved | Стрелка «до» изменена синтетически; показания и рабочий диапазон не подтверждены измерением |
| CASE-02 / 1.2 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_02_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/case_02_after.jpg) | manual_review | Видимый экран не подтверждает правильность протокола или квартиру |
| CASE-03 / 1.3 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_03_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/case_03_after.jpg) | manual_review | Индикация не доказывает исправность автоматики; исходник заявляет ретушь водяного знака |
| CASE-04 / 1.4 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_04_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/case_04_after.jpg) | manual_review | Одна сетка не доказывает чистку всех узлов; нужны два работника и ручные доказательства |
| CASE-05 / 1.5 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_05_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/case_05_after.jpg) | manual_review | «После» — synthetic_edited, удаление трещины; не факт ремонта и не проверка точности |
| CASE-06 / 1.6 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_06_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/case_06_after.jpg) | manual_review | Тождество узла не подтверждено; пока не считать позитивной эталонной парой |
| CASE-NEG-01 / 1.2 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_02_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/neg_01_after_blurry_glare.jpg) | rejected | Синтетические размытие и блик; целевые пороги не измерены |
| CASE-NEG-02 / 1.3 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_03_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/neg_02_after_blurry_glare.jpg) | rejected | Синтетические дефекты и несовпадение ракурса |
| CASE-NEG-03 / 1.1 | [До](nastya-2026-11-04/source/tests/fixtures/photos/case_01_before.jpg) | [После](nastya-2026-11-04/source/tests/fixtures/photos/case_02_before.jpg) | rejected | Разные классы оборудования; повторно используются имеющиеся файлы |

## Повторная проверка передачи

Из корня репозитория:

```powershell
python -B scripts/validate_analyst_handoff.py
python -B scripts/validate_artifacts.py
```

Первая команда проверяет полный состав, хеши, JSON, декодирование JPEG и ссылки манифеста внутри сохранённого корня пакета. Вторая включает эту проверку и проверяет текущие контракты, документацию и диаграммы проекта. Для дополнительной сверки исходного ZIP первой команде можно передать `--archive ПУТЬ_К_АРХИВУ`.

Команды не запускают ML, не создают задания и не присваивают PASS сценариям AN06/AN07. [Фактический протокол импорта](../service/verification.md#04112026-передача-материалов-аналитика-в-dev).
