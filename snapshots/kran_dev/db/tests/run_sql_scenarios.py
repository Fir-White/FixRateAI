"""Run the 50 SQL-only scenarios from docs/database/test_scenarios.md.

Prerequisites:
  * A fresh database with db/001_init.sql applied.
  * Either a running PostgreSQL with psql in PATH, or a Docker container
    with psql (set FIXRATE_PG_CONTAINER).

Each scenario runs in its own transaction and ends with ROLLBACK, so the
target database is not modified.

Examples:
  # Docker (container with the test database)
  FIXRATE_PG_CONTAINER=fixrate_pg_test python db/tests/run_sql_scenarios.py

  # Direct psql (PGHOST/PGPORT/PGUSER/PGPASSWORD are read by psql)
  PGHOST=localhost PGPORT=5433 PGUSER=fixrate \
    PGDATABASE=fixrate_scenarios python db/tests/run_sql_scenarios.py
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scenario_defs import COMMON, TESTS, V

CONTAINER = os.environ.get("FIXRATE_PG_CONTAINER")
DB = os.environ.get("FIXRATE_DB", "fixrate_scenarios")
USER = os.environ.get("PGUSER", "fixrate")


def render(text: str) -> str:
    return re.sub(r"@([A-Z0-9]+)@", lambda m: V[m.group(1)], text)


def build_sql(tc: str, body: str) -> str:
    return (
        "BEGIN;\n"
        "DO $test$\n"
        "DECLARE\n"
        "  v_count INT;\n"
        "  v_text TEXT;\n"
        f"  v_hash TEXT := '{V['HASH']}';\n"
        "BEGIN\n"
        f"{render(COMMON)}\n"
        f"{render(body)}\n"
        f"  RAISE NOTICE 'PASS {tc}';\n"
        "END;\n"
        "$test$;\n"
        "ROLLBACK;\n"
    )


def psql_command(sql: str) -> list[str]:
    if CONTAINER:
        return [
            "docker", "exec", CONTAINER,
            "psql", "-X", "-v", "ON_ERROR_STOP=1",
            "-U", USER, "-d", DB, "-c", sql,
        ]
    return ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", DB, "-c", sql]


def main() -> int:
    results = []
    for tc, body in TESTS:
        sql = build_sql(tc, body)
        proc = subprocess.run(
            psql_command(sql),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        passed = proc.returncode == 0 and f"PASS {tc}" in output
        results.append({
            "tc": tc,
            "status": "PASS" if passed else "FAIL",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        })
        print(f"{tc}: {'PASS' if passed else 'FAIL'}", flush=True)
        if not passed:
            print(output.strip()[:2000], flush=True)

    out = Path(os.environ.get(
        "FIXRATE_RESULTS",
        Path(__file__).with_name("scenario_results.json"),
    ))
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\nSUMMARY: {passed}/{len(results)} PASS")
    print(f"Results: {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
