"""Integration tests; TEST_DATABASE_URL must name an empty disposable test DB."""
from datetime import date, datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.db.models import TABLES, map_schema
from app.db.repository import MaintenanceRepository
from app.db.dto import equipment_create_values
from app.db.session import service_transaction
from app.db.service import MaintenanceService
from app.schemas.maintenance_api import EquipmentCreate


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty disposable PostgreSQL database")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not parsed.database or not parsed.database.startswith("fixrate_test_"):
        pytest.fail("TEST_DATABASE_URL must use psycopg and a database named fixrate_test_*")
    engine = create_engine(url)
    with engine.connect() as check:
        objects = check.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE n.nspname=current_schema() AND c.relkind IN ('r','p','v','m','S','f'))
                OR EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                           WHERE n.nspname=current_schema())
        """))
    if objects:
        engine.dispose()
        pytest.fail("Refusing to apply migrations: test schema is not empty")
    root = Path(__file__).resolve().parents[2]
    with engine.connect() as conn:
        # SQL migration files own their BEGIN/COMMIT boundaries.
        raw = conn.connection.driver_connection
        raw.autocommit = True
        migrations = root / "database/migrations"
        for file in (migrations / name for name in ("001_tl02.sql", "002_planning_contract.sql", "003_occurrence_uniqueness.sql", "004_tl03_safe_constraints.sql")):
            raw.execute(file.read_text(encoding="utf-8-sig"))
        raw.autocommit = False
    models = map_schema(engine)
    yield engine, models
    engine.dispose()


@pytest.fixture
def store(database):
    engine, models = database
    with engine.connect() as conn:
        transaction = conn.begin()
        with Session(conn, expire_on_commit=False) as session:
            yield MaintenanceRepository(session, models), session
        transaction.rollback()


def seed(repo):
    s = repo.add("sites", name="site")
    u = repo.add("users", full_name="Engineer", email=f"{uuid4()}@example.test")
    repo.add("site_memberships", site_id=s.site_id, user_id=u.user_id, role="engineer")
    sys = repo.add("engineering_systems", site_id=s.site_id, code="sys", name="System")
    eqtype = repo.add("equipment_types", code="type", name="Type")
    request = EquipmentCreate(site_id=s.site_id, equipment_type_id=eqtype.equipment_type_id,
                              inventory_code="eq", name="Equipment", commissioned_on=date(2026, 1, 1))
    eq = repo.add("equipment", **equipment_create_values(request, system_id=sys.system_id))
    typ = repo.add("maintenance_types", code="TO", name="TO")
    doc = repo.add("regulation_documents", site_id=s.site_id, title="regulation")
    ed = repo.add("regulation_editions", site_id=s.site_id, regulation_document_id=doc.regulation_document_id, edition_code="A", effective_from=date(2026, 1, 1))
    op = repo.add("operation_templates", site_id=s.site_id, system_id=sys.system_id, code="1.1", title="Operation", maintenance_type_id=typ.maintenance_type_id)
    rule = repo.add("maintenance_rules", site_id=s.site_id, system_id=sys.system_id, operation_template_id=op.operation_template_id, regulation_edition_id=ed.regulation_edition_id, period_unit="day", scheduling_mode="fixed_interval", required_people=1, norm_hours=Decimal("1.125"), active_from=date(2026, 1, 1), source_text="daily", source_ref="source")
    binding = repo.add("rule_equipment", site_id=s.site_id, system_id=sys.system_id, maintenance_rule_id=rule.maintenance_rule_id, equipment_id=eq.equipment_id, valid_from=date(2026, 1, 1))
    plan = repo.add("schedule_plans", site_id=s.site_id, period_year=2026, period_month=10, created_by=u.user_id)
    entry = repo.add("schedule_entries", site_id=s.site_id, system_id=sys.system_id, schedule_plan_id=plan.schedule_plan_id, maintenance_rule_id=rule.maintenance_rule_id, binding_id=binding.binding_id, planned_date=date(2026, 10, 1), regulatory_deadline_on=date(2026, 10, 1), regulatory_deadline_at=datetime(2026, 10, 1, 18, tzinfo=timezone.utc))
    return s, u, sys, eq, ed, op, rule, plan, entry


def test_mapping_and_creation(store, database):
    repo, session = store
    engine, models = database
    assert set(models.classes) == set(TABLES)
    assert set(models.registry.metadata.tables) == set(inspect(engine).get_table_names())
    tables = models.registry.metadata.tables
    assert tables["schedule_entries"].c.planned_date.type.python_type is date
    assert tables["schedule_entries"].c.regulatory_deadline_at.type.timezone is True
    assert (tables["work_orders"].c.norm_hours_snapshot.type.precision,
            tables["work_orders"].c.norm_hours_snapshot.type.scale) == (13, 3)
    fk = next(f for f in tables["work_orders"].foreign_key_constraints if f.name == "fk_work_orders_entry_rule")
    assert [e.parent.name for e in fk.elements] == ["site_id", "system_id", "schedule_entry_id", "maintenance_rule_id"]
    assert [e.column.table.name for e in fk.elements] == ["schedule_entries"] * 4
    s, u, sys, eq, ed, op, rule, plan, entry = seed(repo)
    order = repo.add("work_orders", site_id=s.site_id, system_id=sys.system_id, maintenance_rule_id=rule.maintenance_rule_id, schedule_entry_id=entry.schedule_entry_id, required_people_snapshot=1, norm_hours_snapshot=Decimal("1.125"))
    session.expire_all()
    assert repo.get("equipment", eq.equipment_id).system.name == "System"
    assert repo.get("work_orders", order.work_order_id).entry.planned_date == date(2026, 10, 1)
    assert repo.get("work_orders", order.work_order_id).norm_hours_snapshot == Decimal("1.125")
    assert repo.rules_for_equipment(s.site_id, eq.equipment_id)[0].rule.operation.title == "Operation"
    with Session(session.connection()) as fresh:
        loaded = fresh.get(repo.models["work_orders"], order.work_order_id)
        assert loaded.norm_hours_snapshot == Decimal("1.125")
        assert loaded.entry.rule.maintenance_rule_id == rule.maintenance_rule_id


def test_invalid_rule_and_fk_with_savepoint(store):
    repo, session = store
    s, u, sys, eq, ed, op, rule, plan, entry = seed(repo)
    rule2 = repo.add("maintenance_rules", site_id=s.site_id, system_id=sys.system_id, operation_template_id=op.operation_template_id, regulation_edition_id=ed.regulation_edition_id, rule_version=2, period_unit="day", scheduling_mode="fixed_interval", required_people=1, active_from=date(2026, 1, 1), source_text="daily", source_ref="source")
    with pytest.raises(IntegrityError), session.begin_nested():
        repo.add("work_orders", site_id=s.site_id, system_id=sys.system_id, maintenance_rule_id=rule2.maintenance_rule_id, schedule_entry_id=entry.schedule_entry_id, required_people_snapshot=1, norm_hours_snapshot=Decimal("1.125"))
    with pytest.raises(IntegrityError), session.begin_nested():
        repo.add("equipment", site_id=s.site_id, system_id=uuid4(), asset_code="bad", name="bad")
    assert repo.get("sites", s.site_id).name == "site"


def test_norms_and_history(store):
    repo, session = store
    s, u, sys, eq, ed, op, rule, plan, entry = seed(repo)
    order = repo.add("work_orders", site_id=s.site_id, system_id=sys.system_id, maintenance_rule_id=rule.maintenance_rule_id, schedule_entry_id=entry.schedule_entry_id, status="completed", required_people_snapshot=1, norm_hours_snapshot=Decimal("1.125"))
    for n, value in enumerate(("1.000", "1.125", "48.000", "60.000", "0.001")):
        # Manual orders do not require a schedule entry.
        obj = repo.add("work_orders", site_id=s.site_id, system_id=sys.system_id, origin="manual", required_people_snapshot=1, norm_hours_snapshot=Decimal(value))
        session.expire(obj)
        assert obj.norm_hours_snapshot == Decimal(value)
    report = repo.add("work_reports", site_id=s.site_id, work_order_id=order.work_order_id, revision_no=1, submitted_by=u.user_id)
    repo.add("evidence_files", site_id=s.site_id, work_order_id=order.work_order_id, work_report_id=report.work_report_id, uploaded_by=u.user_id, stage="after", storage_key="test", mime_type="image/jpeg", file_size=10, sha256="a" * 64)
    repo.add("acceptance_reviews", site_id=s.site_id, work_order_id=order.work_order_id, work_report_id=report.work_report_id, reviewer_user_id=u.user_id, decision="accepted")
    with pytest.raises(ValueError):
        repo.supersede_future_entry(s.site_id, entry.schedule_entry_id, date(2026, 1, 1))
    session.expire_all()
    reports, photos, reviews = repo.history(s.site_id, order.work_order_id)
    assert len(reports) == len(photos) == len(reviews) == 1
    assert repo.get("work_orders", order.work_order_id).norm_hours_snapshot == Decimal("1.125")


def test_equipment_dto_rejects_unmapped_state():
    request = EquipmentCreate(site_id=uuid4(), equipment_type_id=uuid4(), inventory_code="x", name="x", state="out_of_service")
    with pytest.raises(ValueError, match="no agreed"):
        equipment_create_values(request, system_id=uuid4())


def test_forecasts_and_two_reports(store):
    repo, session = store
    s, u, sys, eq, ed, op, rule, plan, entry = seed(repo)
    deadline = datetime(2026, 10, 1, 18, tzinfo=timezone.utc)
    predictions = []
    for method in ("rule", "ai"):
        version = repo.add("predictor_versions", kind=method, name=method, version="1")
        predictions.append(repo.add("forecast_runs", site_id=s.site_id, system_id=sys.system_id,
            maintenance_rule_id=rule.maintenance_rule_id, equipment_id=eq.equipment_id,
            predictor_version_id=version.predictor_version_id, method=method, status="ok",
            proposal_at=deadline, regulatory_deadline_at=deadline, input_snapshot={"source": "test"}, rationale=method))
    orchestrator = repo.add("predictor_versions", kind="orchestrator", name="orchestrator", version="1")
    decision = repo.add("orchestration_decisions", site_id=s.site_id, system_id=sys.system_id,
        maintenance_rule_id=rule.maintenance_rule_id, rule_forecast_id=predictions[0].forecast_run_id,
        ai_forecast_id=predictions[1].forecast_run_id, orchestrator_version_id=orchestrator.predictor_version_id,
        selected_method="rule", selected_at=deadline, regulatory_deadline_at=deadline, reason="test")
    order = repo.add("work_orders", site_id=s.site_id, system_id=sys.system_id, maintenance_rule_id=rule.maintenance_rule_id,
        schedule_entry_id=entry.schedule_entry_id, required_people_snapshot=1, norm_hours_snapshot=Decimal("1.125"))
    for revision, result in ((1, "rework"), (2, "accepted")):
        report = repo.add("work_reports", site_id=s.site_id, work_order_id=order.work_order_id, revision_no=revision, submitted_by=u.user_id)
        repo.add("evidence_files", site_id=s.site_id, work_order_id=order.work_order_id, work_report_id=report.work_report_id,
            uploaded_by=u.user_id, stage="after", storage_key=f"photo-{revision}", mime_type="image/jpeg", file_size=10, sha256="a" * 64)
        repo.add("acceptance_reviews", site_id=s.site_id, work_order_id=order.work_order_id, work_report_id=report.work_report_id,
            reviewer_user_id=u.user_id, decision=result)
    session.expire_all()
    forecasts = repo.forecasts(s.site_id, rule.maintenance_rule_id)
    assert {f.predictor.version for f in forecasts} == {"1"}
    assert {f.rationale for f in forecasts} == {"rule", "ai"}
    assert repo.get("orchestration_decisions", decision.orchestration_decision_id).ai_forecast_id == predictions[1].forecast_run_id
    reports, photos, reviews = repo.history(s.site_id, order.work_order_id)
    assert [r.revision_no for r in reports] == [1, 2]
    assert len(photos) == len(reviews) == 2
    assert {photo.work_report_id for photo in photos} == {r.work_report_id for r in reports}


def test_new_rule_and_future_schedule_preserve_completed_order(store):
    repo, session = store
    s, u, sys, eq, ed, op, rule, plan, entry = seed(repo)
    old = repo.add("work_orders", site_id=s.site_id, system_id=sys.system_id,
        maintenance_rule_id=rule.maintenance_rule_id, schedule_entry_id=entry.schedule_entry_id,
        status="completed", required_people_snapshot=1, norm_hours_snapshot=Decimal("1.125"))
    report = repo.add("work_reports", site_id=s.site_id, work_order_id=old.work_order_id, revision_no=1, submitted_by=u.user_id)
    photo = repo.add("evidence_files", site_id=s.site_id, work_order_id=old.work_order_id, work_report_id=report.work_report_id,
        uploaded_by=u.user_id, stage="after", storage_key="old-photo", mime_type="image/jpeg", file_size=10, sha256="a" * 64)
    review = repo.add("acceptance_reviews", site_id=s.site_id, work_order_id=old.work_order_id, work_report_id=report.work_report_id,
        reviewer_user_id=u.user_id, decision="accepted")
    future = repo.add("schedule_entries", site_id=s.site_id, system_id=sys.system_id,
        schedule_plan_id=plan.schedule_plan_id, maintenance_rule_id=rule.maintenance_rule_id,
        planned_date=date(2026, 10, 10), regulatory_deadline_on=date(2026, 10, 10),
        regulatory_deadline_at=datetime(2026, 10, 10, 18, tzinfo=timezone.utc))
    rule2 = repo.add("maintenance_rules", site_id=s.site_id, system_id=sys.system_id,
        operation_template_id=op.operation_template_id, regulation_edition_id=ed.regulation_edition_id,
        supersedes_rule_id=rule.maintenance_rule_id, rule_version=2, period_unit="day", scheduling_mode="fixed_interval",
        required_people=1, norm_hours=Decimal("2.125"), active_from=date(2026, 10, 2), source_text="daily", source_ref="source B")
    repo.supersede_future_entry(s.site_id, future.schedule_entry_id, date(2026, 10, 2))
    next_plan = repo.add("schedule_plans", site_id=s.site_id, period_year=2026, period_month=10, revision=2, created_by=u.user_id)
    new_entry = repo.add("schedule_entries", site_id=s.site_id, system_id=sys.system_id,
        schedule_plan_id=next_plan.schedule_plan_id, maintenance_rule_id=rule2.maintenance_rule_id,
        planned_date=date(2026, 10, 10), regulatory_deadline_on=date(2026, 10, 10),
        regulatory_deadline_at=datetime(2026, 10, 10, 18, tzinfo=timezone.utc))
    session.expire_all()
    assert repo.get("work_orders", old.work_order_id).norm_hours_snapshot == Decimal("1.125")
    assert repo.get("work_orders", old.work_order_id).maintenance_rule_id == rule.maintenance_rule_id
    assert repo.get("schedule_entries", future.schedule_entry_id).status == "superseded"
    assert repo.get("schedule_entries", new_entry.schedule_entry_id).maintenance_rule_id == rule2.maintenance_rule_id
    assert repo.get("evidence_files", photo.evidence_file_id).work_report_id == report.work_report_id
    assert repo.get("acceptance_reviews", review.acceptance_review_id).decision == "accepted"


def test_postgres_commit_and_rollback_across_sessions(database):
    engine, models = database
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        with service_transaction(session):
            site = MaintenanceRepository(session, models).add("sites", name=f"committed-{uuid4()}")
            site_id = site.site_id
    with factory() as session:
        assert session.get(models["sites"], site_id) is not None
    with factory() as session:
        with pytest.raises(RuntimeError, match="test rollback"):
            with service_transaction(session):
                site = MaintenanceRepository(session, models).add("sites", name=f"rolledback-{uuid4()}")
                rollback_id = site.site_id
                raise RuntimeError("test rollback")
    with factory() as session:
        assert session.get(models["sites"], rollback_id) is None


@pytest.mark.parametrize("status", ["draft", "assigned", "in_progress", "in_review", "rework", "completed", "cancelled"])
def test_supersede_refuses_every_existing_order_status(store, status):
    repo, _ = store
    s, u, sys, eq, ed, op, rule, plan, entry = seed(repo)
    repo.add("work_orders", site_id=s.site_id, system_id=sys.system_id, maintenance_rule_id=rule.maintenance_rule_id,
             schedule_entry_id=entry.schedule_entry_id, status=status, required_people_snapshot=1,
             norm_hours_snapshot=Decimal("1.125"))
    with pytest.raises(ValueError, match="has a work order"):
        repo.supersede_future_entry(s.site_id, entry.schedule_entry_id, date(2026, 1, 1))


def test_equipment_service_postgres_autobegin_and_failures(database):
    engine, models = database
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        with service_transaction(session):
            repo = MaintenanceRepository(session, models)
            site = repo.add("sites", name="service site")
            other = repo.add("sites", name="other site")
            system = repo.add("engineering_systems", site_id=site.site_id, code="svc", name="system")
            other_system = repo.add("engineering_systems", site_id=other.site_id, code="svc", name="other system")
            typ = repo.add("equipment_types", code=f"type-{uuid4()}", name="type")
            site_id, other_id, system_id, other_system_id, type_id = site.site_id, other.site_id, system.system_id, other_system.system_id, typ.equipment_type_id
    request = EquipmentCreate(site_id=site_id, equipment_type_id=type_id, inventory_code="svc-asset", name="Equipment")
    with factory() as session:
        repo = MaintenanceRepository(session, models)
        assert session.get(models["sites"], site_id) is not None  # auth dependency autobegin
        equipment = MaintenanceService(repo, site_id).create_equipment(request, system_id=system_id)
        equipment_id = equipment.equipment_id
    with factory() as session:
        assert session.get(models["equipment"], equipment_id).asset_code == "svc-asset"
    with factory() as session:
        service = MaintenanceService(MaintenanceRepository(session, models), site_id)
        with pytest.raises(LookupError, match="system"):
            service.create_equipment(request.model_copy(update={"inventory_code": "bad-system"}), system_id=other_system_id)
        with pytest.raises(LookupError, match="system"):
            service.create_equipment(request.model_copy(update={"inventory_code": "missing-system"}), system_id=uuid4())
        with pytest.raises(ValueError, match="site"):
            service.create_equipment(request.model_copy(update={"site_id": other_id}), system_id=system_id)
        with pytest.raises(IntegrityError):
            service.create_equipment(request.model_copy(update={"inventory_code": "bad-type", "equipment_type_id": uuid4()}), system_id=system_id)
        missing_site = uuid4()
        with pytest.raises(LookupError, match="Site"):
            MaintenanceService(MaintenanceRepository(session, models), missing_site).create_equipment(
                request.model_copy(update={"site_id": missing_site, "inventory_code": "missing-site"}), system_id=system_id)
    with factory() as session:
        Equipment = models["equipment"]
        assert session.query(Equipment).filter(Equipment.site_id == site_id, Equipment.asset_code.in_(["bad-system", "missing-system", "bad-type"])).count() == 0
