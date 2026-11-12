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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--grep", help="Optional Playwright test name filter")
    args = parser.parse_args()
    output, logs = prepare_run(args.output)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "backend"), str(ROOT)]), PYTHONUTF8="1")
    for key in ("DATABASE_URL", "TEST_DATABASE_URL", "INTEGRATION_DATABASE_URL", "VITE_DEMO_MODE"):
        env.pop(key, None)
    env["PHOTO_REVIEW_PROVIDER"] = "clip"  # Dedicated local-vision checks run separately.
    scratch = Path(tempfile.mkdtemp(prefix="fixrate-web-"))
    cluster = scratch / "postgres"
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
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
        run("frontend_build", [shutil.which("npm.cmd" if os.name == "nt" else "npm"), "run", "build"], cwd=ROOT / "frontend")
        run("initdb", [executable("initdb"), "-D", str(cluster), "-U", "postgres", "-A", "trust", "--encoding=UTF8", "--locale=C"])
        pg_port = unused_port()
        with (logs / "postgres.log").open("w", encoding="utf-8") as pg_log, (logs / "api.log").open("w", encoding="utf-8") as api_log:
            postgres = subprocess.Popen([executable("postgres"), "-D", str(cluster), "-p", str(pg_port), "-h", "127.0.0.1"], stdout=pg_log, stderr=subprocess.STDOUT, **hidden)
            import psycopg
            for _ in range(100):
                try:
                    with psycopg.connect(host="127.0.0.1", port=pg_port, user="postgres", dbname="postgres", connect_timeout=1):
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
            finally:
                engine.dispose()
            api_port = unused_port()
            api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=dict(env, DATABASE_URL=url, PHOTO_STORAGE_ROOT=str(scratch / "photos")), stdout=api_log, stderr=subprocess.STDOUT, **hidden)
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
