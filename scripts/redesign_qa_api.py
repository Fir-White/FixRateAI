"""Entrypoint for the isolated redesign QA Docker container, never the live database."""
import os
from pathlib import Path

from app.db.session import make_engine
from app.manage import migrate, seed_demo

url = os.environ['DATABASE_URL']
assert '@fixrate-redesign-qa-db:5432/fixrate_redesign_qa' in url
password = os.environ['FIXRATE_TEST_PASSWORD']
engine = make_engine(url)
migrate(engine)
seed_demo(engine, password)
engine.dispose()
Path(os.environ['PHOTO_STORAGE_ROOT']).mkdir(parents=True, exist_ok=True)
os.execvp('python', ['python', 'scripts/start_backend.py', '--host', '0.0.0.0', '--port', '8000'])
