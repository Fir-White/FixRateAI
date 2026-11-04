"""Demo credential parsing and real PostgreSQL/HTTP rotation; no production fixtures."""
import json
import os
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.demo_accounts import (DEMO_ACCOUNTS, configure_demo_accounts,
                               read_demo_environment, validate_demo_credentials)
from app.integration.demo import demo_id
from scripts.start_local import read_runtime_values, write_runtime_values
from tests.backend.test_runtime_integration import runtime


@pytest.mark.parametrize("password", ["Demo-$!#=quote'pass", 'Demo-$double" space', "Demo-сложный-пароль"])
def test_env_and_private_runtime_preserve_literal_password(tmp_path, password):
    path = tmp_path / ".env"
    path.write_text("DATABASE_URL=ignored\nFIXRATE_DEMO_PASSWORD="+json.dumps(password, ensure_ascii=False)+" # local\n", encoding="utf-8")
    configured = read_demo_environment(path, {})
    assert configured == {"FIXRATE_DEMO_PASSWORD": password}
    private = tmp_path / "runtime.env"
    write_runtime_values(private, configured)
    assert read_runtime_values(private) == configured
    assert "DATABASE_URL" not in configured


def test_demo_environment_priority_single_quotes_and_comments(tmp_path):
    path = tmp_path / ".env"
    path.write_text("export FIXRATE_DEMO_LOGIN = 'person@example.test' # role\nFIXRATE_DEMO_PASSWORD=literal$pass#word # comment\n", encoding="utf-8")
    assert read_demo_environment(path, {"FIXRATE_DEMO_LOGIN": "override@example.test"}) == {
        "FIXRATE_DEMO_LOGIN": "override@example.test", "FIXRATE_DEMO_PASSWORD": "literal$pass#word"}
    assert read_demo_environment(tmp_path/"absent", {}) == {}


@pytest.mark.parametrize("raw", ['"unterminated', "'unterminated", '"valid" garbage'])
def test_invalid_env_does_not_echo_secret(tmp_path, raw):
    path = tmp_path / ".env"
    path.write_text("FIXRATE_DEMO_PASSWORD="+raw, encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid .env value") as exc:
        read_demo_environment(path, {})
    assert raw not in str(exc.value)


@pytest.mark.parametrize("password,values", [
    ("short", {}), ("long-but\nmultiline", {}),
    ("Long-demo-password", {"FIXRATE_DEMO_LOGIN": "not-email"}),
    ("Long-demo-password", {"FIXRATE_DEMO_LOGIN": "FIXRATE-DEMO-ADMIN@example.test"}),
])
def test_invalid_credentials_are_rejected_before_database(password, values):
    with pytest.raises(ValueError):
        configure_demo_accounts(None, password, values)


@pytest.fixture
def demo_accounts_snapshot(runtime):
    engine, app = runtime
    identities = [demo_id(key) for key in validate_demo_credentials("Snapshot-password", {})]
    with engine.connect() as conn:
        rows = [dict(conn.execute(text("SELECT user_id,email,password_hash FROM users WHERE user_id=:id"), {"id": uid}).mappings().one())
                for uid in identities]
    try:
        yield engine, app, rows
    finally:
        with engine.begin() as conn:
            for row in rows:
                conn.execute(text("UPDATE users SET email=:email,password_hash=:password_hash WHERE user_id=:user_id"), row)


def test_explicit_rotation_login_roles_sessions_idempotence_and_history(demo_accounts_snapshot):
    engine, app, original = demo_accounts_snapshot
    def business_state():
        with engine.connect() as conn:
            return [conn.execute(text("SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '[]'::jsonb) FROM "+table+" t")).scalar_one()
                    for table in ("work_orders", "work_assignments", "work_reports", "evidence_files", "acceptance_reviews")]
    before = business_state()
    previous = os.environ["FIXRATE_TEST_PASSWORD"]
    new = "New-demo-$!#=password"
    settings = {"FIXRATE_DEMO_LOGIN": "custom-dispatcher@example.test"}
    with closing(TestClient(app)) as old, closing(TestClient(app)) as current:
        assert old.post('/api/v1/auth/login', json=dict(email='fixrate-demo-dispatcher@example.test', password=previous)).status_code == 200
        assert configure_demo_accounts(engine, new, settings) == 7
        assert old.get('/api/v1/maintenance/ui/tasks').status_code == 401
        assert current.post('/api/v1/auth/login', json=dict(email='fixrate-demo-dispatcher@example.test', password=new)).status_code == 401
        assert current.post('/api/v1/auth/login', json=dict(email=settings['FIXRATE_DEMO_LOGIN'], password=previous)).status_code == 401
        response = current.post('/api/v1/auth/login', json=dict(email=settings['FIXRATE_DEMO_LOGIN'], password=new))
        assert response.status_code == 200 and response.json()['profile']['role'] == 'dispatcher'
        assert configure_demo_accounts(engine, new, settings) == 0
        assert current.get('/api/v1/maintenance/ui/tasks').status_code == 200
    for variable, (role, _, default) in DEMO_ACCOUNTS.items():
        with closing(TestClient(app)) as client:
            reply = client.post('/api/v1/auth/login', json=dict(email=settings.get(variable, default), password=new))
            assert reply.status_code == 200 and reply.json()['profile']['role'] == role
    for number in (1, 2, 3):
        with closing(TestClient(app)) as client:
            reply = client.post('/api/v1/auth/login', json=dict(email=f'fixrate-assignment-{number}@example.test', password=new))
            assert reply.status_code == 200 and reply.json()['profile']['role'] == 'executor'
    assert business_state() == before


def test_email_collision_is_atomic_and_unrelated_user_is_unchanged(demo_accounts_snapshot):
    engine, _, original = demo_accounts_snapshot
    uid = uuid4()
    email = f"real-{uid}@example.test"
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users(user_id,full_name,email,password_hash) VALUES (:id,'Unrelated user',:email,:hash)"),
                     dict(id=uid, email=email, hash=original[0]['password_hash']))
    try:
        with pytest.raises(ValueError, match="belongs to another account"):
            configure_demo_accounts(engine, "Collision-test-password", {
                "FIXRATE_DEMO_ADMIN_EMAIL": "new-admin@example.test", "FIXRATE_DEMO_LOGIN": email})
        with engine.connect() as conn:
            for row in original:
                assert dict(conn.execute(text("SELECT user_id,email,password_hash FROM users WHERE user_id=:id"), {"id": row['user_id']}).mappings().one()) == row
            assert conn.execute(text("SELECT email,password_hash FROM users WHERE user_id=:id"), {"id": uid}).one() == (email, original[0]['password_hash'])
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE user_id=:id"), {"id": uid})
