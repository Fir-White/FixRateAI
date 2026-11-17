# P0-аудит инструментов ассистента, 15.11.2026

## Подтверждённая первопричина

В рабочей PostgreSQL найден ход `2e7e0b73-e517-4691-afbe-3239e47801e1`: инструменты `registry_read` и `overview_read` получили по три отказа 422. Старый журнал содержит только имя, время, статус и HTTP-код. **Исходные аргументы и точный текст старых ошибок не сохранены; восстановить их достоверно нельзя.** Объяснение модели не заменяет эти доказательства.

На текущем коде утверждение «view.limit и view.offset запрещены» неверно. `describe()` экспортирует `ResultView.model_json_schema()`, а `validate_arguments()` проверяет тот же ResultView. `view.offset` — integer >= 0; `view.limit` — integer 1..25; `path` — массив строк до шести элементов; лишние поля запрещены. `registry_read` и `overview_read` не принимают пагинацию в `query`. Generic-сообщение «Проверьте параметры просмотра результата» скрывало поле и причину, а агент повторял неудачные вызовы и делал неподтверждённые выводы о данных.

Общая структура inputSchema этих двух инструментов (опущены только описательные title):

```json
{"type":"object","additionalProperties":false,"required":[],"properties":{"path":{"type":"object","properties":{},"required":[],"additionalProperties":false},"query":{"type":"object","properties":{},"required":[],"additionalProperties":false},"view":{"type":"object","additionalProperties":false,"properties":{"path":{"type":"array","items":{"type":"string"},"maxItems":6},"offset":{"type":"integer","minimum":0,"default":0},"limit":{"type":"integer","minimum":1,"maximum":25,"default":25},"q":{"type":"string","maxLength":200,"default":""},"text_offset":{"type":"integer","minimum":0,"default":0},"text_limit":{"type":"integer","minimum":1,"maximum":6000,"default":6000}}}}}
```

## Воспроизведение на реальных API и PostgreSQL

Инструмент `registry_read`, GET `/api/v1/maintenance/registry`:

```json
{"view":{"path":["items"],"offset":0,"limit":25}}
```

Допустимая команда. Возвращает страницу реального списка оборудования.

```json
{"view":{"path":["items"],"offset":0,"limit":100}}
```

Отказ 422: `{"code":"INVALID_VIEW","issues":[{"field":"view.limit","type":"less_than_equal"}]}`. Одно исправление limit до 25 проходит ту же серверную валидацию и читает реальные записи.

```json
{"query":{"offset":0,"limit":25},"view":{"path":["items"]}}
```

Отказ: неизвестные query-параметры limit/offset, допустимых query-параметров нет. Они переносятся в view без изменения фильтров ресурса и проверяются заново.

`{"view":{"path":["objects"],"offset":0,"limit":25}}` соответствует JSON Schema, но не структуре результата registry: поля objects там нет. Для этой конкретной ошибки проекции один повтор читает разрешённый корень, где есть site_id/site_name/timezone/systems/items. Это не отменяет аутентификацию и не подменяет список объектов.

## Исправления и границы

- **read_transport.py:** максимум две попытки только для GET-инструмента с mode=read и только для исправимых 422. Не удаляет произвольные фильтры, не подставляет неизвестные ID, не повторяет запись или 403/404/5xx. Ошибка транспорта преобразуется в 502.
- **tools.py:** валидация view сообщает код, поле и тип ошибки без исходных значений. Backend-валидация и проверки прав сохранены.
- **service.py:** GET-чтение использует ограниченное восстановление. В trace сохраняются имя, безопасное представление аргументов, сводка результата, тип ошибки, attempt/retry_count. Полные значения body и произвольные поисковые строки не журналируются; строки заменяются длиной и SHA-256, секретные поля маскируются. Структура trace не является внутренними рассуждениями модели.
- **assistant_workspace.py / inventory_read:** постраничная инвентаризация зданий с активным членством пользователя. Для каждого здания применяется его фактическая роль; роль текущего здания не переносится на другое. Сессия и выбранное здание не изменяются. Страница — 25 единиц оборудования.
- **inventory_report.py:** исходный запрос получает отчёт из PostgreSQL без генерации фактов моделью. Отдельно обозначены отсутствие зданий, пустой реестр, отсутствие доступа, сбой backend и частичное чтение. Есть предел 200 страниц. Excel не нужен. Число конфигураций обслуживания не выдаётся за число пунктов чек-листа. Наличие незавершённых плановых заданий не выдаётся за физическую диагностику оборудования.
- Проверка пробелов охватывает опубликованные операции, подтверждённость нормы/единицы/длительности и статус оборудования. Она **не сертифицирует выполнимость плана**: смены, квалификации и загрузка проверяются механизмом подбора назначения.

## Проверка регистрации

Реестр: registry_read; доступные здания: sites_list; межобъектный отчёт: inventory_read; оборудование: equipment_find/equipment_read; регламенты: regulations_read; графики: calendar_read/canonical_calendar/calendar_preview; доступность и смены: staff_read/staff_calendar; подбор: assignment_context/assignment_preview/assignment_prepare. Существующий тест покрытия пользовательских API и экспорт contracts/assistant-tools.json проверяют транспорт и регистрацию. Смена пароля по-прежнему исключена.

## Проверки и успешная трасса

Итоговый прогон — **83 passed**: P0, assistant, capabilities, Excel workbooks и привязка вложений, реальная PostgreSQL и ASGI. Отдельный live-сценарий запускает точный запрос с настроенным локальным провайдером; источник ответа — тот же backend. Успешные результаты не подменяются. Ошибки 403/503 в тесте транспорта вводятся явно для проверки отказа и отсутствия повторов. Sentinel NoModel в отдельном тесте только запрещает генерацию данных моделью, а не подменяет ответ PostgreSQL.

В сценарии создаются настоящие тестовое оборудование и опубликованный регламент через API. Ответ сопоставляется с registry и реальным числом операций. Проверены пустой реестр, исполнитель без права чтения, два здания с разными ролями, отсутствие вызова модели для фактического отчёта, маскирование секретов, страница 25 из 30 и бюджет до 40 SELECT для чтения такой страницы.

Пример успешной trace (тестовая БД; значения счётчиков зависят от набора):

```json
{"tool":"inventory_read","attempt":1,"retry_count":0,"arguments":{"query":{"site_offset":0,"offset":0}},"status":"completed","result":{"type":"object","total":4,"offset":0,"limit":25,"site_status":"ok"},"error_type":null}
```

Полные результаты, воспроизведение и схема: `reports/assistant-p0-backend/pytest.log`. Живой сценарий и окончательные тесты: `reports/assistant-p0-live/`. Отчёты содержат только изолированные тестовые данные; private env не публикуется.

## Изменённые файлы этого аудита

`backend/app/assistant/tools.py`, `backend/app/assistant/service.py`, `backend/app/assistant/read_transport.py`, `backend/app/assistant/inventory_report.py`, `backend/app/assistant/prompts/final.md`, `backend/app/integration/assistant_workspace.py`, `contracts/assistant-tools.json`, `tests/backend/test_assistant_p0.py`, `docs/ASSISTANT_P0_AUDIT.md`, `docs/service/assistant.md`, `docs/service/verification.md`.

SQL-миграций нет. Данные, фото, пользовательские роли и алгоритмы планирования не переписываются. Локальная публикация использует существующую процедуру с резервной копией, проверкой здоровья и сравнением строк БД/фотографий.
