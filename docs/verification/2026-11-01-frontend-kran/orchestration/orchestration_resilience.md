# ALG08: устойчивость

Команда: `.venv/Scripts/python.exe -B scripts/verify_orchestration.py`.

Проверены некорректный JSON, исключение провайдера, чужой snapshot, отсутствие модели и таймаут. Во всех случаях пригодный регламент остаётся доступен.

- model_missing: MODEL_NOT_READY, fallback, 2.82 мс.
- invalid_json: INVALID_AI_JSON, fallback, 2.59 мс.
- provider_exception: PROVIDER_ERROR, fallback, 2.24 мс.
- foreign_snapshot: AI_SNAPSHOT_MISMATCH, fallback, 2.84 мс.
- timeout: TIMEOUT, fallback, 26.29 мс.

Выполнение AI ограничено двумя daemon workers; истёкший запрос не сохраняет поздний ответ. Session БД в поток не передаётся. Повторы и транзакционные ошибки проверяются отдельно реальными HTTP/PostgreSQL-тестами и браузерным прогоном scripts/verify.py --browser.
