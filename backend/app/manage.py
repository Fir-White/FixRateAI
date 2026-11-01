"""Explicit migrations and local demo provisioning; never run during API startup."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import text

from app.db.models import map_schema
from app.db.session import make_engine
from app.security.sessions import API_ROLES, hash_password

ROOT = Path(__file__).resolve().parents[2]


def migration_checksum(file):
    # Git's Windows line-ending conversion must not invalidate the ledger.
    return hashlib.sha256(file.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")).hexdigest()


def migrate(engine, adopt_existing=False):
    """One atomic transaction per migration, with checksum and advisory lock."""
    with engine.connect() as conn:
        raw = conn.connection.driver_connection
        raw.autocommit = True
        raw.execute("SELECT pg_advisory_lock(6813092026)")
        try:
            exists = raw.execute("SELECT to_regclass('public.fixrate_schema_migrations')").fetchone()[0]
            existing = raw.execute("SELECT to_regclass('public.sites')").fetchone()[0]
            files = sorted((ROOT / "database/migrations").glob("[0-9]*.sql"))
            if not exists and existing:
                if not adopt_existing:
                    raise RuntimeError("Existing schema: verify migrations 001–004 and use --adopt-existing")
                # Never bless an arbitrary preexisting schema as 001–004.
                mappings = map_schema(engine)
                mappings.registry.dispose()
                if raw.execute("SELECT to_regclass('public.fixrate_sessions')").fetchone()[0]:
                    raise RuntimeError("Runtime schema exists without a ledger; manual investigation required")
            with raw.transaction():
                raw.execute("""CREATE TABLE IF NOT EXISTS fixrate_schema_migrations
                    (filename TEXT PRIMARY KEY, sha256 CHAR(64) NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
                if not exists and existing:
                    for file in files[:4]:
                        raw.execute("INSERT INTO fixrate_schema_migrations(filename,sha256) VALUES (%s,%s)",
                                    (file.name, migration_checksum(file)))
            for file in files:
                checksum = migration_checksum(file)
                saved = raw.execute("SELECT sha256 FROM fixrate_schema_migrations WHERE filename=%s", (file.name,)).fetchone()
                if saved:
                    if saved[0] != checksum:
                        raise RuntimeError(f"Changed applied migration: {file.name}")
                    continue
                sql = re.sub(r"(?m)^\s*(?:BEGIN|COMMIT);\s*$", "", file.read_text(encoding="utf-8-sig"))
                with raw.transaction():
                    raw.execute(sql)
                    raw.execute("INSERT INTO fixrate_schema_migrations(filename,sha256) VALUES (%s,%s)", (file.name, checksum))
                print(f"Applied {file.name}")
        finally:
            raw.execute("SELECT pg_advisory_unlock(6813092026)")


def seed_demo(engine, password):
    # Explicit invocation only. Imported customer assumptions stay draft.
    from sqlalchemy.orm import Session
    from app.db.repository import MaintenanceRepository
    from app.integration.demo import add_runtime_demo
    with engine.connect() as conn:
        raw = conn.connection.driver_connection
        raw.autocommit = True
        raw.execute((ROOT / "database/seeds/001_customer_schedule_demo.sql").read_text(encoding="utf-8-sig"))
    models = map_schema(engine)
    with Session(engine) as session, session.begin():
        repo = MaintenanceRepository(session, models)
        add_runtime_demo(repo, hash_password(password))
    models.registry.dispose()


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    migration = sub.add_parser("migrate")
    migration.add_argument("--adopt-existing", action="store_true")
    sub.add_parser("seed-demo")
    user = sub.add_parser("create-user")
    user.add_argument("--email", required=True)
    user.add_argument("--name", required=True)
    user.add_argument("--site", type=UUID, required=True)
    user.add_argument("--role", choices=API_ROLES, required=True)
    args = parser.parse_args()
    engine = make_engine()
    try:
        if args.command == "migrate":
            migrate(engine, args.adopt_existing)
        elif args.command == "seed-demo":
            seed_demo(engine, os.environ.get("FIXRATE_DEMO_PASSWORD") or getpass.getpass("Demo password (12+ chars): "))
        else:
            password = hash_password(getpass.getpass("Password (12+ chars): "))
            with engine.begin() as conn:
                uid = conn.scalar(text("""INSERT INTO users(full_name,email,password_hash)
                    VALUES (:name,:email,:hash) RETURNING user_id"""), dict(name=args.name, email=args.email, hash=password))
                conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:user,:role)"),
                             dict(site=args.site, user=uid, role=API_ROLES[args.role]))
            print("User created")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
