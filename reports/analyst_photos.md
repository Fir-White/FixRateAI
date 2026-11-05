# AN06: фактический облачный фотоанализ

Прогон `20261105T175820Z`, модель AI Tunnel / Qwen3.7 Flash, prompt `maintenance-aitunnel-vision-v3`.

Исходные изображения/manifest аналитика сохранены неизменными. Проверенная политика — `docs/analysis/photo_review_policy.json`. CASE-01 описан в источнике как один прибор, но фактически содержит разные манометры; ожидание approved не принимается за корректный эталон. MATCH/DIFF остаются видимыми.

| Кейс | Ожидание источника | Факт | Совпадение с источником | Проверенная политика |
|---|---|---|---|---|
| CASE-01 | approved | rejected | DIFF | PASS |
| CASE-02 | manual_review | rejected | DIFF | PASS |
| CASE-03 | manual_review | manual_review | MATCH | PASS |
| CASE-04 | manual_review | manual_review | MATCH | PASS |
| CASE-05 | manual_review | manual_review | MATCH | PASS |
| CASE-06 | manual_review | manual_review | MATCH | PASS |
| CASE-NEG-01 | rejected | rejected | MATCH | PASS |
| CASE-NEG-02 | rejected | rejected | MATCH | PASS |
| CASE-NEG-03 | rejected | rejected | MATCH | PASS |

Итого: 9 PASS, 0 FAIL, 0 SKIP. Это пригодность визуальных доказательств, не подтверждение скрытых работ, безопасности или качества реального ТО. Нет метрик точности на заказчике. Полный E2E исходных шести операций BLOCKED до утверждения нормативов.

Предыдущие реальные прогоны не скрыты: `20261105T174903Z` — 2 PASS/1 SKIP; `20261105T175310Z` — 8 PASS/1 SKIP. Диагностика выявила пропуски/неверные имена полей. После исправления единая системная инструкция содержит схему; один ограниченный повтор возвращает только заново валидированный ответ, при повторном отказе остаётся контролируемая ошибка.

Воспроизведение: `python -B scripts/verify_analyst_photos.py --cloud`. Нужен приватный API-ключ в .env; команда платная и передаёт фото провайдеру. Результаты — reports/analyst-photos/<UTC-run>. Код 0 — все выбранные кейсы PASS, 1 — FAIL, 2 — облачный SKIP.
