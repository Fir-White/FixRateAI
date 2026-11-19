"""Customer XLSX preview/import boundary for CR-17."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from uuid import UUID, uuid4
from xml.etree import ElementTree
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile
from sqlalchemy import text


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SUPPORTED_SHEETS = {"Лист1", "Sheet1"}


@dataclass(frozen=True)
class SourceRow:
    row_number: int
    code: str
    title: str
    maintenance_type: str
    frequency: str
    norm_hours: Decimal | None
    required_people: int
    source_ref: str
    extra: dict[str, str]


@dataclass(frozen=True)
class SourceWorkbook:
    content_sha256: str
    sheet: str
    rows: tuple[SourceRow, ...]


def _column_reference(reference: str) -> str:
    return "".join(character for character in reference if character.isalpha())


def _read_cell(cell, shared_strings: list[str]) -> str:
    if cell.find("x:f", NS) is not None:
        raise ValueError("Формулы в исходном XLSX не поддерживаются")
    value = cell.find("x:v", NS)
    if value is None:
        inline = cell.find("x:is/x:t", NS)
        return inline.text or "" if inline is not None else ""
    raw = value.text or ""
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(raw)]
        except (IndexError, ValueError):
            raise ValueError("Повреждённая таблица shared strings") from None
    return raw


def parse_workbook(data: bytes) -> SourceWorkbook:
    digest = sha256(data).hexdigest()
    try:
        with ZipFile(BytesIO(data)) as archive:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            strings_data = archive.read("xl/sharedStrings.xml") if "xl/sharedStrings.xml" in archive.namelist() else b""
            strings_root = ElementTree.fromstring(strings_data) if strings_data else None
            sheet_root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError("Нужен корректный XLSX-файл") from exc

    sheets = workbook.findall("x:sheets/x:sheet", NS)
    sheet_name = sheets[0].attrib.get("name", "") if sheets else ""
    if sheet_name not in SUPPORTED_SHEETS:
        raise ValueError("Поддерживается только лист Лист1")

    shared_strings = (
        ["".join(node.itertext()) for node in strings_root.findall("x:si", NS)]
        if strings_root is not None
        else []
    )
    parsed: list[SourceRow] = []
    for row in sheet_root.findall("x:sheetData/x:row", NS):
        number = int(row.attrib["r"])
        if number < 6:
            continue
        values = {
            _column_reference(cell.attrib.get("r", "")): _read_cell(cell, shared_strings)
            for cell in row.findall("x:c", NS)
        }
        code = values.get("A", "").strip()
        if not code:
            continue
        title = values.get("B", "").strip()
        maintenance_type = values.get("C", "").strip()
        frequency = values.get("D", "").strip()
        try:
            norm_hours = Decimal(values["E"]) if values.get("E", "").strip() else None
        except InvalidOperation:
            raise ValueError(f"Строка {number}: некорректная норма часов") from None
        try:
            required_people = int(Decimal(values.get("F", "0")))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Строка {number}: некорректное количество людей") from None
        if not title or maintenance_type not in {"ТО1", "ТО2"} or required_people < 1:
            raise ValueError(f"Строка {number}: заполнены не все обязательные поля")
        extra = {
            key: value
            for key, value in values.items()
            if key not in {"A", "B", "C", "D", "E", "F"} and value
        }
        parsed.append(SourceRow(
            number, code, title, maintenance_type, frequency, norm_hours,
            required_people, f"{sheet_name}!A{number}:F{number}", extra,
        ))
    if not parsed:
        raise ValueError("В XLSX не найдено ни одной строки каталога")
    return SourceWorkbook(digest, sheet_name, tuple(parsed))


def preview(workbook: SourceWorkbook) -> dict:
    return {
        "sourceSha256": workbook.content_sha256,
        "sheet": workbook.sheet,
        "rowCount": len(workbook.rows),
        "rows": [
            {
                "row": row.row_number,
                "code": row.code,
                "title": row.title,
                "maintenanceType": row.maintenance_type,
                "frequency": row.frequency,
                "normHours": str(row.norm_hours) if row.norm_hours is not None else None,
                "requiredPeople": row.required_people,
                "sourceRef": row.source_ref,
                "unknown": row.extra,
            }
            for row in workbook.rows
        ],
    }


def export_workbook(source_rows: dict) -> bytes:
    rows = source_rows["rows"]
    columns = ["A", "B", "C", "D", "E", "F"]
    unknown_columns = sorted({
        column for row in rows for column in row.get("unknown", {})
    })
    columns.extend(unknown_columns)

    def cell(column: str, row_number: int, value: object) -> str:
        text = escape(str(value if value is not None else ""))
        return f'<c r="{column}{row_number}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'

    sheet_rows = [f'<row r="{row_number}"></row>' for row_number in range(1, 6)]
    for index, row in enumerate(rows, 6):
        values = [
            row["code"], row["title"], row["maintenanceType"], row["frequency"],
            row["normHours"], row["requiredPeople"],
        ]
        values.extend(row.get("unknown", {}).get(column, "") for column in unknown_columns)
        sheet_rows.append(
            f'<row r="{index}">'
            + "".join(cell(column, index, value) for column, value in zip(columns, values))
            + "</row>"
        )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>" + "".join(sheet_rows) + "</sheetData></worksheet>"
    )
    files = {
        "[Content_Types].xml":
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        "_rels/.rels":
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        "xl/workbook.xml":
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Лист1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels":
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        "xl/worksheets/sheet1.xml": sheet,
    }
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content.encode())
    return data.getvalue()


def _frequency(value: str) -> tuple[str, int, int]:
    normalized = value.lower().replace(" ", "")
    if normalized == "1/день":
        return "day", 1, 1
    if normalized == "1/квар":
        return "quarter", 1, 1
    if normalized.endswith("/год") and normalized[:-4].isdigit():
        return "year", 1, int(normalized[:-4])
    raise ValueError(f"Неподдержанная периодичность: {value}")


async def read_upload(upload: UploadFile) -> tuple[bytes, SourceWorkbook]:
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "Загрузите XLSX-файл")
    data = await upload.read(10_485_761)
    if len(data) > 10_485_760:
        raise HTTPException(422, "XLSX-файл слишком большой")
    try:
        return data, parse_workbook(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def enqueue_revision(session, *, site_id: UUID, actor_id: UUID, scope: str,
                     source_revision: int, source_sha256: str | None,
                     entity_type: str, entity_id: UUID | None,
                     change_type: str, payload: dict) -> UUID:
    event_id = uuid4()
    session.execute(text("""
        INSERT INTO source_revision_events
            (event_id,site_id,scope,source_revision,source_sha256,
             entity_type,entity_id,change_type,payload)
        VALUES (:event,:site,:scope,:revision,:sha,:entity,:entity_id,:change,
                CAST(:payload AS jsonb))
        ON CONFLICT (site_id,scope,source_revision,entity_type,entity_id)
        DO NOTHING
    """), {
        "event": event_id, "site": site_id, "scope": scope,
        "revision": source_revision, "sha": source_sha256,
        "entity": entity_type, "entity_id": entity_id, "change": change_type,
        "payload": json.dumps({
            "actor_user_id": str(actor_id),
            "revision": source_revision,
            **payload,
        }, ensure_ascii=False),
    })
    return event_id


def next_revision(session, *, site_id: UUID, scope: str) -> int:
    return session.execute(text("""
        SELECT COALESCE(MAX(source_revision), 0) + 1
        FROM source_revision_events
        WHERE site_id=:site AND scope=:scope
    """), {"site": site_id, "scope": scope}).scalar_one()


def import_workbook(session, principal, workbook: SourceWorkbook, system_id: UUID,
                    effective_from: date, source_name: str):
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": f"source-xlsx:{principal.site_id}"})
    existing = session.execute(text("""
        SELECT source_import_id, source_revision, row_count
        FROM source_imports
        WHERE site_id=:site AND source_sha256=:sha
    """), {"site": principal.site_id, "sha": workbook.content_sha256}).mappings().first()
    if existing:
        return {
            "sourceImportId": str(existing["source_import_id"]),
            "sourceSha256": workbook.content_sha256,
            "sourceRevision": existing["source_revision"],
            "rowCount": existing["row_count"],
            "repeated": True,
        }

    system = session.execute(text("""
        SELECT system_id FROM engineering_systems
        WHERE site_id=:site AND system_id=:system AND is_active
        FOR SHARE
    """), {"site": principal.site_id, "system": system_id}).scalar()
    if system is None:
        raise HTTPException(404, "Инженерная система не найдена")

    source_revision = session.execute(text("""
        SELECT COALESCE(MAX(source_revision), 0) + 1
        FROM source_imports WHERE site_id=:site
    """), {"site": principal.site_id}).scalar_one()
    document_id = uuid4()
    import_id = uuid4()

    session.execute(text("""
        INSERT INTO source_imports
            (source_import_id,site_id,source_sha256,source_name,source_revision,
             status,row_count,source_rows,created_by)
        VALUES (:id,:site,:sha,:name,:revision,'imported',:count,
                CAST(:rows AS jsonb),:actor)
    """), {
        "id": import_id, "site": principal.site_id, "sha": workbook.content_sha256,
        "name": source_name[:512], "revision": source_revision,
        "count": len(workbook.rows),
        "rows": json.dumps(preview(workbook), ensure_ascii=False),
        "actor": principal.user_id,
    })
    session.execute(text("""
        INSERT INTO regulation_documents
            (regulation_document_id,site_id,title,source_kind,source_uri,external_reference)
        VALUES (:id,:site,:title,'customer',:uri,:sha)
    """), {
        "id": document_id, "site": principal.site_id, "title": source_name[:512],
        "uri": f"sha256:{workbook.content_sha256}", "sha": workbook.content_sha256,
    })
    edition_id = uuid4()
    session.execute(text("""
        INSERT INTO regulation_editions
            (regulation_edition_id,site_id,regulation_document_id,edition_code,
             effective_from,source_sha256)
        VALUES (:id,:site,:document,:code,:effective,:sha)
    """), {
        "id": edition_id, "site": principal.site_id, "document": document_id,
        "code": f"import-{source_revision}", "effective": effective_from,
        "sha": workbook.content_sha256,
    })

    for row in workbook.rows:
        period_unit, period_count, occurrences = _frequency(row.frequency)
        operation_id = session.execute(text("""
            INSERT INTO operation_templates
                (site_id,system_id,code,title,description,maintenance_type_id)
            SELECT :site,:system,:code,:title,:title,maintenance_type_id
            FROM maintenance_types WHERE name=:kind
            ON CONFLICT (site_id,system_id,code) DO UPDATE
                SET title=EXCLUDED.title, description=EXCLUDED.description
            RETURNING operation_template_id
        """), {
            "site": principal.site_id, "system": system_id,
            "code": row.code, "title": row.title, "kind": row.maintenance_type,
        }).scalar_one()
        version = session.execute(text("""
            SELECT COALESCE(MAX(rule_version), 0) + 1
            FROM maintenance_rules
            WHERE site_id=:site AND operation_template_id=:operation
        """), {"site": principal.site_id, "operation": operation_id}).scalar_one()
        session.execute(text("""
            INSERT INTO maintenance_rules
                (site_id,system_id,operation_template_id,regulation_edition_id,
                 rule_version,period_unit,period_count,occurrences_per_period,
                 scheduling_mode,source_text,source_ref,schedule_parameters,
                 required_people,norm_hours,norm_hours_basis,active_from,
                 publication_status,data_origin)
            VALUES (:site,:system,:operation,:edition,:version,:unit,:period,
                    :occurrences,'fixed_interval',:source_text,:source_ref,
                    CAST(:parameters AS jsonb),:people,:hours,'unknown',
                    :effective,'draft','customer')
        """), {
            "site": principal.site_id, "system": system_id,
            "operation": operation_id, "edition": edition_id,
            "version": version, "unit": period_unit, "period": period_count,
            "occurrences": occurrences, "source_text": row.frequency,
            "source_ref": f"{workbook.content_sha256}:{row.source_ref}",
            "parameters": json.dumps({
                "frequency": row.frequency,
                "source_sha256": workbook.content_sha256,
                "source_ref": row.source_ref,
                "unknown": row.extra,
            }, ensure_ascii=False),
            "people": row.required_people, "hours": row.norm_hours,
            "effective": effective_from,
        })

    session.execute(text("""
        INSERT INTO audit_events
            (site_id,actor_type,actor_user_id,entity_type,entity_id,
             action,after_snapshot)
        VALUES (:site,'user',:actor,'source_import',:id,
                'source_revision',CAST(:snapshot AS jsonb))
    """), {
        "site": principal.site_id, "actor": principal.user_id, "id": import_id,
        "snapshot": json.dumps({
            "source_sha256": workbook.content_sha256,
            "source_revision": source_revision,
            "scope": str(principal.site_id),
            "row_count": len(workbook.rows),
        }, ensure_ascii=False),
    })
    enqueue_revision(
        session, site_id=principal.site_id, actor_id=principal.user_id,
        scope="maintenance_catalog", source_revision=source_revision,
        source_sha256=workbook.content_sha256,
        entity_type="source_import", entity_id=import_id,
        change_type="source_revision",
        payload={"row_count": len(workbook.rows)},
    )
    return {
        "sourceImportId": str(import_id),
        "sourceSha256": workbook.content_sha256,
        "sourceRevision": source_revision,
        "rowCount": len(workbook.rows),
        "repeated": False,
    }
