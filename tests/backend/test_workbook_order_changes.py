from uuid import uuid4

from sqlalchemy import text

from app.catalog_excel import write_workbook
from tests.backend.test_draft_plans import worker as add_worker
from tests.backend.test_management import managed
from tests.backend.test_publication import PATH, approve, prepared, publishing
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_runtime_integration import PREFIX
from tests.backend.test_workbooks import BASE, upload, workbook_site


def issued(managed):
    engine, _, _, _, ids = managed
    admin, _, proposal, _, worker = prepared(managed)
    proposal = approve(admin, proposal)
    result = admin.chief.post(PATH + proposal["proposal_id"] + "/publish", json=publishing(proposal))
    assert result.status_code == 200, result.text
    with engine.connect() as conn:
        order = conn.execute(text("SELECT * FROM work_orders WHERE site_id=:site"), ids).mappings().one()
    return admin, worker, order


def changes(chief, order, *, duplicate=False):
    rows = [["Наряд", "Начало", "План, чел.-ч", "Примечание"],
            [order["work_order_id"], "2027-01-02T10:00", "3.25", "Согласовано с диспетчером"]]
    if duplicate:
        rows.append(rows[1])
    result = upload(chief, write_workbook({"Сводка": [["Без изменений"]], "Изменения нарядов": rows}))
    assert result.status_code == 201, result.text
    return result.json(), f"{BASE}/{result.json()['book_id']}/versions/1/order-changes"


def test_confirmed_workbook_diff_updates_issued_order_not_source(workbook_site):
    engine, _, _, _, ids = workbook_site
    admin, worker, order = issued(workbook_site)
    book, path = changes(admin.chief, order)
    command = {"row_number": 2, "reason": "Согласован перенос"}
    targets = admin.chief.get(BASE + "/issued-orders", params={"q": str(order["work_order_id"])[:8]})
    assert targets.status_code == 200, targets.text
    assert [item["task_id"] for item in targets.json()["items"]] == [str(order["work_order_id"])]
    assert admin.get(BASE + "/issued-orders").status_code == 403
    rows = admin.chief.get(path)
    assert rows.status_code == 200, rows.text
    assert rows.json()["has_sheet"] and rows.json()["items"][0]["row_number"] == 2
    assert rows.json()["items"][0]["task_id"] == str(order["work_order_id"])
    assert not rows.json()["items"][0]["issue"]
    assert admin.post(path + "/preview", json=command).status_code == 403
    preview = admin.chief.post(path + "/preview", json=command)
    assert preview.status_code == 200, preview.text
    diff = preview.json()
    assert diff["can_apply"], diff
    assert diff["items"][0]["task_id"] == str(order["work_order_id"])
    assert diff["requires_assigned_confirmation"] and diff["items"][0]["planned_end"] == "2027-01-02T13:00"
    command.update(preview_digest=diff["preview_digest"], idempotency_key=str(uuid4()), confirm_assigned=True)
    assert admin.chief.post(path + "/apply", json=dict(command, confirm_assigned=False)).status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT revision FROM work_orders WHERE site_id=:site"), ids) == order["revision"]
    result = admin.chief.post(path + "/apply", json=command)
    assert result.status_code == 200, result.text
    assert admin.chief.post(path + "/apply", json=command).json()["replayed"]
    with engine.connect() as conn:
        fresh = conn.execute(text("SELECT * FROM work_orders WHERE site_id=:site"), ids).mappings().one()
        assert fresh["revision"] == order["revision"] + 1
        assert fresh["work_order_id"] == order["work_order_id"]
        for immutable in ("norm_hours_snapshot", "regulatory_deadline_at", "maintenance_rule_id"):
            assert fresh[immutable] == order[immutable]
        snap, original = fresh["operation_snapshot"], order["operation_snapshot"]
        assert snap["source_sha256"] == original["source_sha256"] and snap["checklist"] == original["checklist"]
        assert snap["planned_person_hours"] == "3.25"
        assert snap["worksheet_note"] == "Согласовано с диспетчером"
        assert str(conn.scalar(text("SELECT user_id FROM work_assignments WHERE site_id=:site AND status='assigned'"), ids)) == worker
        assert conn.scalar(text("SELECT count(*) FROM maintenance_notifications WHERE site_id=:site"), ids) == 2
        assert conn.scalar(text("SELECT planned_at FROM schedule_entries WHERE site_id=:site"), ids) == fresh["planned_start_at"]
        audit = conn.scalar(text("SELECT after_snapshot FROM audit_events WHERE site_id=:site AND action='workbook_reschedule'"), ids)
        assert audit["workbook"]["sha256"] == book["sha256"]


