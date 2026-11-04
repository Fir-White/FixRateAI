"""Explicit server launcher; migration is opt-in and seed is always separate."""
import argparse
import logging
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    parser=argparse.ArgumentParser()
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8000)
    parser.add_argument("--migrate",action="store_true")
    args=parser.parse_args()
    from app.config import RuntimeSettings
    RuntimeSettings.from_environment()
    if args.migrate:
        from app.db.session import make_engine
        from app.manage import migrate
        engine=make_engine()
        try:
            migrate(engine)
        finally:
            engine.dispose()
    handler=logging.StreamHandler()
    formatter=logging.Formatter("%(asctime)sZ %(levelname)s %(name)s %(message)s",datefmt="%Y-%m-%dT%H:%M:%S")
    formatter.converter=time.gmtime
    handler.setFormatter(formatter)
    application_logger=logging.getLogger("app")
    application_logger.handlers[:]=[handler]
    application_logger.setLevel(logging.INFO)
    application_logger.propagate=False
    import uvicorn
    # Query strings and cookies must not be emitted by default access logs.
    uvicorn.run("app.main:app",host=args.host,port=args.port,access_log=False)

if __name__ == "__main__":
    main()
