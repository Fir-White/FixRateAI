# ALG08: устойчивость

Команда: `.venv/Scripts/python.exe -B scripts/verify_orchestration.py`.

Проверены некорректный JSON, исключение провайдера, чужой snapshot, отсутствие модели и таймаут. Во всех случаях пригодный регламент остаётся доступен.

- model_missing: MODEL_NOT_READY, fallback, 1.06 мс.
- invalid_json: INVALID_AI_JSON, fallback, 1.52 мс.
- provider_exception: PROVIDER_ERROR, fallback, 1.44 мс.
- foreign_snapshot: AI_SNAPSHOT_MISMATCH, fallback, 1.56 мс.
- timeout: TIMEOUT, fallback, 20.36 мс.

Выполнение AI ограничено двумя daemon workers; истёкший запрос не сохраняет поздний ответ. Session БД в поток не передаётся. Повторы и транзакционные ошибки проверяются отдельно реальными HTTP/PostgreSQL-тестами и браузерным прогоном scripts/verify.py --browser.