def test_workbook_diff_rejects_started_stale_or_ambiguous_order(workbook_site):
    engine, _, _, _, ids = workbook_site
    admin, _, order = issued(workbook_site)
    _, bad = changes(admin.chief, order, duplicate=True)
    command = {"row_number": 2, "reason": "Согласован перенос"}
    rows = admin.chief.get(bad)
    assert rows.status_code == 200 and all("несколько раз" in item["issue"] for item in rows.json()["items"])
    assert admin.chief.post(bad + "/preview", json=command).status_code == 422
    _, path = changes(admin.chief, order)
    preview = admin.chief.post(path + "/preview", json=command).json()
    assert preview["can_apply"], preview
    with engine.begin() as conn:
        conn.execute(text("UPDATE work_orders SET status='in_progress', started_at=now(), revision=revision+1 WHERE site_id=:site"), ids)
    result = admin.chief.post(path + "/apply", json=dict(command, preview_digest=preview["preview_digest"],
                                                        idempotency_key=str(uuid4()), confirm_assigned=True))
    assert result.status_code == 409, result.text
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT planned_start_at FROM work_orders WHERE site_id=:site"), ids) == order["planned_start_at"]
        assert conn.scalar(text("SELECT count(*) FROM maintenance_notifications WHERE site_id=:site"), ids) == 1


def test_workbook_move_rechecks_equipment_reserved_after_preview(workbook_site):
    engine, _, _, _, ids = workbook_site
    admin, _, order = issued(workbook_site)
    _, path = changes(admin.chief, order)
    command = {"row_number": 2, "reason": "Согласован перенос"}
    preview = admin.chief.post(path + "/preview", json=command).json()
    assert preview["can_apply"], preview
    with engine.begin() as conn:
        params = dict(ids, task=order["work_order_id"], other=uuid4())
        conn.execute(text("""
            INSERT INTO work_orders(work_order_id,site_id,system_id,maintenance_rule_id,origin,status,
                planned_start_at,planned_end_at,regulatory_deadline_at,required_people_snapshot,norm_hours_snapshot,
                norm_hours_basis_snapshot,operation_snapshot,created_by)
            SELECT :other,site_id,system_id,maintenance_rule_id,'manual','assigned',
                planned_start_at + interval '1 hour', planned_end_at + interval '1 hour',regulatory_deadline_at,
                required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot,operation_snapshot,created_by
            FROM work_orders WHERE site_id=:site AND work_order_id=:task
        """), params)
        conn.execute(text("""
            INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id,asset_snapshot)
            SELECT site_id,system_id,:other,equipment_id,asset_snapshot
            FROM work_order_equipment WHERE site_id=:site AND work_order_id=:task
        """), params)
    denied = admin.chief.post(path + "/apply", json=dict(command, preview_digest=preview["preview_digest"],
                                                        idempotency_key=str(uuid4()), confirm_assigned=True))
    assert denied.status_code == 409, denied.text
    current = admin.chief.post(path + "/preview", json=command).json()
    assert not current["can_apply"] and "Оборудование уже занято" in current["items"][0]["issue"]


def test_ordinary_assignment_respects_issued_equipment_reservation(workbook_site):
    engine, _, _, _, ids = workbook_site
    admin, _, order = issued(workbook_site)
    other_worker = add_worker(workbook_site, "Тест: свободный исполнитель для другого наряда")
    params = dict(ids, task=order["work_order_id"], other=uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO work_orders(work_order_id,site_id,system_id,maintenance_rule_id,origin,status,
                regulatory_deadline_at,required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot,operation_snapshot,created_by)
            SELECT :other,site_id,system_id,maintenance_rule_id,'manual','draft',
                regulatory_deadline_at,required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot,
                operation_snapshot - 'catalog_publication_id',created_by
            FROM work_orders WHERE site_id=:site AND work_order_id=:task
        """), params)
        conn.execute(text("""
            INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
            SELECT site_id,system_id,:other,equipment_id
            FROM work_order_equipment WHERE site_id=:site AND work_order_id=:task
        """), params)
    path = f"{PREFIX}/tasks/{params['other']}"
    search = admin.chief.post(path + "/assignment-preview", json=dict(
        expected_revision=1, start_local="2027-01-02T09:00", end_local="2027-01-02T12:00",
        executor_ids=[other_worker], individual_only=True))
    assert search.status_code == 200 and search.json()["command"], search.text
    result = admin.chief.post(path + "/assign", json=dict(search.json()["command"], reason="Тестовое назначение"))
    assert result.status_code == 409 and "Оборудование уже занято" in result.json()["detail"], result.text
