"""Upgrade a separately created database from 010; compare every preexisting row."""
from pathlib import Path
import re
from uuid import uuid4
import json
import pytest

from sqlalchemy import text

from app.db.session import make_engine
from app.manage import migrate, migration_checksum, seed_demo
from tests.backend.test_runtime_integration import runtime

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('version',[10,13,14,15])
def test_upgrade_preserves_all_rows_and_supports_full_day_shifts(runtime,version):
    runtime_engine, _ = runtime
    assert runtime_engine.url.database.startswith('fixrate_test_')
    name = 'fixrate_test_planning_upgrade_' + uuid4().hex
    with runtime_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.exec_driver_sql('CREATE DATABASE ' + name)
    engine = make_engine(runtime_engine.url.set(database=name))
    try:
        old = sorted((ROOT/'database/migrations').glob('*.sql'))
        old = [path for path in old if int(path.name[:3]) <= version]
        with engine.begin() as conn:
            for path in old:
                sql = re.sub(r'(?m)^\s*(?:BEGIN|COMMIT);\s*$', '', path.read_text(encoding='utf-8-sig'))
                conn.connection.driver_connection.execute(sql)
            conn.exec_driver_sql('CREATE TABLE fixrate_schema_migrations (filename text PRIMARY KEY, sha256 char(64) NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
            for path in old:
                conn.execute(text('INSERT INTO fixrate_schema_migrations(filename,sha256) VALUES (:name,:hash)'),
                             dict(name=path.name, hash=migration_checksum(path)))
        seed_demo(engine, 'Isolated-migration-test-password')
        if version >= 13:
            from app.catalog_import import inspect_catalog
            from tests.fixtures.catalog_source import catalog_book
            content=catalog_book(5);catalog=inspect_catalog(content)
            with engine.begin() as conn:
                conn.execute(text('''INSERT INTO regulation_catalog_imports
                    (import_id,site_id,created_by,filename,source_sha256,parser_version,source_kind,source_file,summary,catalog_data)
                    SELECT :id,site_id,user_id,'synthetic-upgrade.xlsx',:sha,:parser,:kind,:file,CAST(:summary AS jsonb),CAST(:data AS jsonb)
                    FROM site_memberships WHERE role='chief_engineer' LIMIT 1'''),dict(id=uuid4(),sha=catalog['source_sha256'],
                    parser=catalog['parser_version'],kind=catalog['source_kind'],file=content,
                    summary=json.dumps(catalog['summary']),data=json.dumps(catalog)))
                if version>=14:
                    from app.schemas.catalog_decisions import DecisionInput
                    conn.execute(text('''INSERT INTO catalog_operation_decisions
                        (decision_id,site_id,import_id,row_number,revision,created_by,reason,payload,binding_snapshot)
                        SELECT :id,site_id,import_id,:row,1,created_by,'TEST ONLY upgrade decision',CAST(:payload AS jsonb),'[]'
                        FROM regulation_catalog_imports LIMIT 1'''),dict(id=uuid4(),row=catalog['operations'][0]['row'],payload=DecisionInput().model_dump_json()))
                if version>=15:
                    conn.execute(text('''INSERT INTO planning_draft_versions
                        (version_id,draft_id,site_id,import_id,revision,created_by,title,reason,starts_on,ends_on,input_sha256,
                         source_snapshot,resource_snapshot,occurrences,segments,validation_snapshot,summary,month_summary)
                        SELECT :version,:draft,site_id,import_id,1,created_by,'TEST ONLY retained draft','TEST ONLY upgrade',
                          '2027-01-01','2027-01-31',:sha,'{"test":"source"}','{"test":"resources"}','[]','[]','{}','{}','[]'
                        FROM regulation_catalog_imports LIMIT 1'''),dict(version=uuid4(),draft=uuid4(),sha='a'*64))
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO employee_shift_rules(site_id,user_id,label,calendar_pattern,valid_from,starts_local,ends_local) "
                "SELECT site_id,user_id,'TEST legacy night shift','{}','2026-01-01','22:00','06:00' "
                "FROM site_memberships WHERE role IN ('executor','technician') LIMIT 1"))

        # Compare all original columns/rows; later migrations may add columns and tables.
        with engine.connect() as conn:
            names = list(conn.scalars(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name NOT IN ('fixrate_schema_migrations','maintenance_types')")))
            columns = {name: list(conn.scalars(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:name ORDER BY ordinal_position"),dict(name=name))) for name in names}

        def snapshot():
            with engine.connect() as conn:
                return {name: conn.scalar(text(f'SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,\'[]\')) FROM (SELECT '+','.join('"'+c+'"' for c in columns[name])+f' FROM "{name}") t')) for name in names}

        before = snapshot()
        migrate(engine)
        migrate(engine)
        assert snapshot() == before
        with engine.begin() as conn:
            assert conn.scalar(text('SELECT count(*) FROM engineering_systems WHERE system_group IS NOT NULL OR revision<>1')) == 0
            assert conn.scalar(text('SELECT count(*) FROM equipment_components')) == 0
            assert conn.scalar(text('SELECT count(*) FROM regulation_catalog_imports')) == (1 if version>=13 else 0)
            assert conn.scalar(text('SELECT count(*) FROM catalog_operation_decisions')) == (1 if version>=14 else 0)
            assert conn.scalar(text('SELECT count(*) FROM planning_draft_versions')) == (1 if version>=15 else 0)
            assert conn.scalar(text('SELECT count(*) FROM draft_optimization_runs')) == 0
            assert conn.scalar(text("SELECT count(*) FROM maintenance_types WHERE code='TO3' AND name='ТО3'")) == 1
            row = conn.execute(text('SELECT shift_rule_id,starts_local,ends_local FROM employee_shift_rules LIMIT 1')).one()
            conn.execute(text('UPDATE employee_shift_rules SET ends_local=starts_local WHERE shift_rule_id=:id'), dict(id=row.shift_rule_id))
            assert conn.scalar(text('SELECT starts_local=ends_local FROM employee_shift_rules WHERE shift_rule_id=:id'), dict(id=row.shift_rule_id))
    finally:
        engine.dispose()
        with runtime_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.exec_driver_sql('DROP DATABASE ' + name)
