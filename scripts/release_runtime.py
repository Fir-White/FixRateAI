"""Container-only maintenance entrypoint. Never seeds data or downloads models."""
from __future__ import annotations
import argparse
import asyncio
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]


def files_export(root, output):
    root = Path(root).resolve()
    with tarfile.open(fileobj=output, mode='w|gz') as archive:
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                raise ValueError('Storage symlinks are not supported')
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)


def files_check(source):
    from pathlib import PurePosixPath
    with tarfile.open(fileobj=source, mode='r|gz') as archive:
        for member in archive:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or '\\' in member.name or ':' in member.name or not (member.isdir() or member.isfile()):
                raise ValueError('Unsafe storage backup member')
            if member.isfile():
                with archive.extractfile(member) as body:
                    while body.read(1024*1024): pass


def files_restore(root, source):
    """Validate every member before replacing anything; caller confirms replacement."""
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(dir=root.parent) as directory:
        staging = Path(directory)
        # Seekable archive is required to validate all names before extraction.
        with tempfile.TemporaryFile(dir=root.parent) as buffered:
            shutil.copyfileobj(source, buffered)
            buffered.seek(0)
            with tarfile.open(fileobj=buffered, mode='r:gz') as archive:
                for member in archive.getmembers():
                    target = (staging / member.name).resolve()
                    if not target.is_relative_to(staging) or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                        raise ValueError('Unsafe storage backup member')
                archive.extractall(staging, filter='data')
        root.mkdir(parents=True, exist_ok=True)
        for path in root.iterdir():
            if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
            else: path.unlink()
        for path in staging.iterdir(): shutil.move(str(path), root / path.name)


async def worker(engine):
    from app.main import create_app
    from app.optimization_worker import OptimizationManager
    from app.integration.scheduler import run
    app = create_app(engine)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for kind in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(kind, stop.set)
        except NotImplementedError: pass
    async with app.router.lifespan_context(app):
        manager = OptimizationManager(engine)
        app.state.optimizer = manager
        manager.start()
        schedule = asyncio.create_task(run(app))
        try:
            while not stop.is_set():
                if not manager.thread.is_alive(): raise RuntimeError('Optimization coordinator stopped')
                if schedule.done():
                    schedule.result()
                    raise RuntimeError('Maintenance scheduler stopped')
                Path('/tmp/fixrate-worker-heartbeat').write_text(str(time.time()))
                try: await asyncio.wait_for(stop.wait(), timeout=5)
                except TimeoutError: pass
        finally:
            schedule.cancel()
            try: await schedule
            except asyncio.CancelledError: pass
            manager.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('api','migrate','worker','worker-health','files-export','files-restore','files-check','recover-admin','schema-status','ollama-status','doctor'))
    parser.add_argument('--email')
    parser.add_argument('--confirm-data-replacement', action='store_true')
    args = parser.parse_args()
    if args.command.startswith('files-'):
        path = os.environ['PHOTO_STORAGE_ROOT']
        if args.command == 'files-export': files_export(path, sys.stdout.buffer)
        elif args.command == 'files-check': files_check(sys.stdin.buffer)
        elif not args.confirm_data_replacement: parser.error('Explicit data replacement confirmation required')
        else: files_restore(path, sys.stdin.buffer)
        return
    if args.command == 'ollama-status':
        import urllib.request
        url=os.environ.get('OLLAMA_CHAT_BASE_URL','http://host.docker.internal:11434').rstrip('/')
        with urllib.request.urlopen(url+'/api/tags',timeout=5) as response: result=json.load(response)
        print(json.dumps({'available':True,'installed_models':len(result.get('models',[])),'inference_requests':0}))
        return
    if args.command == 'api':
        import uvicorn
        uvicorn.run('app.main:app', host='0.0.0.0', port=8000, access_log=False, proxy_headers=True,
                    forwarded_allow_ips=os.environ.get('FIXRATE_TRUSTED_PROXIES','127.0.0.1'))
        return
    from sqlalchemy import text
    from app.db.session import make_engine
    engine = make_engine()
    try:
        if args.command == 'migrate':
            from app.manage import migrate
            from app.installation import arm_bootstrap
            migrate(engine)
            arm_bootstrap(engine)
        elif args.command == 'worker': asyncio.run(worker(engine))
        elif args.command == 'worker-health':
            if time.time()-float(Path('/tmp/fixrate-worker-heartbeat').read_text())>30: raise RuntimeError('Worker heartbeat expired')
            with engine.connect() as conn: conn.execute(text('SELECT 1'))
        elif args.command == 'schema-status':
            with engine.connect() as conn:
                print(json.dumps([dict(r) for r in conn.execute(text('SELECT filename,sha256 FROM fixrate_schema_migrations ORDER BY filename')).mappings()]))
        elif args.command == 'doctor':
            with engine.connect() as conn: conn.execute(text('SELECT 1'))
            storage=Path(os.environ['PHOTO_STORAGE_ROOT'])
            with tempfile.TemporaryFile(dir=storage) as probe:
                probe.write(b'fixrate-storage-probe');probe.seek(0)
                if probe.read()!=b'fixrate-storage-probe':raise RuntimeError('Storage probe failed')
            print(json.dumps({'database':'ready','storage':'read-write','storage_free_bytes':shutil.disk_usage(storage).free,
                              'source_revision':os.environ.get('FIXRATE_SOURCE_REVISION','unknown'),'automatic_model_downloads':False}))
        elif args.command == 'recover-admin':
            if not args.email or not args.confirm_data_replacement: parser.error('Email and explicit recovery confirmation required')
            from app.security.sessions import hash_password
            password=getpass.getpass('New administrator password (12+ characters): ')
            if not 12 <= len(password) <= 1024: raise ValueError('Password must contain 12 to 1024 characters')
            if password != getpass.getpass('Repeat password: '): raise ValueError('Passwords differ')
            with engine.begin() as conn:
                user=conn.execute(text("SELECT u.user_id,m.site_id FROM users u JOIN site_memberships m USING(user_id) WHERE lower(u.email)=lower(:email) AND m.role='admin' AND m.is_active FOR UPDATE OF u"),{'email':args.email}).mappings().first()
                if not user: raise ValueError('Active administrator not found')
                conn.execute(text('UPDATE users SET password_hash=:hash,is_active=true WHERE user_id=:id'),{'hash':hash_password(password),'id':user['user_id']})
                conn.execute(text('DELETE FROM fixrate_sessions WHERE user_id=:id'),{'id':user['user_id']})
                conn.execute(text("INSERT INTO audit_events(site_id,actor_type,entity_type,entity_id,action) VALUES (:site,'system','users',:user,'operator_password_recovery')"),dict(site=user['site_id'],user=user['user_id']))
            print('Administrator access recovered; existing sessions revoked.')
    finally: engine.dispose()

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        # SQLAlchemy/driver errors may include connection strings or row contents.
        print('Maintenance failed: '+type(exc).__name__+'. Inspect the private environment and database health.',file=sys.stderr)
        raise SystemExit(1)
