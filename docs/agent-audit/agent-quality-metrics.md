# Метрики качества агента

## Уточнение C4: неустойчивость предыдущего среза

Второй frozen 75a1fa9: **1 failed/1157 passed, 835,95 с**, тот же source hash/source_stable=true. Task-oracle 23/24, 21 эпизод с inference; p50 9,2615 с, p95 31,212 с, max 38,187 с. Это красный повтор, а не «оба раунда прошли». Артефакт metrics-2.json сохранён рядом с metrics-1.json.

Разработческий C4-срез (не frozen): все **24/24 live** прошли, включая настоящие два vision-вызова и сохранность остальных полей SQL-строк в трёх mutations. В pytest **1 failed/127 passed**: старый oracle ожидал общий текст «не хватает сведений», а ответ теперь явно называл недоступный backend и отсутствие доказательства пустого реестра. Oracle уточнён по смыслу 503; это не новый продуктовый дефект. p50 8,5995 с, p95 29,623 с, max 30,379 с относятся только к этому разработческому составу. Дополнительные 74 parser/renderer/grammar tests прошли отдельно. К следующему source checkpoint будет приложен полный стабильный прогон; частный результат не подменяет его.

## Окончательный код 75a1fa9 — первый замороженный раунд

Source SHA-256 `71b335da775e5eaa438aa04ca14ebe235f735df8805702e33f8020784be9b8e4`, source_stable=true. Полный backend/ML: **2036 passed, 36 skipped, 1 xfailed / 780,36 с**, весь native pipeline. Агентный round 1 с локальной моделью: **1158 passed / 739,11 с**, весь pipeline; round 2 измеряется отдельно, его результат не подразумевается из первого.

Из 24 эпизодов 21 сделал настоящую inference (62 запроса модели). Task-oracle 24/24, tool success 29/31, неожиданные proposals 0/24, cross-turn 2/2, подтверждение+replay 4/4; среднее 1,292 логического вызова. p50 9,432 с, p95 23,781 с, max 44,425 с. Токены 392111/5756. Денежная стоимость и полные claim-by-claim/unauthorized-execution/constraint rates остаются null, а не искусственным 0 или 100%. Семантика task-oracle не расширена: отдельные опорные факты проверены вручную/SQL, но не каждое высказывание модели.

Артефакты: reports/agent-audit-frozen-75a1fa9/metrics-1.json и round-1/agent-audit. Прогоны полного backend и первого round частично шли одновременно в разных PostgreSQL; эти задержки не изолированный сравнительный performance benchmark. Положительные новые операции покрывают rename/staff-role/component; числа 619 MCP и 24 эпизода не суммируются в LLM-объём.

