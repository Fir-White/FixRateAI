"""Run the SPA browser suite against an isolated API and disposable PostgreSQL.

Use verify.py --browser for the full SQL/backend/ML release check.
This focused runner checks the built SPA without changing the working database.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from scripts.verification_paths import log_reference, prepare_run
from scripts.verify import unused_port


def verification_app():
    from app.main import create_app

    return create_app(frontend_dist=Path(os.environ["FIXRATE_VERIFY_WEB_DIST"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--grep", help="Optional Playwright test name filter")
    parser.add_argument("--order-table", action="store_true", help="Enable the synthetic one-time order fixture and worksheet E2E")
    parser.add_argument("--documentation", action="store_true", help="Capture the release gallery on a new local test database")
    parser.add_argument("--documentation-local-ai", action="store_true",
                        help="Also capture grounded v4 replies using an already pinned local Ollama model")
    parser.add_argument("--documentation-video", action="store_true", help="Also record the two main role journeys")
    args = parser.parse_args()
    output, logs = prepare_run(args.output)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "backend"), str(ROOT)]), PYTHONUTF8="1")
    for key in ("DATABASE_URL", "TEST_DATABASE_URL", "INTEGRATION_DATABASE_URL", "VITE_DEMO_MODE"):
        env.pop(key, None)
    env["PHOTO_REVIEW_PROVIDER"] = "aitunnel"  # Without AITUNNEL_API_KEY, cloud photo review reports unavailable.
    env.pop("FIXRATE_ORDER_TABLE_E2E", None)
    env.pop("FIXRATE_DOCUMENTATION_CAPTURE", None)
    if args.documentation:
        if args.order_table:
            parser.error("Documentation and worksheet E2E mutate the same fixture; run them separately")
        env.update(FIXRATE_DOCUMENTATION_CAPTURE="1", FIXRATE_PERMISSION_PROFILE="mvp", ASSISTANT_PROVIDER="ollama",
                   FIXRATE_ACTIVE_ROLES="chief_engineer,engineer,executor", FIXRATE_ASSISTANT_AGENT_VERSION="v4",
                   FIXRATE_LLM_LOCAL_ONLY="1", FIXRATE_AGENT_LIVE="0", AITUNNEL_API_KEY="", AI_TUNNEL_API_KEY="",
                   MAINTENANCE_SCHEDULER="false", OPTIMIZATION_WORKER="false")
        args.grep = args.grep or "documentation gallery"
    env.pop("FIXRATE_DOCS_LOCAL_AI", None)
    env.pop("FIXRATE_DOCS_VIDEO", None)
    if args.documentation_local_ai:
        if not args.documentation or not env.get("OLLAMA_CHAT_DIGEST") or not env.get("OLLAMA_CHAT_MODEL"):
            parser.error("Local AI capture requires --documentation and a pinned OLLAMA_CHAT_MODEL / OLLAMA_CHAT_DIGEST")
        env.update(FIXRATE_DOCS_LOCAL_AI="1", OLLAMA_CHAT_BASE_URL="http://127.0.0.1:11434")
    if args.documentation_video:
        if not args.documentation:
            parser.error("Video capture requires --documentation")
        env["FIXRATE_DOCS_VIDEO"] = "1"
    if args.order_table:
        env.update(FIXRATE_ORDER_TABLE_E2E="1", FIXRATE_LLM_LOCAL_ONLY="1", FIXRATE_AGENT_LIVE="0",
                   AITUNNEL_API_KEY="", AI_TUNNEL_API_KEY="", MAINTENANCE_SCHEDULER="false", OPTIMIZATION_WORKER="false")
    scratch = Path(tempfile.mkdtemp(prefix="fixrate-web-"))
    cluster = scratch / "postgres"
    dist = scratch / "dist"
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    postgres_hidden = hidden
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        postgres_hidden = dict(creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup, stdin=subprocess.DEVNULL)
    api = postgres = None
    results = []

    def executable(name):
        return str(args.pg_bin / (name + (".exe" if os.name == "nt" else "")))

    def run(name, command, variables=env, cwd=ROOT):
        print(name, flush=True)
        log_path = logs / f"{name}.log"
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=cwd, env=variables, stdout=log, stderr=subprocess.STDOUT, **hidden)
        results.append(dict(check=name, exit_code=result.returncode, log=log_reference(output, log_path)))
        if result.returncode:
            print(log_path.read_text(encoding="utf-8")[-5000:], flush=True)
            raise RuntimeError(f"{name} failed; see {log_path}")

    try:
        run("frontend_build", [shutil.which("npm.cmd" if os.name == "nt" else "npm"), "run", "build", "--",
                              "--outDir", str(dist)], cwd=ROOT / "frontend")
        run("initdb", [executable("initdb"), "-D", str(cluster), "-U", "postgres", "-A", "trust", "--encoding=UTF8", "--locale=C"])
        pg_port = unused_port()
        with (logs / "postgres.log").open("w", encoding="utf-8") as pg_log, (logs / "api.log").open("w", encoding="utf-8") as api_log:
            postgres = subprocess.Popen([executable("postgres"), "-D", str(cluster), "-p", str(pg_port), "-h", "127.0.0.1"], stdout=pg_log, stderr=subprocess.STDOUT, **postgres_hidden)
            import psycopg
            for _ in range(100):
                try:
                    with psycopg.connect(host="127.0.0.1", port=pg_port, user="postgres", dbname="postgres", connect_timeout=1) as conn:
                        if Path(conn.execute("SHOW data_directory").fetchone()[0]).resolve() != cluster.resolve():
                            raise RuntimeError("PostgreSQL port belongs to another cluster; no database was created")
                        break
                except psycopg.OperationalError:
                    if postgres.poll() is not None:
                        raise RuntimeError("PostgreSQL failed to start")
                    time.sleep(0.2)
            else:
                raise RuntimeError("PostgreSQL readiness timeout")
            run("createdb", [executable("createdb"), "-h", "127.0.0.1", "-p", str(pg_port), "-U", "postgres", "fixrate_test_browser"])
            from app.db.session import make_engine
            from app.manage import migrate, seed_demo
            url = f"postgresql+psycopg://postgres@127.0.0.1:{pg_port}/fixrate_test_browser"
            engine = make_engine(url)
            password = "Web-Verification-" + os.urandom(16).hex()
            try:
                migrate(engine)
                seed_demo(engine, password)
                if args.documentation:
                    from tests.fixtures.catalog_source import catalog_book

                    workbook = scratch / "Учебный каталог СВиК.xlsx"
                    workbook.write_bytes(catalog_book(8))
                    env["FIXRATE_DOCS_CATALOG"] = str(workbook)
                if args.order_table or args.documentation:
                    from app.integration.demo import demo_id
                    from sqlalchemy import text

                    with engine.begin() as conn:
                        conn.execute(text("""UPDATE maintenance_rules SET schedule_parameters =
                            schedule_parameters || '{"methodology_ref":"TEST: учебный регламент"}'::jsonb
                            WHERE maintenance_rule_id=:id"""), dict(id=demo_id("assignment-rule")))
                        if args.documentation:
                            # Forecast input, from the already typed synthetic planning fixture.
                            conn.execute(text("""UPDATE equipment AS target SET equipment_type_id=source.equipment_type_id
                                FROM equipment AS source WHERE target.equipment_id=:target AND source.equipment_id=:source
                                AND target.site_id=source.site_id"""), dict(target=demo_id("assignment-equipment"),
                                source=demo_id("planning-equipment")))
            finally:
                engine.dispose()
            api_port = unused_port()
            api = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "scripts.verify_web:verification_app", "--factory",
                 "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT,
                env=dict(env, DATABASE_URL=url, PHOTO_STORAGE_ROOT=str(scratch / "photos"),
                         FIXRATE_VERIFY_WEB_DIST=str(dist)), stdout=api_log, stderr=subprocess.STDOUT, **hidden)
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{api_port}/api/health", timeout=1):
                        break
                except Exception:
                    if api.poll() is not None:
                        raise RuntimeError("API failed to start")
                    time.sleep(0.2)
            else:
                raise RuntimeError("API readiness timeout")
            command = [shutil.which("npm.cmd" if os.name == "nt" else "npm"), "run", "test:e2e", "--", "--output", str(output / "playwright")]
            if args.grep:
                command += ["--grep", args.grep]
            run("browser_e2e", command, dict(env, FIXRATE_BASE_URL=f"http://127.0.0.1:{api_port}", FIXRATE_TEST_PASSWORD=password, FIXRATE_E2E_OUTPUT=str(output)), ROOT / "frontend")
    finally:
        if api:
            api.terminate()
            api.wait(timeout=10)
        if postgres:
            subprocess.run([executable("pg_ctl"), "-D", str(cluster), "stop", "-m", "fast", "-w"], capture_output=True, **hidden)
            postgres.wait(timeout=10)
        assert scratch.resolve().parent == Path(tempfile.gettempdir()).resolve()
        assert scratch.name.startswith("fixrate-web-")
        shutil.rmtree(scratch)
        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Results: {output / 'results.json'}", flush=True)
        print(f"Logs: {logs}", flush=True)


if __name__ == "__main__":
    main()
