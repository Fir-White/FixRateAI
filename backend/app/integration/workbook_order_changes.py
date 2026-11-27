"""Apply a reviewed, explicitly linked row from an immutable workbook version."""
from collections import Counter
import re
from uuid import UUID

from fastapi import Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text

from app.catalog_excel import read_workbook
from .order_table import Apply, ExistingRow, Preview, _apply, _plan
from .workbooks import BASE, CACHE, read_version, require_editor


SHEET = "Изменения нарядов"
HEADERS = ("Наряд", "Начало", "План, чел.-ч", "Примечание")
ORDER_CHANGES = BASE + "/{book_id}/versions/{version}/order-changes"
ISSUED_ORDERS = BASE + "/issued-orders"
PAGE = 25


class WorkbookPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    row_number: int = Field(ge=2, le=1_048_576)
    reason: str = Field(min_length=1, max_length=1000)


class WorkbookApply(WorkbookPreview):
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: UUID
    confirm_assigned: bool = False


def _rows(content):
    try:
        sheet = read_workbook(content, datetime_cells=True).get(SHEET)
    except ValueError:
        return False, [], "Не удалось прочитать лист изменений."
    if sheet is None:
        return False, [], None
    if not sheet or sheet[0][0] != 1 or tuple(sheet[0][1].get(c, {}).get("value") for c in "ABCD") != HEADERS:
        return True, [], "Укажите в A1:D1 заголовки: " + " | ".join(HEADERS)
    rows = []
    for number, cells in sheet[1:]:
        if not any(c["value"] or c["formula"] for c in cells.values()):
            continue
        value = {col: cells.get(col, {}).get("value", "") for col in "ABCD"}
        try:
            task = UUID(value["A"])
        except ValueError:
            task = None
        issue = None
        if any(cells.get(col, {}).get("formula") for col in "ABCD"):
            issue = "Для правок наряда вставьте значения вместо формул"
        elif task is None:
            issue = "Скопируйте строку выпущенного наряда из FixRate"
        elif not any(value[col] for col in "BCD"):
            issue = "Заполните новое начало, плановые часы или примечание"
        elif value["B"] and not re.fullmatch(r"20\d\d-\d\d-\d\d[T ]\d\d:\d\d(?::00)?", value["B"]):
            issue = "Укажите местные дату и время, например 2027-01-02T10:00"
        values = {name: value[col] for name, col in zip(("planned_start", "planned_person_hours", "note"), "BCD")
                  if value[col]}
        if "planned_person_hours" in values:
            values["planned_person_hours"] = values["planned_person_hours"].replace(",", ".")
        if values.get("note") == "—":
            values["note"] = ""
        rows.append(dict(row_number=number, task_id=task, values=values, issue=issue))
    counts = Counter(row["task_id"] for row in rows if row["task_id"] is not None)
    for row in rows:
        if counts[row["task_id"]] > 1:
            row["issue"] = "Наряд указан несколько раз; оставьте одну строку"
    return True, rows, None


def _read(v, book_id, version, row_number):
    book = read_version(v, book_id, version, include_content=True)
    _, rows, issue = _rows(bytes(book["content"]))
    row = next((row for row in rows if row["row_number"] == row_number), None)
    if issue or row is None or row["issue"]:
        raise HTTPException(422, issue or (row["issue"] if row else "На указанной строке листа «Изменения нарядов» нет правок"))
    task = row["task_id"]
    order = v.task(task)
    try:
        change = ExistingRow(kind="existing", task_id=task, expected_revision=order.revision, **row["values"])
    except ValidationError:
        raise HTTPException(422, "Проверьте время (ГГГГ-ММ-ДДTчч:мм), плановые часы и примечание (до 500 символов).") from None
    return change, dict(book_id=str(book_id), version=version, sha256=book["sha256"], sheet=SHEET, row_number=row_number)


