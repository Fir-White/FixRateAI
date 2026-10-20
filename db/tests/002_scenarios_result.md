# SQL-сценарии матрицы: результат прогона

**Дата:** 20.10.2026<br>
**Окружение:** PostgreSQL 16.15 + pgvector 0.8.7, контейнер `fixrate_pg_test`, БД `fixrate_scenarios`, DDL v3.1 (`db/001_init.sql`).<br>
**Команда:** `FIXRATE_PG_CONTAINER=fixrate_pg_test python db/tests/run_sql_scenarios.py`<br>
**Итог:** **50/50 PASS**. Каждый сценарий выполнен в отдельной транзакции с `ROLLBACK`; после прогона `users`, `repair_requests` и `estimates` содержат 0 строк.

| TC | Результат |
|---|---|
| TC-001 | PASS |
| TC-002 | PASS |
| TC-004 | PASS |
| TC-005 | PASS |
| TC-007 | PASS |
| TC-009 | PASS |
| TC-010 | PASS |
| TC-011 | PASS |
| TC-012 | PASS |
| TC-013 | PASS |
| TC-014 | PASS |
| TC-016 | PASS |
| TC-021 | PASS |
| TC-022 | PASS |
| TC-023 | PASS |
| TC-024 | PASS |
| TC-025 | PASS |
| TC-026 | PASS |
| TC-027 | PASS |
| TC-031 | PASS |
| TC-032 | PASS |
| TC-033 | PASS |
| TC-034 | PASS |
| TC-038 | PASS |
| TC-040 | PASS |
| TC-041 | PASS |
| TC-046 | PASS |
| TC-047 | PASS |
| TC-049 | PASS |
| TC-056 | PASS |
| TC-057 | PASS |
| TC-058 | PASS |
| TC-059 | PASS |
| TC-060 | PASS |
| TC-065 | PASS |
| TC-066 | PASS |
| TC-067 | PASS |
| TC-068 | PASS |
| TC-069 | PASS |
| TC-071 | PASS |
| TC-072 | PASS |
| TC-073 | PASS |
| TC-076 | PASS |
| TC-080 | PASS |
| TC-087 | PASS |
| TC-088 | PASS |
| TC-090 | PASS |
| TC-091 | PASS |
| TC-094 | PASS |
| TC-095 | PASS |

**Ограничение:** это только 50 SQL-сценариев. 13 сценариев `SQL+APP` и 34 сценария `APP`/`APP+INFRA` требуют backend, API, файлового хранилища или ML-пайплайна и в этот прогон не входят.

Воспроизведение: подготовьте чистую БД, примените `db/001_init.sql` и запустите `db/tests/run_sql_scenarios.py` (см. `db/README.md`). Файл `scenario_results.json` генерируется runner-ом и не хранится в git.
