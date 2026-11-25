"""Build a local portable application image with the pinned RF model, without credentials."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    docker = shutil.which("docker")
    if not docker and os.name == "nt":
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe"
        if candidate.is_file():
            docker = str(candidate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default=docker or "docker")
    parser.add_argument("--tag", default="fixrate-ai:bundled")
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    state = ROOT / "var/bundled-image" / run_id
    logs = ROOT / "logs/bundled-image" / run_id
    report = ROOT / "reports/bundled-image" / run_id
    logs.mkdir(parents=True)
    report.mkdir(parents=True)
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    def command(label, *parts):
        print(label, flush=True)
        done = subprocess.run(list(parts), cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", **hidden)
        (logs / (label + ".log")).write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
        if done.returncode:
            raise RuntimeError(label + " failed; see " + str(logs))
        return done.stdout.strip()
    commit = command("git_revision", "git", "rev-parse", "HEAD")
    dirty = bool(command("git_status", "git", "status", "--porcelain=v1"))
    revision = commit + ("-dirty" if dirty else "")
    base_tag = "fixrate-ai:runtime-" + commit[:12] + "-" + run_id.rsplit("-", 1)[1]
    command("base_build", args.docker, "build", "--build-arg", "SOURCE_REVISION=" + revision,
            "--tag", base_tag, ".")
    command("bundled_build", args.docker, "build", "--file", "Dockerfile.bundled",
            "--build-arg", "BASE_IMAGE=" + base_tag,
            "--tag", args.tag, ".")
    image_id = command("image_id", args.docker, "image", "inspect", args.tag, "--format", "{{.Id}}")
    readiness = command("offline_models", args.docker, "run", "--rm", "--network", "none",
        args.tag, "python", "-c",
        "import json; from ml_service.app.forecast.runtime import load_verified_forecaster; "
        "rf=load_verified_forecaster(); "
        "assert rf.is_fitted; "
        "print(json.dumps(dict(rf='synthetic_demo:rf:'+rf.artifact_sha256[:16])))")
    models = json.loads(readiness)
    result = {"image": args.tag, "image_id": image_id, "source_revision": revision,
              "base_image": base_tag, "models": models, "cache_bundled": False,
              "offline_model_check": "passed", "logs": str(logs), "run_id": run_id}
    state.mkdir(parents=True, exist_ok=True)
    (state / "image.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (report / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
