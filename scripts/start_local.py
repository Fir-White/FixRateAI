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
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
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


AI_KEYS = ("AITUNNEL_API_KEY", "AI_TUNNEL_API_KEY", "AITUNNEL_BASE_URL", "AITUNNEL_VISION_MODEL",
           "AITUNNEL_FORECAST_MODEL", "AITUNNEL_TIMEOUT_SECONDS", "AITUNNEL_REASONING_EFFORT", "FIXRATE_CLOUD_AI",
           "MAINTENANCE_SCHEDULER")


def read_ai_environment(path, environment=None):
    from dotenv import dotenv_values
    values = dotenv_values(path)
    current = os.environ if environment is None else environment
    return {key: current.get(key, values.get(key)) for key in AI_KEYS
            if current.get(key, values.get(key)) is not None}


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
    parser.add_argument("--presentation",action="store_true",help="Provision the isolated presentation object and accounts")
    ai_mode=parser.add_mutually_exclusive_group()
    ai_mode.add_argument("--local-vision",action="store_true",help="Use the prepared local vision-language model on GPU")
    ai_mode.add_argument("--cloud-ai",action="store_true",help="Use AI Tunnel for photo review and maintenance advice")
    parser.add_argument("--bundled-image",help="Use a prebuilt local image with RF/CLIP weights inside")
    action=parser.add_mutually_exclusive_group()
    action.add_argument("--stop",action="store_true",help="Stop this project; keep all persistent volumes")
    action.add_argument("--status",action="store_true")
    args=parser.parse_args()
    if (args.bundled_image or args.local_vision or args.cloud_ai) and (args.stop or args.status):
        parser.error("Select an image when starting, not with --status or --stop")
    requested=read_demo_environment(ROOT/".env", os.environ) if not (args.stop or args.status) else {}
    requested_ai=read_ai_environment(ROOT/".env") if not (args.stop or args.status) else {}
    cloud_requested=args.cloud_ai or (not args.local_vision and requested_ai.get("FIXRATE_CLOUD_AI", "").lower()=="true")
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
        if not args.bundled_image and not cloud_requested and not cache.is_dir(): raise ValueError("Prepared CLIP cache directory is required; use --cache")
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
    if not (args.stop or args.status):
        values.update(requested_ai)
    if args.cloud_ai or (not args.local_vision and values.get("FIXRATE_CLOUD_AI", "").lower()=="true"):
        values.update(FIXRATE_CLOUD_AI="true", FIXRATE_LOCAL_VISION="false", PHOTO_REVIEW_TIMEOUT_SECONDS="120",
                      FORECAST_TIMEOUT_SECONDS="100")
        from ml_service.app.providers.aitunnel import AITunnelConfig
        for tool in ("vision", "forecast"):
            if not AITunnelConfig.from_environment(tool, values).api_key:
                raise ValueError("Set AITUNNEL_API_KEY (or AI_TUNNEL_API_KEY) in .env before starting cloud mode")
    if args.local_vision:
        values["FIXRATE_CLOUD_AI"]="false"
        values["FORECAST_TIMEOUT_SECONDS"]="2"
        metadata_path=ROOT/"var/local-vision/model.json"
        if not metadata_path.is_file():
            raise ValueError("Prepare local vision first: python scripts/prepare_local_vision.py")
        metadata=json.loads(metadata_path.read_text(encoding="utf-8"))
        values.update(FIXRATE_LOCAL_VISION="true",OLLAMA_IMAGE=metadata["image"],
            OLLAMA_VISION_MODEL=metadata["model"],OLLAMA_VISION_DIGEST=metadata["digest"])
    if not exists:
        write_runtime_values(ENVFILE, values)
    bundled=values.get("FIXRATE_ML_PROFILE")=="bundled"
    env=dict(os.environ,**values)
    base=[args.docker,"compose","--project-name",PROJECT,"--env-file",str(ENVFILE),
        "--project-directory",str(ROOT)]
    cloud_ai=values.get("FIXRATE_CLOUD_AI")=="true"
    for filename in (["compose.bundled.yaml"] if bundled else ["compose.yaml"] if cloud_ai else ["compose.yaml","compose.ml.yaml"]):
        base.extend(["-f",str(ROOT/filename)])
    local_vision=values.get("FIXRATE_LOCAL_VISION")=="true"
    cloud_ai=values.get("FIXRATE_CLOUD_AI")=="true"
    if local_vision:
        base.extend(["-f",str(ROOT/"compose.vision.yaml")])
    if cloud_ai:
        base.extend(["-f",str(ROOT/"compose.cloud.yaml")])
    logdir=ROOT/"logs/local"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    logdir.mkdir(parents=True,exist_ok=False)
    def command(name,*parts):
        print(name,flush=True)
        result=subprocess.run([*base,*parts],cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",**hidden)
        raw=result.stdout+"\n"+result.stderr
        for key in ("POSTGRES_PASSWORD","FIXRATE_DEMO_PASSWORD","AITUNNEL_API_KEY","AI_TUNNEL_API_KEY"):
            if values.get(key): raw=raw.replace(values[key],"[REDACTED]")
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
    if not bundled and not cloud_ai and not Path(values["CLIP_CACHE_ROOT"]).is_dir(): raise ValueError("Prepared CLIP cache is missing")
    if not args.no_build and not bundled: command("build","build","app")
    command("start","up","--detach","--no-build","--remove-orphans","--wait","--wait-timeout","180")
    account_env=[part for key in DEMO_KEYS for part in ("-e", key)]
    command("seed","exec","-T",*account_env,"app","python","-m","app.manage","seed-demo","--configure-accounts")
    presentation=None
    if args.presentation:
        raw=command("presentation","exec","-T","-e","FIXRATE_DEMO_PASSWORD","app","python","-m","app.manage","seed-presentation")
        presentation=json.loads(raw.strip().splitlines()[-1])
        (STATE/"presentation.json").write_text(json.dumps(presentation,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_runtime_values(ENVFILE, values)
    if cloud_ai:
        readiness=command("models","exec","-T","app","python","-c",
            "import json,os; from ml_service.app.providers.aitunnel import AITunnelConfig; v=AITunnelConfig.from_environment('vision'); f=AITunnelConfig.from_environment('forecast'); assert v.api_key and f.api_key; print(json.dumps(dict(vision=v.model_ref,forecast=f.model_ref,source_revision=os.environ.get('FIXRATE_SOURCE_REVISION','unknown'))))")
        image_readiness=json.loads(readiness)
        models={key:image_readiness[key] for key in ("vision","forecast")}
    else:
        readiness=command("models","exec","-T","app","python","-c",
            "import json,os; from ml_service.app.forecast.runtime import load_verified_forecaster; from ml_service.app.cv.classifier import CLIPZeroShotClassifier; rf=load_verified_forecaster(); cv=CLIPZeroShotClassifier(); assert rf.is_fitted and cv.is_torch_active; print(json.dumps(dict(rf='synthetic_demo:rf:'+rf.artifact_sha256[:16],clip=cv.model_ref,source_revision=os.environ.get('FIXRATE_SOURCE_REVISION','unknown'))))")
        image_readiness=json.loads(readiness)
        models={key:image_readiness[key] for key in ("rf","clip")}
    if local_vision:
        vision_readiness=command("vision_model","exec","-T","app","python","-c",
            "from ml_service.app.cv.local_vision import LocalVisionConfig,LocalVisionClient; c=LocalVisionConfig.from_environment(); LocalVisionClient(c).check_model(); print(c.model_ref)")
        models["vision"]=vision_readiness.strip()
        command("vision_warmup","exec","-T","app","python","-c",
            "from ml_service.app.cv.local_vision import warmup_local_model; print(warmup_local_model())")
    origin="http://127.0.0.1:"+values["FIXRATE_PORT"]
    with urlopen(origin+"/api/health",timeout=10) as response:
        assert json.load(response)["database"]=="ready"
    accounts=STATE/"accounts.txt"
    emails=[role+": "+values[key] for key,(role,_,_) in DEMO_ACCOUNTS.items()]
    emails.extend("fixrate-assignment-"+str(number)+"@example.test" for number in (1,2,3))
    if presentation:
        presentation_roles = {"director", "chief_engineer", "engineer", "executor"}
        emails = [person["role"]+": "+person["email"]+" · "+person["name"]
                  for person in presentation["accounts"]
                  if person["role"] in presentation_roles and person["email"] in {
                      "director@fixrate.local", "chief@fixrate.local", "engineer@fixrate.local", "technician@fixrate.local"}]
    accounts.write_text(origin+"\n\n"+"\n".join(emails)+"\n\nPassword: "+values["FIXRATE_DEMO_PASSWORD"]+"\n",encoding="utf-8")
    state_path=STATE/"state.json"
    previous=json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    if previous and previous.get("project")!=PROJECT:
        raise RuntimeError("Private state belongs to a different project")
    previous.update(project=PROJECT,url=origin,models=models,logs=str(logdir),
        database_volume=PROJECT+"_postgres_data",photo_volume=PROJECT+"_photos",started_at=datetime.now(timezone.utc).isoformat(),
        image=values.get("FIXRATE_IMAGE","fixrate-ai:local"),image_profile="cloud" if cloud_ai else "bundled" if bundled else "external-cache",
        source_revision=image_readiness.get("source_revision","unknown"))
    state_path.write_text(json.dumps(previous,indent=2),encoding="utf-8")
    print(command("status","ps"))
    print("URL: "+origin)
    print("Accounts: "+str(accounts))
    print("Logs: "+str(logdir))

if __name__=="__main__": main()
