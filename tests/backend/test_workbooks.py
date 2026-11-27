from contextlib import closing
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest
from sqlalchemy import text

from app.catalog_excel import MAX_FILE, write_workbook
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import PREFIX, login, runtime
from tests.fixtures.catalog_source import catalog_book


BASE = PREFIX + "/workbooks"
CATALOG = PREFIX + "/catalog-imports"
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def workbook_site(managed):
    engine, _, _, _, ids = managed
    try:
        yield managed
    finally:
        with engine.begin() as conn:
            if conn.scalar(text("SELECT to_regclass('source_workbooks')")) is not None:
                conn.execute(text("DELETE FROM source_workbooks WHERE site_id=:site"), ids)


def upload(client, blob, filename="Регламент.xlsx"):
    return client.post(BASE, files={"file": (filename, blob, MIME)})


def test_original_is_immutable_and_scoped(workbook_site):
    _, app, admin, _, _ = workbook_site
    chief = admin.chief
    content = write_workbook({"Январь": [["Операция", 12]], "Сводка": [["Всего", 12]]})
    original = upload(chief, content)
    assert original.status_code == 201, original.text
    saved = original.json()
    identity = saved["book_id"]
    assert saved["version"] == 1 and saved["sha256"] == sha256(content).hexdigest()
    duplicate = upload(chief, content)
    assert duplicate.status_code == 200 and duplicate.json() == saved

    listing = chief.get(BASE)
    assert listing.headers["cache-control"] == "private, no-store"
    assert listing.json() == {"items": [saved], "total": 1}
    assert chief.get(f"{BASE}/{identity}/versions").json() == {"items": [saved], "total": 1}
    download = chief.get(f"{BASE}/{identity}/versions/1/xlsx")
    assert download.status_code == 200 and download.content == content
    assert download.headers["content-type"] == MIME
    assert chief.get(f"{BASE}/{identity}/versions/2/xlsx").status_code == 404
    assert upload(admin, content).status_code == 403
    with closing(login(app, "chief_engineer")) as other:
        assert other.get(f"{BASE}/{identity}/versions").status_code == 404
        assert other.get(f"{BASE}/{identity}/versions/1/xlsx").status_code == 404
    with closing(login(app, "executor")) as worker:
        assert worker.get(BASE).status_code == 403
        assert upload(worker, content).status_code == 403


def test_explicit_catalog_import_uses_only_selected_version(workbook_site):
    engine, _, admin, _, ids = workbook_site
    chief = admin.chief
    book = upload(chief, catalog_book(2)).json()
    unsupported = upload(chief, write_workbook({"График": [["Смена", "Время"]]})).json()
    assert chief.get(CATALOG).json()["total"] == 0
    endpoint = f"{BASE}/{book['book_id']}/versions/1/catalog"
    first = chief.post(endpoint)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "draft" and first.json()["summary"]["operation_count"] == 2
    again = chief.post(endpoint)
    assert again.status_code == 200 and again.json()["import_id"] == first.json()["import_id"]
    assert chief.get(CATALOG).json()["total"] == 1
    imported = chief.post(f"{BASE}/from-catalog/{first.json()['import_id']}")
    assert imported.status_code == 200 and imported.json()["book_id"] == book["book_id"]
    assert chief.post(f"{BASE}/{unsupported['book_id']}/versions/1/catalog").status_code == 422
    assert chief.get(f"{BASE}/{unsupported['book_id']}/versions/1/xlsx").status_code == 200
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM work_orders WHERE site_id=:site"), ids) == 0


def test_unsupported_xlsx_is_rejected(workbook_site):
    _, _, admin, _, _ = workbook_site
    chief = admin.chief
    original = write_workbook({"Лист 1": [["Значение"]]})
    stream = BytesIO()
    with ZipFile(BytesIO(original)) as source, ZipFile(stream, "w") as output:
        for name in source.namelist():
            output.writestr(name, source.read(name))
        output.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")
    cases = (
        (original, "Workbook.xlsm", 422),
        (b"not a workbook", "Workbook.xlsx", 422),
        (stream.getvalue(), "Workbook.xlsx", 422),
        (b"0" * (MAX_FILE + 1), "Workbook.xlsx", 413),
    )
    for content, name, status_code in cases:
        assert upload(chief, content, name).status_code == status_code
    assert chief.get(BASE).json()["total"] == 0


def test_catalog_open_returns_latest_without_changing_original(workbook_site):
    engine, _, admin, _, ids = workbook_site
    chief = admin.chief
    original = catalog_book(2)
    book = upload(chief, original).json()
    catalog = chief.post(f"{BASE}/{book['book_id']}/versions/1/catalog").json()
    revised = write_workbook({"Сводка": [["Контроль", 12]]})
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO source_workbook_versions(site_id,book_id,version,sha256,content,created_by)
            VALUES (:site,:book,2,:sha,:content,:author)
        """), dict(site=ids["site"],book=book["book_id"],sha=sha256(revised).hexdigest(),
                   content=revised,author=book["created_by"]))

    path = f"{BASE}/from-catalog/{catalog['import_id']}"
    latest = chief.post(path)
    assert latest.status_code == 200 and latest.json()["version"] == 2
    assert latest.json()["book_id"] == book["book_id"]
    assert chief.get(f"{BASE}/{book['book_id']}/versions/1/xlsx").content == original


def test_workbook_editor_detaches_connections_without_editing_original(workbook_site):
    from app.workbooks import editor_workbook

    _, _, admin, _, _ = workbook_site
    chief = admin.chief
    original = write_workbook({"Лист 1": [["Значение", 1]]})
    stream = BytesIO()
    with ZipFile(BytesIO(original)) as source, ZipFile(stream, "w") as output:
        for name in source.namelist():
            data = source.read(name)
            if name == "xl/_rels/workbook.xml.rels":
                data = data.replace(b"</Relationships>",
                    b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/connections" Target="connections.xml" /></Relationships>')
            if name == "[Content_Types].xml":
                data = data.replace(b"</Types>",
                    b'<Override PartName="/xl/connections.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.connections+xml" /></Types>')
            output.writestr(name, data)
        output.writestr("xl/connections.xml", "<connections><connection><dbPr connection='SYNTHETIC'/></connection></connections>")
    book = stream.getvalue()
    response = upload(chief, book)
    assert response.status_code == 201, response.text
    path = f"{BASE}/{response.json()['book_id']}/versions/1/xlsx"
    assert chief.get(path).content == book
    copy = editor_workbook(book)
    with ZipFile(BytesIO(copy)) as package:
        assert "xl/connections.xml" not in package.namelist()
        assert b"connections.xml" not in package.read("[Content_Types].xml")
        assert b"connections.xml" not in package.read("xl/_rels/workbook.xml.rels")
    assert chief.get(path).content == book
