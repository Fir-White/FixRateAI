"""Reproducible verification in a new loopback-only, disposable PostgreSQL cluster.

No project DATABASE_URL is read or modified. Requires installed PostgreSQL binaries.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, default=Path("C:/Program Files/PostgreSQL/16/bin") if os.name == "nt" else Path("/usr/lib/postgresql/16/bin"))
    parser.add_argument("--output", type=Path, default=ROOT / "var/verification")
    parser.add_argument("--browser", action="store_true", help="Also run built-SPA browser tests")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "backend"), str(ROOT)]), PYTHONUTF8="1")
    # Test destinations are created here, never accepted from the calling shell.
    env.pop("DATABASE_URL", None)
    env.pop("TEST_DATABASE_URL", None)
    env.pop("INTEGRATION_DATABASE_URL", None)
    env.pop("VITE_DEMO_MODE", None)
    pg_port = unused_port()
    scratch = Path(tempfile.mkdtemp(prefix="fixrate-verify-"))
    pg_data = scratch / "postgres"
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    server = api = None
    pg_log = api_log = None

    def exe(name):
        return str(args.pg_bin / (name + (".exe" if os.name == "nt" else "")))

    def run(name, command, *, cwd=ROOT, variables=None):
        print(name, flush=True)
        start = time.monotonic()
        with (output / f"{name}.log").open("w", encoding="utf-8") as log:
            done = subprocess.run(command, cwd=cwd, env=variables or env, stdout=log, stderr=subprocess.STDOUT,
                                  encoding="utf-8", **hidden)
        results.append(dict(check=name, command=subprocess.list2cmdline([str(x) for x in command]),
                            status="Пройдено" if done.returncode == 0 else "Ошибка", exit_code=done.returncode,
                            seconds=round(time.monotonic()-start, 2), log=f"{name}.log"))
        if done.returncode:
            print((output / f"{name}.log").read_text(encoding="utf-8")[-15000:])
            raise RuntimeError(f"{name} failed")

    def sql(db, file, name):
        run(name, [exe("psql"), "-X", "-h", "127.0.0.1", "-p", str(pg_port), "-U", "postgres", "-d", db,
                   "-v", "ON_ERROR_STOP=1", "-f", str(file)])

    def create_db(name):
        subprocess.run([exe("createdb"), "-h", "127.0.0.1", "-p", str(pg_port), "-U", "postgres", name], check=True, **hidden)
        return f"postgresql+psycopg://postgres@127.0.0.1:{pg_port}/{name}"

    try:
        run("initdb", [exe("initdb"), "-D", str(pg_data), "-U", "postgres", "-A", "trust", "--encoding=UTF8", "--locale=C"])
        pg_log = (output / "postgres.log").open("w", encoding="utf-8")
        server = subprocess.Popen([exe("postgres"), "-D", str(pg_data), "-p", str(pg_port), "-h", "127.0.0.1"],
                                  stdout=pg_log, stderr=subprocess.STDOUT, **hidden)
        import psycopg
        for attempt in range(100):
            try:
                with psycopg.connect(host="127.0.0.1", port=pg_port, user="postgres", dbname="postgres", connect_timeout=1) as conn:
                    pg_version = conn.execute("SELECT version()").fetchone()[0]
                break
            except psycopg.OperationalError:
                if server.poll() is not None:
                    raise RuntimeError("Temporary PostgreSQL exited")
                time.sleep(0.2)
        else:
            raise RuntimeError("Temporary PostgreSQL did not start")
        print(pg_version, flush=True)
        orm_url = create_db("fixrate_test_orm")
        runtime_url = create_db("fixrate_test_runtime")
        upgrade_url = create_db("fixrate_test_upgrade")
        # Upgrade a populated 001–004 database; every imported SQL assertion remains intact.
        for file in sorted((ROOT / "database/migrations").glob("00[1-4]*.sql")):
            sql("fixrate_test_upgrade", file, "upgrade_" + file.stem)
        for file in sorted((ROOT / "database/tests").glob("00[1-4]*.sql")):
            sql("fixrate_test_upgrade", file, "sql_" + file.stem)
        sql("fixrate_test_upgrade", ROOT / "database/qa/test_maintenance_schema.sql", "sql_qa_schema")
        sql("fixrate_test_upgrade", ROOT / "database/seeds/001_customer_schedule_demo.sql", "seed_source")
        sql("fixrate_test_upgrade", ROOT / "database/seeds/001_customer_schedule_demo.sql", "seed_source_rerun")
        sql("fixrate_test_upgrade", ROOT / "database/tests/005_demo_seed.sql", "sql_demo_seed")
        from app.manage import migrate, seed_demo
        from app.db.session import make_engine
        engine = make_engine(upgrade_url)
        import hashlib
        with engine.connect() as conn:
            raw = conn.connection.driver_connection
            before = raw.execute("SELECT md5(string_agg(to_jsonb(w)::text,',' ORDER BY work_order_id)) FROM work_orders w").fetchone()[0]
        migrate(engine, adopt_existing=True)
        migrate(engine)
        with engine.connect() as conn:
            # Added revision is the only intended work-order shape change.
            raw = conn.connection.driver_connection
            after = raw.execute("SELECT md5(string_agg((to_jsonb(w)-'revision')::text,',' ORDER BY work_order_id)) FROM work_orders w").fetchone()[0]
            assert before == after, "Upgrade changed existing work history"
        engine.dispose()
        results.append(dict(check="upgrade_004_to_005_and_idempotence", command="app.manage.migrate(adopt_existing=True); migrate(); compare persisted history", status="Пройдено"))
        # Independent fresh installation, then seed twice without resetting history or passwords.
        engine = make_engine(runtime_url)
        migrate(engine)
        password = "Verification-" + os.urandom(12).hex()
        seed_demo(engine, password)
        seed_demo(engine, password)
        engine.dispose()
        results.append(dict(check="fresh_001_to_005_and_seed_rerun", command="app.manage.migrate(); seed_demo(); seed_demo()", status="Пройдено"))
        test_env = dict(env, TEST_DATABASE_URL=orm_url, INTEGRATION_DATABASE_URL=runtime_url, FIXRATE_TEST_PASSWORD=password,
                        PHOTO_STORAGE_ROOT=str(scratch / "photos"))
        run("pytest", [sys.executable, "-B", "-m", "pytest", "-q"], variables=test_env)
        run("architecture", [sys.executable, "-B", "docs/architecture/validate_artifacts.py"])
        run("compileall", [sys.executable, "-m", "compileall", "-q", "backend/app", "ml_service"])
        run("pip_check", [sys.executable, "-m", "pip", "check"])
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        run("frontend_build", [npm, "run", "build"], cwd=ROOT / "frontend")
        run("frontend_tests", [npm, "test"], cwd=ROOT / "frontend")
        run("frontend_audit", [npm, "audit", "--audit-level=moderate"], cwd=ROOT / "frontend")
        if args.browser:
            browser_url = create_db("fixrate_test_browser")
            engine = make_engine(browser_url)
            migrate(engine)
            seed_demo(engine, password)
            engine.dispose()
            api_port = unused_port()
            api_env = dict(env, DATABASE_URL=browser_url, PHOTO_STORAGE_ROOT=str(scratch / "browser-photos"))
            api_log = (output / "api.log").open("w", encoding="utf-8")
            api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
                                    "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env,
                                   stdout=api_log, stderr=subprocess.STDOUT, **hidden)
            for attempt in range(100):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{api_port}/api/health", timeout=1).close()
                    break
                except Exception:
                    if api.poll() is not None:
                        raise RuntimeError("API did not start; see api.log")
                    time.sleep(0.2)
            else:
                raise RuntimeError("API readiness timeout")
            run("browser_e2e", [npm, "run", "test:e2e"], cwd=ROOT / "frontend", variables=dict(env,
                FIXRATE_BASE_URL=f"http://127.0.0.1:{api_port}", FIXRATE_TEST_PASSWORD=password,
                FIXRATE_E2E_OUTPUT=str(output)))
    except Exception as exc:
        if not results or results[-1].get("status") != "Ошибка":
            results.append(dict(check="verification_runner", status="Ошибка", error=str(exc)))
        raise
    finally:
        if api:
            api.terminate()
            api.wait(timeout=10)
        if api_log:
            api_log.close()
        if server:
            subprocess.run([exe("pg_ctl"), "-D", str(pg_data), "stop", "-m", "fast", "-w"], capture_output=True, **hidden)
            server.wait(timeout=10)
        if pg_log:
            pg_log.close()
        # Verify the exact generated absolute target before recursive cleanup.
        assert scratch.resolve().parent == Path(tempfile.gettempdir()).resolve()
        assert scratch.name.startswith("fixrate-verify-")
        shutil.rmtree(scratch)
        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(f"Results: {output / 'results.json'}", flush=True)


if __name__ == "__main__":
    main()
