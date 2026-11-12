"""Upgrade a separately created database from 010; compare every preexisting row."""
from pathlib import Path
import re
from uuid import uuid4

from sqlalchemy import text

from app.db.session import make_engine
from app.manage import migrate, migration_checksum, seed_demo
from tests.backend.test_runtime_integration import runtime

ROOT = Path(__file__).resolve().parents[2]


def test_upgrade_010_preserves_all_rows_and_supports_full_day_shifts(runtime):
    runtime_engine, _ = runtime
    assert runtime_engine.url.database.startswith('fixrate_test_')
    name = 'fixrate_test_planning_upgrade_' + uuid4().hex
    with runtime_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.exec_driver_sql('CREATE DATABASE ' + name)
    engine = make_engine(runtime_engine.url.set(database=name))
    try:
        old = sorted((ROOT/'database/migrations').glob('*.sql'))
        old = [path for path in old if int(path.name[:3]) <= 10]
        with engine.begin() as conn:
            for path in old:
                sql = re.sub(r'(?m)^\s*(?:BEGIN|COMMIT);\s*$', '', path.read_text(encoding='utf-8-sig'))
                conn.connection.driver_connection.execute(sql)
            conn.exec_driver_sql('CREATE TABLE fixrate_schema_migrations (filename text PRIMARY KEY, sha256 char(64) NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
            for path in old:
                conn.execute(text('INSERT INTO fixrate_schema_migrations(filename,sha256) VALUES (:name,:hash)'),
                             dict(name=path.name, hash=migration_checksum(path)))
        seed_demo(engine, 'Isolated-migration-test-password')
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO employee_shift_rules(site_id,user_id,label,calendar_pattern,valid_from,starts_local,ends_local) "
                "SELECT site_id,user_id,'TEST legacy night shift','{}','2026-01-01','22:00','06:00' "
                "FROM site_memberships WHERE role IN ('executor','technician') LIMIT 1"))

        def snapshot():
            with engine.connect() as conn:
                names = list(conn.scalars(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name NOT IN ('fixrate_schema_migrations','maintenance_types')")))
                return {table: conn.scalar(text(f'SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,\'[]\')) FROM "{table}" t')) for table in names}

        before = snapshot()
        migrate(engine)
        migrate(engine)
        assert snapshot() == before
        with engine.begin() as conn:
            assert conn.scalar(text("SELECT count(*) FROM maintenance_types WHERE code='TO3' AND name='ТО3'")) == 1
            row = conn.execute(text('SELECT shift_rule_id,starts_local,ends_local FROM employee_shift_rules LIMIT 1')).one()
            conn.execute(text('UPDATE employee_shift_rules SET ends_local=starts_local WHERE shift_rule_id=:id'), dict(id=row.shift_rule_id))
            assert conn.scalar(text('SELECT starts_local=ends_local FROM employee_shift_rules WHERE shift_rule_id=:id'), dict(id=row.shift_rule_id))
    finally:
        engine.dispose()
        with runtime_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.exec_driver_sql('DROP DATABASE ' + name)
