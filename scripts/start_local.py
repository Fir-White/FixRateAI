"""Persistent loopback-only demo stack, using private state and prepared real ML weights."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
PROJECT="fixrate-local"
STATE=ROOT/"var/compose-local"
ENVFILE=STATE/"runtime.env"


def main():
    docker=shutil.which("docker")
    if not docker and os.name=="nt":
        candidate=Path(os.environ.get("LOCALAPPDATA",""))/"Programs/DockerDesktop/resources/bin/docker.exe"
        if candidate.is_file(): docker=str(candidate)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker",default=docker or "docker")
    parser.add_argument("--port",type=int)
    parser.add_argument("--cache",type=Path,default=ROOT/".venv/hf-cache")
    parser.add_argument("--no-build",action="store_true")
    action=parser.add_mutually_exclusive_group()
    action.add_argument("--stop",action="store_true",help="Stop this project; keep all persistent volumes")
    action.add_argument("--status",action="store_true")
    args=parser.parse_args()
    hidden={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
    exists=ENVFILE.is_file()
    if not exists and (args.stop or args.status):
        parser.error("No local stack configuration exists yet")
    if not exists:
        subprocess.run([args.docker,"info","--format","{{.ServerVersion}}"],check=True,stdout=subprocess.DEVNULL,**hidden)
        found=subprocess.run([args.docker,"volume","ls","--filter","label=com.docker.compose.project="+PROJECT,"--format","{{.Name}}"],capture_output=True,text=True,check=True,**hidden)
        if found.stdout.strip():
            raise RuntimeError("Existing local volumes have no matching private configuration; refusing to replace credentials")
        cache=args.cache.resolve()
        if not cache.is_dir(): raise ValueError("Prepared CLIP cache directory is required; use --cache")
        port=args.port
        if port is None:
            for candidate in (8000,8080,8090):
                with socket.socket() as sock:
                    try: sock.bind(("127.0.0.1",candidate))
                    except OSError: continue
                    port=candidate; break
        if port is None or not 1<=port<=65535:
            raise ValueError("Select an available port with --port")
        with socket.socket() as sock: sock.bind(("127.0.0.1",port))
        values=dict(POSTGRES_PASSWORD=secrets.token_hex(32),FIXRATE_DEMO_PASSWORD="Local-"+secrets.token_urlsafe(15),
            FIXRATE_PORT=str(port),CLIP_CACHE_ROOT=cache.as_posix(),COOKIE_SECURE="false",
            FORECAST_TIMEOUT_SECONDS="2",PHOTO_REVIEW_TIMEOUT_SECONDS="20",PHOTO_REVIEW_MAX_FILES="20",PHOTO_REVIEW_MAX_BYTES="52428800")
        STATE.mkdir(parents=True,exist_ok=True)
        ENVFILE.write_text("".join(key+"="+value+"\n" for key,value in values.items()),encoding="utf-8")
    else:
        values=dict(line.split("=",1) for line in ENVFILE.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#"))
        if args.port is not None and str(args.port)!=values["FIXRATE_PORT"]:
            raise ValueError("Existing port is preserved; edit private runtime.env deliberately to change it")
    env=dict(os.environ,**values)
    base=[args.docker,"compose","--project-name",PROJECT,"--env-file",str(ENVFILE),
        "--project-directory",str(ROOT),"-f",str(ROOT/"compose.yaml"),"-f",str(ROOT/"compose.ml.yaml")]
    logdir=ROOT/"logs/local"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    logdir.mkdir(parents=True,exist_ok=False)
    def command(name,*parts):
        print(name,flush=True)
        result=subprocess.run([*base,*parts],cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",**hidden)
        raw=result.stdout+"\n"+result.stderr
        for key in ("POSTGRES_PASSWORD","FIXRATE_DEMO_PASSWORD"):
            raw=raw.replace(values[key],"[REDACTED]")
        (logdir/(name+".log")).write_text(raw,encoding="utf-8")
        if result.returncode:
            raise RuntimeError(name+" failed; see "+str(logdir/(name+".log")))
        return result.stdout
    command("config","config","--quiet")
    if args.stop:
        command("stop","down")
        print("Stopped; database and photo volumes are preserved.")
        return
    if args.status:
        print(command("status","ps"))
        return
    if not Path(values["CLIP_CACHE_ROOT"]).is_dir(): raise ValueError("Prepared CLIP cache is missing")
    if not args.no_build: command("build","build","app")
    command("start","up","--detach","--no-build","--wait","--wait-timeout","180")
    command("seed","exec","-T","-e","FIXRATE_DEMO_PASSWORD","app","python","-m","app.manage","seed-demo")
    readiness=command("models","exec","-T","app","python","-c",
        "import json; from ml_service.app.forecast.runtime import load_verified_forecaster; from ml_service.app.cv.classifier import CLIPZeroShotClassifier; rf=load_verified_forecaster(); cv=CLIPZeroShotClassifier(); assert rf.is_fitted and cv.is_torch_active; print(json.dumps(dict(rf='synthetic_demo:rf:'+rf.artifact_sha256[:16],clip=cv.model_ref)))")
    models=json.loads(readiness)
    origin="http://127.0.0.1:"+values["FIXRATE_PORT"]
    with urlopen(origin+"/api/health",timeout=10) as response:
        assert json.load(response)["database"]=="ready"
    accounts=STATE/"accounts.txt"
    emails=["fixrate-demo-admin@example.test","fixrate-demo-dispatcher@example.test","fixrate-demo-engineer@example.test","fixrate-demo-1@example.test"]
    emails.extend("fixrate-assignment-"+str(number)+"@example.test" for number in (1,2,3))
    accounts.write_text(origin+"\n\n"+"\n".join(emails)+"\n\nPassword: "+values["FIXRATE_DEMO_PASSWORD"]+"\n",encoding="utf-8")
    state_path=STATE/"state.json"
    previous=json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    if previous and previous.get("project")!=PROJECT:
        raise RuntimeError("Private state belongs to a different project")
    previous.update(project=PROJECT,url=origin,models=models,logs=str(logdir),
        database_volume=PROJECT+"_postgres_data",photo_volume=PROJECT+"_photos",started_at=datetime.now(timezone.utc).isoformat())
    state_path.write_text(json.dumps(previous,indent=2),encoding="utf-8")
    print(command("status","ps"))
    print("URL: "+origin)
    print("Accounts: "+str(accounts))
    print("Logs: "+str(logdir))

if __name__=="__main__": main()