Все значения — для синтетических одноразовых БД и pinned `qwen3.5:4b-q4_K_M`, digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`. Успех теста означает прохождение его oracle, а не отсутствие всех возможных галлюцинаций.

| Прогон | Результат | Что считать |
|---|---:|---|
| offline-baseline | 112 passed / 53,95 с | Прежняя серверная регрессия, не число LLM-диалогов |
| controls-repro → controls-after | 1 failed/18 passed → 57 passed | AG-001 и смежная регрессия |
| provenance-before → evidence-after | 10 failed → 654 passed | 10 faults + 25 прежних analytics + 619 matrix |
| scope-before → scope-final | 10 failed/1 passed → 73 passed | AG-003 плюс прежние P0/analytics/contracts |
| planning-baseline | 94 passed / 109,94 с | Реальные PostgreSQL/CP-SAT/API |
| production-run | 12 passed / 31,25 с | Сквозные typed workflows с включённым local provider; не 12 свободных LLM-планирований |
| lock-order-before → lock-order-final | 6 failed → 98 passed | 90 свойства/locks + 8 core solver; фикс AG-006 |
| live-baseline | 4/7 passed | 2 продуктовых сбоя чтения, 1 ошибочный oracle раннего guard |
| live-json-repair | 7/7 passed / 105,53 с | 6/7 эпизодов действительно вызвали модель, 22 inference requests |
| live-expanded | 15/15 passed / 248,89 с | 14/15 эпизодов с inference, 66 модельных вызовов, 1 ранний guard |

Не суммируйте эти строки как уникальные случаи: часть наборов повторяется и входит друг в друга. Корпус границ MCP — 619 уникальных случаев, свободных live-эпизодов в последней расширенной выборке — 15. До/после для общих семи случаев сравнимы, расширение на восемь — holdout, не доказательство улучшения на той же выборке.

Live-baseline: p50 **13,458 с**, p95/max **34,493 с**, 136 412 prompt tokens / 3 368 output tokens. Live-json-repair: p50 **12,085 с**, p95/max **29,083 с**, 141 316 / 2 711 tokens. Live-expanded: p50 **14,955 с**, p95/max **42,464 с**, 429 382 / 6 342 tokens. При 15 образцах p95 совпадает с максимумом; статистическая неопределённость велика, это не production SLA. Длинный контекст и несколько inference на запрос остаются причиной задержек.

Денежная стоимость — **не измерена**, не 0: provider локальный, но энергозатраты/износ/занятость GPU не оценены. Не утверждается безгаллюцинаторность 4B. Повторы запросов, токены и границы parser считаются отдельно от бизнес-успеха. Отрицательный role guard не делает inference зря и считается корректной серверной защитой.

Общий runner `agent-audit-integrated` проверяет объединённый срез; его итог и позднейшие ограничения фиксируются отдельно после окончания. Частичные ранние прогоны не выдаются за итоговую release-регрессию.

Поздний `agent-audit-live-files`: **21/21 passed**, 19/21 с inference, 57 модельных запросов. p50 **8,728 с**, p95 **18,573 с**, max **31,956 с**, 342 259 prompt / 4 560 completion tokens. На этой выборке task oracle=21/21, логические tool calls completed/proposed=23/26 (88,46%), GET recovery=1/1, неожиданные proposals=0/21, cross-turn=2/2, create+replay=1/1; в среднем 1,238 логического вызова на эпизод. Сокращение времени не считается изолированным causal benchmark: изменились состав, typed paths и состояние кеша модели.

Машинный расчёт: `scripts/summarize_agent_audit.py <каталог live JSON>`. Grounded Answer Rate и Hallucination Rate **не измерены целиком**: проверены опорные факты и неизменность домена, но не независимая разметка каждого утверждения. Unauthorized Execution Rate/Constraint Violation Rate для всей совокупности также не выводятся из 21 ответов — их отрицательные границы и отдельные solver-оракулы описаны в других наборах. Неизмеренное значение null, а не 0/100%.

Существенная корректировка интерпретации: ручная проверка нашла выдуманные 2 чел·ч при пустом B2/quantity=2 в старом live-эпизоде, прошедшем слабый oracle. Поэтому старые 21/21 — только pytest outcome, **не 21/21 grounded answers**. После AG-009 проверяется именно отсутствие подтверждённого норматива и невозможность кадрового расчёта; сценарий обязан назвать B2, а не просто содержать слова о недостатке данных. Frozen 32c08bf дал 1080/1080 дважды с устойчивым source hash; это не отменяет ручной находки. Широкий C1: 1957 passed/33 skipped/5 xfailed. Срез C2: 63 связанных проверки passed; его полный генеративный и широкий результат ещё предстоит измерить.

## C5, frozen fe39fb7, round 1

Первый повторяемый live-only раунд: **41 passed / 595,70 с**, весь native pipeline exit0, source_stable=true, SHA-256 08923e354fd41ec2b51f18e39d32314afeca8cb23bedcf69dc40a05a25a0c5aa. Это 29 chat episodes + 12 typed production workflows. Из 29 эпизодов 26 действительно вызвали модель; 80 inference requests. Task-oracle **29/29**, logical tool success **51/55**, unexpected proposal **0/29**, cross-turn **2/2**, actual confirm/replay **9/9**. У всех восьми mutation эпизодов unrequested_fields_preserved=true. GET repairs в этой выборке отсутствуют: denominator=0, rate=null (не 100%). Среднее логических calls 55/29=1,8966.

Latency по 29 полным эпизодам: p50 11,416 с, p95 47,446 с, max 107,717 с. Токены 612705 prompt / 9924 completion. Сюда входят routing/повторы/несколько turns внутри эпизода, это не TTFT одного ответа. Широкая регрессия идёт параллельно в другой БД, поэтому это не изолированный speed benchmark. Денежная стоимость и универсальные grounded/hallucination/unauthorized-execution/constraint rates остаются null. Ручная проверка выявила OBS-001 (широкое «в системе» после current-object чтения), поэтому 29/29 не интерпретируется как 29 безошибочных ответов. Машинный результат: reports/agent-audit-frozen-fe39fb7-live/metrics-1.json; второй раунд публикуется после завершения, не подставляется заранее.
## C5 — широкая frozen регрессия fe39fb7

Весь tests/backend + tests/ml: **2189 passed / 41 skipped / 1 xfailed / 972,35 с**, весь выбранный native pipeline exit0. Все 41 skips — opt-in live/production cases, проверяемые отдельно; strict xfail — описанный BUG05/ENV-003. Source hash до/после совпал: 08923e354fd41ec2b51f18e39d32314afeca8cb23bedcf69dc40a05a25a0c5aa, HEAD fe39fb766e40d0def6793dd5de388990ce0b6acc. Артефакты reports/agent-audit-frozen-fe39fb7-full и -provenance.json, pytest log logs/agent-audit-frozen-fe39fb7-full/pytest.log. Не засчитываются legacy upgrade SQL, frontend/mobile или Docker; --agent-only ограничивает ровно эти выбранные стадии, не скрывает этот scope.
Второй общий C5 round прерван без terminal pytest/pipeline result: сохранены 26 passed episode JSON из 29, 0 зафиксированных failed, но это не полный успех. Универсальные/latency rates для неполного цензурированного раунда не вычисляются. Source всё ещё совпадает; подробный interruption record сохранён. Три оставшиеся mutation + 12 production проверяются отдельно; их результат не превращается задним числом в «41 passed» прерванного pytest процесса.
## C5 — завершённое дополнение после прерывания

Оставшиеся LIVE-M06/M07/M08 и 12 typed production workflows выполнены отдельно на новой БД: **15 passed / 241,94 с**, весь native pipeline exit0, source_stable=true, тот же source SHA-256 08923e354fd41ec2b51f18e39d32314afeca8cb23bedcf69dc40a05a25a0c5aa и HEAD fe39fb7. Артефакты reports/agent-audit-fe39fb7-supplement, -source.json, -provenance.json и supplement-production. Все 29 episode IDs повторно дали успешные бизнес-oracle в записанных частях, но прерванный pytest не превращается в цельный «41 passed» и не скрывает отсутствие его teardown/pipeline результата. Сравнимые исходные полные доказательства: backend/ML 2189 passed/41 opt-in skipped/1 strict xfailed и первый live-only 41 passed.

После выдачи local preview наблюдался отдельный OLLAMA_TIMEOUT на длинном пользовательском диалоге при параллельной нагрузке. Backend чтения выполнялись; это не ошибка PostgreSQL или доказательство отсутствия данных. Ограничение локальной 4B модели/общего deadline не объявлено исправленным увеличением timeout либо успешным inventory примером. Фоновые модельные проверки завершены; SLA и универсальная точность свободных ответов не подтверждены.