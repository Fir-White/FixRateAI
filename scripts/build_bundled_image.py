"""Build a local portable application image with the pinned CLIP files, without credentials."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MODEL_FILES = (
    "config.json", "preprocessor_config.json", "tokenizer_config.json",
    "tokenizer.json", "special_tokens_map.json", "vocab.json",
    "merges.txt", "pytorch_model.bin",
)


def model_pin():
    tree = ast.parse((ROOT / "ml_service/app/core/config.py").read_text(encoding="utf-8"))
    config = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MLConfig")
    defaults = {n.target.id: ast.literal_eval(n.value) for n in config.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                and n.target.id in {"clip_model_name", "clip_revision"}}
    return defaults["clip_model_name"], defaults["clip_revision"]


def export_pinned_cache(cache: Path, output: Path, model: str, revision: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", model):
        raise ValueError("Invalid model repository")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("A pinned model commit is required")
    folder = "models--" + model.replace("/", "--")
    candidates = [cache / "hub" / folder, cache / folder]
    model_root = next((p.resolve() for p in candidates
                       if (p / "snapshots" / revision).is_dir()), None)
    if model_root is None:
        raise ValueError("Pinned CLIP snapshot is missing; prepare it before building")
    if output.exists():
        raise ValueError("Model export must use a new directory")
    sources = {}
    for name in MODEL_FILES:
        source = (model_root / "snapshots" / revision / name).resolve()
        if not source.is_relative_to(model_root) or not source.is_file():
            raise ValueError("Missing or unsafe model file: " + name)
        sources[name] = source
    target = output / "hub" / folder / "snapshots" / revision
    target.mkdir(parents=True)
    manifest = {"model_ref": model + "@" + revision, "files": {}}
    for name, source in sources.items():
        dest = target / name
        shutil.copyfile(source, dest)
        with dest.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest["files"][name] = {"bytes": dest.stat().st_size, "sha256": digest}
    refs = target.parent.parent / "refs"
    refs.mkdir()
    (refs / "main").write_text(revision, encoding="utf-8")
    (output / "bundle-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    docker = shutil.which("docker")
    if not docker and os.name == "nt":
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe"
        if candidate.is_file():
            docker = str(candidate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default=docker or "docker")
    parser.add_argument("--cache", type=Path, default=ROOT / ".venv/hf-cache")
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
    model, model_revision = model_pin()
    manifest = export_pinned_cache(args.cache.resolve(), state / "model-cache", model, model_revision)
    base_tag = "fixrate-ai:runtime-" + commit[:12] + "-" + run_id.rsplit("-", 1)[1]
    command("base_build", args.docker, "build", "--build-arg", "SOURCE_REVISION=" + revision,
            "--tag", base_tag, ".")
    command("bundled_build", args.docker, "build", "--file", "Dockerfile.bundled",
            "--build-arg", "BASE_IMAGE=" + base_tag,
            "--build-context", "clip_weights=" + str(state / "model-cache"),
            "--tag", args.tag, ".")
    image_id = command("image_id", args.docker, "image", "inspect", args.tag, "--format", "{{.Id}}")
    readiness = command("offline_models", args.docker, "run", "--rm", "--network", "none",
        args.tag, "python", "-c",
        "import json; from ml_service.app.forecast.runtime import load_verified_forecaster; "
        "from ml_service.app.cv.classifier import CLIPZeroShotClassifier; "
        "rf=load_verified_forecaster(); cv=CLIPZeroShotClassifier(); "
        "assert rf.is_fitted and cv.is_torch_active and cv.warmup(); "
        "print(json.dumps(dict(rf='synthetic_demo:rf:'+rf.artifact_sha256[:16],clip=cv.model_ref)))")
    models = json.loads(readiness)
    assert models["clip"] == manifest["model_ref"]
    result = {"image": args.tag, "image_id": image_id, "source_revision": revision,
              "base_image": base_tag, "models": models, "cache_bundled": True,
              "offline_model_check": "passed", "logs": str(logs), "run_id": run_id}
    (state / "image.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (report / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
