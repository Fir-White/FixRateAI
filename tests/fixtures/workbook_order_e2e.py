"""Publish a synthetic order over HTTP in the disposable fixrate-xlsx-check project."""
import json
import os
from contextlib import ExitStack
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db.session import make_engine
from tests.backend.test_publication import PATH, approve, prepared, publishing


def main():
    # Resolve the named QA containers rather than accepting destinations from the caller.
    url = make_url(os.environ["DATABASE_URL"])
    if url.host != "db" or url.database != "fixrate":
        raise SystemExit("Run only in the fixrate-xlsx-check Compose project.")
    password = os.environ["FIXRATE_TEST_PASSWORD"]
    engine = make_engine(url.set(host="fixrate-xlsx-check-db-1").render_as_string(hide_password=False))
    ids = dict(site=uuid4(), user=uuid4(), system=uuid4(), chief=uuid4(), marker=uuid4().hex)
    chief_email = f"chief-xlsx-{ids['marker']}@example.test"
    admin_email = f"admin-xlsx-{ids['marker']}@example.test"
    with engine.begin() as conn:
        ids["type"] = conn.scalar(text("SELECT equipment_type_id FROM equipment_types ORDER BY equipment_type_id LIMIT 1"))
        if not ids["type"]:
            raise RuntimeError("Seed the isolated demo database first.")
        conn.execute(text("INSERT INTO sites(site_id,name) VALUES (:site,'QA XLSX browser')"), ids)
        conn.execute(text("""
            INSERT INTO engineering_systems(system_id,site_id,code,name)
            VALUES (:system,:site,'XLSX-QA','QA XLSX equipment')
        """), ids)
        for who, email, role in ((ids["chief"], chief_email, "chief_engineer"), (ids["user"], admin_email, "admin")):
            params = dict(site=ids["site"], who=who, email=email, role=role)
            conn.execute(text("""
                INSERT INTO users(user_id,full_name,email,password_hash)
                SELECT :who,'QA XLSX browser',:email,password_hash
                FROM users WHERE email='fixrate-demo-admin@example.test'
            """), params)
            conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:who,:role)"), params)

    with ExitStack() as clients:
        def login(email):
            client = clients.enter_context(httpx.Client(base_url="http://fixrate-xlsx-check-app-1:8000", timeout=30))
            response = client.post("/api/v1/auth/login", json=dict(email=email, password=password))
            response.raise_for_status()
            client.headers["X-CSRF-Token"] = response.json()["csrfToken"]
            return client

        admin = login(admin_email)
        admin.chief = login(chief_email)
        _, _, proposal, _, _ = prepared((engine, None, admin, login, ids))
        approved = approve(admin, proposal)
        response = admin.chief.post(PATH + approved["proposal_id"] + "/publish", json=publishing(approved))
        response.raise_for_status()
        assert response.json()["state"] == "published"

    with engine.connect() as conn:
        task = conn.execute(text("""
            SELECT work_order_id FROM published_catalog_tasks WHERE site_id=:site
        """), ids).scalar_one()
    engine.dispose()
    print(json.dumps(dict(chiefEmail=chief_email, taskId=str(task))))


if __name__ == "__main__":
    main()
