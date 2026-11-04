"""Explicit one-time download of a pinned local vision model; no user photos are sent."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VOLUME = "fixrate-local_vision_models"
BOOTSTRAP = "fixrate-vision-bootstrap"


def main():
    docker = shutil.which("docker")
    if not docker and os.name == "nt":
        docker = str(Path(os.environ.get("LOCALAPPDATA", ""))/"Programs/DockerDesktop/resources/bin/docker.exe")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default=docker or "docker")
    parser.add_argument("--image", default="ollama/ollama:0.40.14@sha256:ebaef4f4c5d93660e1f25f8ad085a112f51ccfb0e8458073e71793959dba91c9")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--expected-digest", default="sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04")
    parser.add_argument("--keep-bootstrap", action="store_true", help="Keep a loopback-only service for explicit local verification")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9._/-]+:[a-z0-9._-]+", args.model) or "cloud" in args.model:
        parser.error("Select an explicit local model tag")
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logs = ROOT/"logs/local-vision"/run
    logs.mkdir(parents=True, exist_ok=False)
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    def command(name, *parts):
        print(name, flush=True)
        with (logs/(name+".log")).open("w", encoding="utf-8") as stream:
            result = subprocess.run([args.docker, *parts], stdout=stream, stderr=subprocess.STDOUT, **hidden)
        if result.returncode:
            raise RuntimeError(name+" failed; see "+str(logs/(name+".log")))
        return (logs/(name+".log")).read_text(encoding="utf-8").strip()
    exists = subprocess.run([args.docker,"container","inspect",BOOTSTRAP],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**hidden)
    if exists.returncode == 0:
        raise RuntimeError("Bootstrap container already exists; inspect it before retrying")
    command("pull_image", "pull", args.image)
    image = json.loads(command("image_inspect", "image", "inspect", args.image))[0]
    pinned_image = image["RepoDigests"][0]
    command("volume", "volume", "create", "--label", "org.fixrate.component=local-vision", VOLUME)
    launched = False
    success = False
    try:
        command("bootstrap", "run", "--detach", "--name", BOOTSTRAP, "--gpus", "all",
            "--publish", "127.0.0.1::11434", "--volume", VOLUME+":/root/.ollama",
            "--env", "OLLAMA_NO_CLOUD=1", "--env", "OLLAMA_NUM_PARALLEL=1",
            "--env", "OLLAMA_MAX_LOADED_MODELS=1", "--env", "OLLAMA_FLASH_ATTENTION=1",
            "--env", "OLLAMA_KV_CACHE_TYPE=q8_0", "--env", "OLLAMA_CONTEXT_LENGTH=4096", pinned_image)
        launched = True
        command("gpu", "exec", BOOTSTRAP, "nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader")
        info = json.loads(command("container", "inspect", BOOTSTRAP))[0]
        port = info["NetworkSettings"]["Ports"]["11434/tcp"][0]["HostPort"]
        base = "http://127.0.0.1:"+port
        for attempt in range(100):
            try:
                with urlopen(base+"/api/version", timeout=2) as response: version = json.load(response)
                break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError("Local vision bootstrap did not become ready")
        command("pull_model", "exec", BOOTSTRAP, "ollama", "pull", args.model)
        with urlopen(base+"/api/tags", timeout=10) as response: tags = json.load(response)
        model = next(m for m in tags["models"] if m["name"] == args.model)
        if re.fullmatch(r"[0-9a-f]{64}", model["digest"]):
            model["digest"]="sha256:"+model["digest"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", model["digest"]):
            raise RuntimeError("Invalid model manifest digest")
        if model["digest"] != args.expected_digest:
            raise RuntimeError("Downloaded model manifest differs from --expected-digest; refusing to adopt it")
        metadata = dict(image=pinned_image, image_tag=args.image, model=args.model, digest=model["digest"],
            volume=VOLUME, server_version=version["version"], size=model["size"], prepared_at=datetime.now(timezone.utc).isoformat(),
            logs=str(logs), bootstrap_url=base if args.keep_bootstrap else None, cloud_enabled=False)
        state = ROOT/"var/local-vision"
        state.mkdir(parents=True, exist_ok=True)
        (state/"model.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
        report = ROOT/"reports/local-vision"/run
        report.mkdir(parents=True, exist_ok=True)
        (report/"preparation.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(metadata, indent=2), flush=True)
        success = True
    finally:
        if launched and (not success or not args.keep_bootstrap):
            command("stop_bootstrap", "stop", BOOTSTRAP)
            command("remove_bootstrap", "rm", BOOTSTRAP)


if __name__ == "__main__":
    main()