def register_routes(app, views):
    @app.get(ISSUED_ORDERS)
    def issued_orders(response: Response, q: str = Query("", max_length=120),
                      offset: int = Query(0, ge=0, le=1_000_000), v=Depends(views)):
        require_editor(v)
        result = v.session.execute(text("""
            SELECT o.work_order_id AS task_id, o.operation_snapshot->>'title' AS title,
                   o.planned_start_at, e.asset_code AS asset_code
            FROM published_catalog_tasks p JOIN work_orders o USING(site_id,work_order_id)
            LEFT JOIN schedule_entries s USING (site_id,schedule_entry_id)
            LEFT JOIN rule_equipment b ON b.site_id=s.site_id AND b.binding_id=s.binding_id
            LEFT JOIN equipment e ON e.site_id=b.site_id AND e.equipment_id=b.equipment_id
            WHERE o.site_id=:site AND o.status IN ('draft','assigned')
              AND o.started_at IS NULL AND o.regulatory_deadline_at>now() AND s.status='planned'
              AND NOT EXISTS (SELECT 1 FROM work_reports r WHERE r.site_id=o.site_id AND r.work_order_id=o.work_order_id)
              AND (:q='' OR strpos(lower(concat_ws(' ',o.work_order_id::text,o.operation_snapshot->>'title',e.asset_code,e.name)),:q)>0)
            ORDER BY o.planned_start_at NULLS LAST,o.work_order_id LIMIT :limit OFFSET :offset
        """), dict(site=v.principal.site_id, q=q.strip().lower(), offset=offset, limit=PAGE + 1)).mappings().all()
        response.headers.update(CACHE)
        return dict(items=[dict(row) for row in result[:PAGE]], has_more=len(result)>PAGE)

    @app.get(ORDER_CHANGES)
    def candidate_rows(book_id: UUID, response: Response,
                       version: int = Path(ge=1, le=2_147_483_647),
                       offset: int = Query(0, ge=0, le=1_000_000), v=Depends(views)):
        require_editor(v)
        book = read_version(v, book_id, version, include_content=True)
        present, rows, issue = _rows(bytes(book["content"]))
        page = rows[offset:offset+PAGE]
        identities = list({row["task_id"] for row in page if row["task_id"]})
        found = v.session.execute(text("""
            SELECT o.work_order_id, o.operation_snapshot->>'title' AS title, o.status, o.started_at,
                o.regulatory_deadline_at>now() AS before_deadline,
                EXISTS (SELECT 1 FROM work_reports r WHERE r.site_id=o.site_id AND r.work_order_id=o.work_order_id) AS has_report
            FROM published_catalog_tasks p JOIN work_orders o USING (site_id,work_order_id)
            WHERE p.site_id=:site AND p.work_order_id=ANY(:ids)
        """), dict(site=v.principal.site_id, ids=identities)).mappings() if identities else []
        existing = {row["work_order_id"]: row for row in found}
        items = []
        for row in page:
            order = existing.get(row["task_id"])
            row_issue = row["issue"]
            if not row_issue:
                if order is None:
                    row_issue = "Выпущенный наряд не найден на текущем объекте"
                elif order["status"] not in ("assigned", "draft") or order["started_at"] or order["has_report"]:
                    row_issue = "Работа уже начата, закрыта или имеет отчёт"
                elif not order["before_deadline"]:
                    row_issue = "У наряда нет будущего подтверждённого срока"
            items.append(dict(row_number=row["row_number"], task_id=row["task_id"] if order else None,
                              title=order["title"] if order else None, issue=row_issue))
        response.headers.update(CACHE)
        return dict(items=items, total=len(rows), has_sheet=present, issue=issue)

    @app.post(ORDER_CHANGES + "/preview")
    def preview(book_id: UUID, command: WorkbookPreview, response: Response,
                version: int = Path(ge=1, le=2_147_483_647), v=Depends(views)):
        require_editor(v)
        response.headers.update(CACHE)
        change, source = _read(v, book_id, version, command.row_number)
        return _plan(v, Preview(changes=[change], reason=command.reason), workbook_source=source)[1]

    @app.post(ORDER_CHANGES + "/apply")
    def apply(book_id: UUID, command: WorkbookApply, response: Response,
              version: int = Path(ge=1, le=2_147_483_647), v=Depends(views)):
        require_editor(v)
        response.headers.update(CACHE)
        change, source = _read(v, book_id, version, command.row_number)
        payload = command.model_dump(exclude={"row_number"})
        return _apply(v, Apply(changes=[change], **payload), workbook_source=source, workbook_request=command.model_dump(mode="json"))
