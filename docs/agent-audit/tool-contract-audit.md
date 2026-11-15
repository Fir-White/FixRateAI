# Контракты инструментов

Cycle 9 дополнительно проверяет повторную нормализацию write DTO: пропущенные PATCH-поля не должны превращаться в default=null. AG-015 исправлен exclude_unset без ослабления валидатора; nullable и запрещённый null различаются. INVALID_COMMAND содержит ограниченные field/type без raw input/ctx. Native Ollama AgentStep использует объект аргументов на своём wire, адаптер преобразует его в прежний arguments_json string; каноническая/облачная DTO и фактические backend capability schemas сохранены. Это явная транспортная адаптация, а не поддержка произвольного Python/невалидного JSON.

Manifest содержит **167 capability**, из них 73 изменяющих. Схемы формируются из настоящего OpenAPI/backend, а не из отдельно написанных LLM-контрактов. `scripts/assistant_capabilities.py --write` обновляет export; coverage test проверяет отсутствие неучтённых пользовательских маршрутов. Смена пароля исключена по правилам проекта.

Матрица **619/619**: каждое объявление схемы, неизвестный root/query, запрещённая роль и чужой диалог для записи. MCP вызывает настоящий ASGI/backend/PostgreSQL, а не фиктивную выдачу. Модели эти 619 случаев не отправляются. Отдельные P0 tests проверяют required path, ограничения view, регистрацию оборудования/регламентов/графиков/доступности и ошибки 403/503.

AG-004 воспроизведён реальной моделью: equipment_list с query:null и выдуманным view.path; catalog_read/registry_read с цепочкой систем/оборудования вместо реального equipment_id. Исправлена транспортная коррекция, не серверная строгость. Максимум две коррекции только GET; повтор после envelope-fix разрешён лишь для неизвестной проекции. Ошибки 403/5xx и отправленные write не ретраятся. Неизвестные фильтры/ID не удаляются ради успешного ответа.

Потоки PostgreSQL: inventory_read (доступные здания и scope каждой membership), equipment_find/read, regulations_read и frozen operation data, tasks_find/tasks_analyze, workforce/staff/availability, planning_context/drafts/optimization. Workbook не необходим для этих API. No Excel, no assets, access_denied, argument_validation, not_found и backend_unavailable — разные состояния.

Новый фильтр **cohort=unfinished|execution_pending|in_review** добавлен в настоящий endpoint task-analysis, строгий whitelist и manifest. starts_on/ends_on отбирают дату назначенного начала, иначе нормативный день; вывод описывает эту основу. Агрегаты общего объекта и выбранного поднабора не смешиваются.

В equipment_find добавлен необязательный **asset_code**, literal case-insensitive совпадение. Он не является поиском по name/location, сохраняет site/role фильтры, экранирует SQL LIKE `%`, `_`, backslash и не теряется за 25 совпадениями названий. q/offset совместимы. Для явного кода grounding использует этот фильтр и фактический ID; для регламентов — точные service-configurations, не tasks_find и не глобальный список editions. Пример view отражён также штатным export в contracts/assistant.schema.json. Capability export/check по-прежнему 167: новые операции не добавлялись, расширены реальные query-схемы.

Трасса GET содержит имя, номер попытки/retry_count, безопасные аргументы, stage/code/error_type, сводку результата, полноту и snapshot_id. Строковые значения хешируются, секретные поля редактируются, body не журналируется. Свободный текст модели и скрытые рассуждения не заменяют эту трассу. Ошибка инструмента не доказывает пустой реестр. Evidence gate проверяет арифметику и соответствие фильтров до полного аналитического отчёта.

Ограничение доказательства: матрица не доказывает корректность бизнес-параметров каждого положительного write. Положительные подтверждения проверяются отдельно и только на тестовых данных; полный API coverage не равен полной точности LLM.
