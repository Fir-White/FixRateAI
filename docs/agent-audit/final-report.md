# Срез автономного аудита

Статус: контрольная точка перед окончательной проверкой зафиксированного среза. Исходный worktree kran_dev чист, HEAD **f8178754433d57cf5cfeb2690eb64b2fe0207ec2**; runtime, фото, роли и производственная БД не изменялись. Исправления находятся только в `audit/agent-red-team-20261115` отдельного worktree с собственными Git-метаданными. Push/merge/deploy не выполнялись.

Подтверждено и исправлено восемь классов: личный DELETE директора; доверие противоречивым агрегатам; потеря условий аналитики; составные read-аргументы; недостаточная диагностика nested JSON Ollama; пересортировка закреплённой бригады; отсутствие поиска перед заявлением «не найдено»; смешивание заданий/чужих регламентов с конфигурациями конкретного актива. [Воспроизведения и красные протоколы](known-defects.md) сохранены, ошибки oracle отдельно помечены.

Изменённые зоны:

- `backend/app/assistant/`: evidence, analysis_scope, grounding, read_transport, task_report, service и одна предметная подсказка prompt. Серверная проверка и подтверждение не заменены LLM.
- `backend/app/integration/assistant_workspace.py`, `task_analytics.py`: строгий cohort и точный поиск asset_code, прежний q остаётся совместимым; схемы получаются из настоящего OpenAPI.
- `backend/app/security/sessions.py`: узкое исключение личного чата; `schemas/assistant.py`: описание view.path.
- `backend/app/scheduling/optimization.py`: frozen records целиком, model version v3; нормы, состав, hard validator и функция цели не ослаблены.
- `ml_service/app/providers/ollama.py`: безопасный path/type feedback для единственного повторного inference, без ошибочного текста и скрытых рассуждений.
- `scripts/verify.py`: изолированный agent-only; `agent_redteam.py`, `generate_agent_redteam.py`, `summarize_agent_audit.py`: воспроизводимость, корпус и честные метрики.
- Новые `test_agent_redteam_*`, уточнённые fixture/oracle прежних analytics/live tests, machine JSON корпуса и этот набор документации. Миграций и правок frontend нет.

Контрактный export `contracts/assistant.schema.json` обновлён штатным --write-schema после изменения описания view. Ранние частные pytest-прогоны могли завершаться следующим красным architecture gate из-за устаревшего export; эти результаты не считаются целым успешным pipeline. Перед checkpoint schema/artifact check проходит, включая 31 неизменённый исходник аналитика и 1027 локальных ссылок.

Доказательства к этой точке: 619 distinct MCP/contract boundaries; 73 scope/P0/analytics regressions; 94 planning/API/CP-SAT; 98 solver/properties после lock fix; 12 сквозных typed workflows; 21 live-эпизод с Excel/изображениями и domain fingerprint, **21 passed / 228,98 с** (19 реально использовали inference). Эти наборы пересекаются, их нельзя складывать в число уникальных сценариев. Из более позднего кода точного поиска ещё выполняются проверки; общий frozen-source протокол будет приложен после окончания.

Пример успешной цепочки: запрос операций насоса → equipment_find по коду в текущем разрешённом объекте → фактический equipment_id → regulations_read → число published/draft, операции и периодичность. Пустой tasks_find не участвует в доказательстве отсутствия регламента. Пример изменения: запрос создания → equipment_create proposal → отсутствие записи до approval → точное подтверждение → succeeded → replay → одна строка equipment и одно confirmed audit event.

Существенные ограничения: не выполнено 300 свободных LLM-диалогов; 619 — транспортные границы. Проверен широкий, но не полный положительный набор всех 167 возможностей. 4B-модель может расширять объяснения сверх фактов, общее claim-by-claim качество не измерено. What-if отсутствий, multi-site solve, полный простой/смены, ресурс без норм/темпа и часть MVP отсутствуют или частичны. UI/mobile и полный фото-цикл исполнителя не переоценивались. Исторический SQL upgrade ENV-001 не закрыт и не замаскирован успешной свежей установкой.

Денежная стоимость/универсальная hallucination rate не объявлены нулём; методика и знаменатели находятся в [метриках](agent-quality-metrics.md). Критерии полного завершения директивы не считаются все выполненными по одному зелёному прогону. Этот документ — проверяемая передача текущего состояния, а не сертификат промышленной готовности.

Следующий срез после 32c08bf: завершены два frozen-live раунда по 1080 passed и широкий backend/ML 1957 passed/33 skipped/5 xfailed, source_stable=true. Независимый ручной пересмотр обнаружил AG-009 (quantity→норма) и AG-010 (digest-free hex36) даже при зелёном прежнем oracle. Они исправлены readiness/null/UUID-scope контролями; усиленная связанная регрессия — 63 passed, полный native pipeline. Дополнительные файлы: workbook_readiness.py, workbooks.py, service.py/read_transport.py, norm/privacy tests и обновлённый live oracle. Реальный расчёт по raw Excel теперь честно требует подготовленных исходных данных вместо выдуманной численности; обычный анализ и явный импорт не подменяются. Четыре старых forecast/schedule xfail изучаются отдельно; конфликт демо-политики не выдаётся за устранённый дефект.
