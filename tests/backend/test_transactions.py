"""Transaction lifecycle tests use SQLite only; not a PostgreSQL/DDL test."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db.session import service_transaction, session_dependency
from app.db.service import MaintenanceService
from app.schemas.maintenance_api import EquipmentCreate
from uuid import uuid4


def test_fastapi_service_commit_and_rollback_between_sessions(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    engine = create_engine(f"sqlite:///{tmp_path / 'transactions.db'}", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))
    factory = sessionmaker(engine, expire_on_commit=False)
    app = fastapi.FastAPI()
    dependency = session_dependency(factory)

    def authorise(session=fastapi.Depends(dependency)):
        session.execute(text("SELECT count(*) FROM items"))
        return session

    @app.post("/ok")
    def ok(session=fastapi.Depends(authorise)):
        with service_transaction(session):
            session.execute(text("INSERT INTO items (id, value) VALUES (1, 'saved')"))
        return {"ok": True}

    @app.post("/fail")
    def fail(session=fastapi.Depends(authorise)):
        with service_transaction(session):
            session.execute(text("INSERT INTO items (id, value) VALUES (2, 'rolled back')"))
            raise ValueError("failure")

    @app.post("/integrity")
    def integrity(session=fastapi.Depends(authorise)):
        with service_transaction(session):
            session.execute(text("INSERT INTO items (id, value) VALUES (3, 'rolled back')"))
            session.execute(text("INSERT INTO items (id, value) VALUES (1, 'duplicate')"))

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/ok").status_code == 200
        assert client.post("/fail").status_code == 500
        assert client.post("/integrity").status_code == 500
    with factory() as fresh:
        assert fresh.execute(text("SELECT id, value FROM items")).all() == [(1, "saved")]
    engine.dispose()


def test_service_does_not_commit_explicit_outer_transaction(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'outer.db'}")
    factory = sessionmaker(engine)
    with factory() as session:
        with session.begin():
            with pytest.raises(RuntimeError, match="explicitly managed"):
                with service_transaction(session):
                    pass
            assert session.in_transaction()
    engine.dispose()


def test_service_does_not_commit_existing_savepoint(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'savepoint.db'}")
    with sessionmaker(engine)() as session:
        session.execute(text("SELECT 1"))
        with session.begin_nested():
            with pytest.raises(RuntimeError, match="explicitly managed"):
                with service_transaction(session):
                    pass
            assert session.in_nested_transaction()
    engine.dispose()


def test_no_implicit_commit_in_dependency(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dependency.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY)"))
    factory = sessionmaker(engine)
    dep = session_dependency(factory)()
    session = next(dep)
    session.execute(text("INSERT INTO items VALUES (1)"))
    with pytest.raises(StopIteration):
        next(dep)
    with factory() as fresh:
        assert fresh.scalar(text("SELECT count(*) FROM items")) == 0
    engine.dispose()


def test_equipment_service_checks_site_and_commits(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'service.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (name TEXT NOT NULL)"))
    factory = sessionmaker(engine, expire_on_commit=False)
    site, system = uuid4(), uuid4()
    request = EquipmentCreate(site_id=site, equipment_type_id=uuid4(), inventory_code="x", name="pump")

    class Repository:
        def __init__(self, session):
            self.session = session

        def add(self, table, **values):
            assert table == "equipment" and values["system_id"] == system
            self.session.execute(text("INSERT INTO items (name) VALUES (:name)"), {"name": values["name"]})
            return values

        def ensure_site_system(self, site_id, system_id):
            assert site_id == site and system_id == system

    with factory() as session:
        service = MaintenanceService(Repository(session), site)
        session.execute(text("SELECT count(*) FROM items"))  # prior dependency read starts a transaction
        service.create_equipment(request, system_id=system)
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM items")) == 1
        with pytest.raises(ValueError, match="site"):
            MaintenanceService(Repository(session), uuid4()).create_equipment(request, system_id=system)
    engine.dispose()
