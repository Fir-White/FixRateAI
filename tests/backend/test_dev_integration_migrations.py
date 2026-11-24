"""Preserve populated schemas from either migration history on a disposable PostgreSQL."""
import json
import os
from pathlib import Path
from shutil import copyfile
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import manage
from app.assistant import graph_persistence
from app.db.session import make_engine
from app.integration.demo import demo_id


MIGRATIONS = Path(__file__).resolve().parents[2] / 'database/migrations'
CATALOG = ('027_source_catalog_hardening.sql', '028_source_catalog_backfill.sql', '029_source_catalog_legacy_index.sql')
ASSISTANT = ('027_assistant_turn_claim.sql', '028_assistant_graph_threads.sql', '029_assistant_tool_agent.sql')
MATERIALS = '030_work_consumptions.sql'


@pytest.mark.parametrize('applied', [CATALOG, ASSISTANT, (*CATALOG, MATERIALS)], ids=['dev', 'kran-dev', 'dev-backend-2'])
def test_upgrade_keeps_both_migration_histories_and_existing_rows(tmp_path, monkeypatch, applied):
    raw_url = os.environ.get('INTEGRATION_DATABASE_URL')
    if not raw_url:
        pytest.skip('Use scripts/verify.py with a disposable runtime database')
    url = make_url(raw_url)
    assert url.host in ('127.0.0.1', 'localhost') and url.database.startswith('fixrate_test_')
    source = tmp_path / 'database/migrations'
    source.mkdir(parents=True)
    for path in MIGRATIONS.glob('[0-9]*.sql'):
        if int(path.name[:3]) <= 26 or path.name in applied:
            copyfile(path, source / path.name)
    assert all((source / name).is_file() for name in applied)
    db = f'fixrate_test_integration_{uuid4().hex}'
    admin = make_engine(url)
    engine = make_engine(url.set(database=db))
    with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.exec_driver_sql('CREATE DATABASE ' + db)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(manage, 'ROOT', tmp_path)
            if ASSISTANT[1] not in applied:
                # The catalog-only releases had no LangGraph checkpoint setup.
                patch.setattr(graph_persistence, 'migrate', lambda _engine: None)
            manage.migrate(engine)
        manage.seed_demo(engine, 'TEST-only-integration-password')
        ids = dict(task=demo_id('runtime-order'), user=demo_id('user-1'), report=uuid4(), chat=uuid4(),
                   turn=uuid4(), request=uuid4(), source=uuid4(), material=uuid4(), sha='47' * 32,
                   book=json.dumps({'rows': [{'code': 'TEST-MERGE', 'sourceRef': 'TEST!A1', 'title': 'TEST upgrade'}]}))
        with engine.begin() as conn:
            ids['site'] = conn.scalar(text('SELECT site_id FROM work_orders WHERE work_order_id=:task'), ids)
            conn.execute(text("""INSERT INTO work_reports
                (work_report_id,site_id,work_order_id,submitted_by,comment)
                VALUES (:report,:site,:task,:user,'TEST retained report')"""), ids)
            conn.execute(text("""INSERT INTO assistant_conversations
                (conversation_id,site_id,user_id,role,title,agent)
                VALUES (:chat,:site,:user,'executor','TEST retained chat','assistant')"""), ids)
            conn.execute(text("""INSERT INTO assistant_turns
                (turn_id,conversation_id,request_key,content,status,prompt_version)
                VALUES (:turn,:chat,:request,'TEST retained reply','completed','TEST')"""), ids)
            conn.execute(text("""INSERT INTO source_imports
                (source_import_id,site_id,source_sha256,source_name,source_revision,status,row_count,source_rows,created_by)
                VALUES (:source,:site,:sha,'TEST.xlsx',1,'imported',1,CAST(:book AS jsonb),:user)"""), ids)
            if MATERIALS in applied:
                conn.execute(text("""INSERT INTO work_consumptions
                    (consumption_id,site_id,work_order_id,work_report_id,material_name,quantity,unit,recorded_by,
                    task_revision,idempotency_key)
                    VALUES (:material,:site,:task,:report,'TEST filter',2,'pcs',:user,1,:request)"""), ids)

        def ledger():
            with engine.connect() as conn:
                return dict((row.filename, (row.sha256, row.applied_at)) for row in conn.execute(
                    text('SELECT filename,sha256,applied_at FROM fixrate_schema_migrations')))

        before = ledger()
        manage.migrate(engine)
        after = ledger()
        manage.migrate(engine)
        assert ledger() == after
        assert all(after[name] == entry for name, entry in before.items())
        assert set((*CATALOG, *ASSISTANT, MATERIALS)) <= after.keys()
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT comment FROM work_reports WHERE work_report_id=:report'), ids) == 'TEST retained report'
            assert conn.execute(text("""SELECT content,execution_engine,agent_context FROM assistant_turns
                WHERE turn_id=:turn"""), ids).one() == ('TEST retained reply', 'v2', None)
            assert conn.scalar(text('SELECT source_rows->\'rows\'->0->>\'sourceRef\' FROM source_imports WHERE source_import_id=:source'), ids) == 'TEST!A1'
            quantity = conn.scalar(text('SELECT quantity FROM work_consumptions WHERE consumption_id=:material'), ids)
            assert quantity == (2 if MATERIALS in applied else None)
            if CATALOG[0] not in applied:
                assert conn.scalar(text('SELECT source_ref FROM source_catalog_index WHERE site_id=:site AND source_sha256=:sha'), ids) == 'TEST!A1'
    finally:
        engine.dispose()
        with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.exec_driver_sql('DROP DATABASE ' + db)
        admin.dispose()
