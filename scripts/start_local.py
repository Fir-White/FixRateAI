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
sys.path.insert(0, str(ROOT / "backend"))
from app.demo_accounts import DEMO_ACCOUNTS, DEMO_KEYS, read_demo_environment, validate_demo_credentials


def write_runtime_values(path, values):
    # Compose expands $, so escape it on disk; subprocess env carries literal values.
    path.write_text("".join(key+"="+json.dumps(value, ensure_ascii=False).replace("$", "$$")+"\n"
                            for key,value in values.items()), encoding="utf-8")


def read_runtime_values(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = json.loads(value).replace("$$", "$") if value.startswith('"') else value
    return values


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
    parser.add_argument("--bundled-image",help="Use a prebuilt local image with RF/CLIP weights inside")
    action=parser.add_mutually_exclusive_group()
    action.add_argument("--stop",action="store_true",help="Stop this project; keep all persistent volumes")
    action.add_argument("--status",action="store_true")
    args=parser.parse_args()
    if args.bundled_image and (args.stop or args.status):
        parser.error("Select an image when starting, not with --status or --stop")
    requested=read_demo_environment(ROOT/".env", os.environ) if not (args.stop or args.status) else {}
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
        if not args.bundled_image and not cache.is_dir(): raise ValueError("Prepared CLIP cache directory is required; use --cache")
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
        values=dict(POSTGRES_PASSWORD=secrets.token_hex(32),FIXRATE_DEMO_PASSWORD=requested.get("FIXRATE_DEMO_PASSWORD", "Local-"+secrets.token_urlsafe(15)),
            FIXRATE_PORT=str(port),CLIP_CACHE_ROOT=cache.as_posix(),COOKIE_SECURE="false",
            FORECAST_TIMEOUT_SECONDS="2",PHOTO_REVIEW_TIMEOUT_SECONDS="20",PHOTO_REVIEW_MAX_FILES="20",PHOTO_REVIEW_MAX_BYTES="52428800")
        STATE.mkdir(parents=True,exist_ok=True)
    else:
        values=read_runtime_values(ENVFILE)
        if args.port is not None and str(args.port)!=values["FIXRATE_PORT"]:
            raise ValueError("Existing port is preserved; edit private runtime.env deliberately to change it")
    if not (args.stop or args.status):
        values.update(requested)
        for key, (_, _, default) in DEMO_ACCOUNTS.items():
            values.setdefault(key, default)
        validate_demo_credentials(values["FIXRATE_DEMO_PASSWORD"], values)
    if args.bundled_image:
        subprocess.run([args.docker,"image","inspect",args.bundled_image],check=True,stdout=subprocess.DEVNULL,**hidden)
        values["FIXRATE_IMAGE"]=args.bundled_image
        values["FIXRATE_ML_PROFILE"]="bundled"
    if not exists:
        write_runtime_values(ENVFILE, values)
    bundled=values.get("FIXRATE_ML_PROFILE")=="bundled"
    env=dict(os.environ,**values)
    base=[args.docker,"compose","--project-name",PROJECT,"--env-file",str(ENVFILE),
        "--project-directory",str(ROOT)]
    for filename in (["compose.bundled.yaml"] if bundled else ["compose.yaml","compose.ml.yaml"]):
        base.extend(["-f",str(ROOT/filename)])
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
    if not bundled and not Path(values["CLIP_CACHE_ROOT"]).is_dir(): raise ValueError("Prepared CLIP cache is missing")
    if not args.no_build and not bundled: command("build","build","app")
    command("start","up","--detach","--no-build","--wait","--wait-timeout","180")
    account_env=[part for key in DEMO_KEYS for part in ("-e", key)]
    command("seed","exec","-T",*account_env,"app","python","-m","app.manage","seed-demo","--configure-accounts")
    write_runtime_values(ENVFILE, values)
    readiness=command("models","exec","-T","app","python","-c",
        "import json,os; from ml_service.app.forecast.runtime import load_verified_forecaster; from ml_service.app.cv.classifier import CLIPZeroShotClassifier; rf=load_verified_forecaster(); cv=CLIPZeroShotClassifier(); assert rf.is_fitted and cv.is_torch_active; print(json.dumps(dict(rf='synthetic_demo:rf:'+rf.artifact_sha256[:16],clip=cv.model_ref,source_revision=os.environ.get('FIXRATE_SOURCE_REVISION','unknown'))))")
    image_readiness=json.loads(readiness)
    models={key:image_readiness[key] for key in ("rf","clip")}
    origin="http://127.0.0.1:"+values["FIXRATE_PORT"]
    with urlopen(origin+"/api/health",timeout=10) as response:
        assert json.load(response)["database"]=="ready"
    accounts=STATE/"accounts.txt"
    emails=[role+": "+values[key] for key,(role,_,_) in DEMO_ACCOUNTS.items()]
    emails.extend("fixrate-assignment-"+str(number)+"@example.test" for number in (1,2,3))
    accounts.write_text(origin+"\n\n"+"\n".join(emails)+"\n\nPassword: "+values["FIXRATE_DEMO_PASSWORD"]+"\n",encoding="utf-8")
    state_path=STATE/"state.json"
    previous=json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    if previous and previous.get("project")!=PROJECT:
        raise RuntimeError("Private state belongs to a different project")
    previous.update(project=PROJECT,url=origin,models=models,logs=str(logdir),
        database_volume=PROJECT+"_postgres_data",photo_volume=PROJECT+"_photos",started_at=datetime.now(timezone.utc).isoformat(),
        image=values.get("FIXRATE_IMAGE","fixrate-ai:local"),image_profile="bundled" if bundled else "external-cache",
        source_revision=image_readiness.get("source_revision","unknown"))
    state_path.write_text(json.dumps(previous,indent=2),encoding="utf-8")
    print(command("status","ps"))
    print("URL: "+origin)
    print("Accounts: "+str(accounts))
    print("Logs: "+str(logdir))

if __name__=="__main__": main()
