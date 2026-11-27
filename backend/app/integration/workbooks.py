from hashlib import sha256
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Depends, File, Form, HTTPException, Path, Query, Response, UploadFile
from sqlalchemy import text

from app.catalog_excel import MAX_FILE
from app.schemas.catalog import CatalogSaved
from app.schemas.workbooks import WorkbookPage, WorkbookVersion
from app.security.permissions import permits
from app.workbooks import XLSX_MIME, validate_xlsx, workbook_filename
from .catalog_imports import inspect as inspect_catalog, persist_draft
from .management import PREFIX, _audit, _edit, _guard


BASE = PREFIX + "/workbooks"
CACHE = {"Cache-Control": "private, no-store"}
_FIELDS = "b.book_id,b.filename,w.version,w.sha256,w.size_bytes,w.created_by,w.created_at"


def require_editor(v):
    # MVP's shared preparation gate does not make a regular engineer the workbook owner/editor.
    if not permits(v.principal.role, "edit_source_workbook"):
        raise HTTPException(403, "Редактировать исходные книги может главный инженер.")


def _read_guard(v):
    _guard(v, "chief_engineer", "engineer", exact=True)


def _not_found():
    return HTTPException(404, "Исходная книга или версия не найдена.")


def read_version(v, book_id: UUID, version: int, *, include_content: bool = False) -> dict:
    fields = _FIELDS + (",w.content" if include_content else "")
    found = v.session.execute(text(f"""
        SELECT {fields} FROM source_workbooks b JOIN source_workbook_versions w USING(site_id,book_id)
        WHERE b.site_id=:site AND b.book_id=:book_id AND w.version=:version
    """), dict(site=v.principal.site_id, book_id=book_id, version=version)).mappings().first()
    if found is None:
        raise _not_found()
    return dict(found)


def _checked(filename: str, content: bytes) -> str:
    if len(content) > MAX_FILE:
        raise HTTPException(413, "Размер книги превышает 5 МиБ.")
    try:
        name = workbook_filename(filename)
        validate_xlsx(content)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return name


def lock_book(v, book_id):
    where = dict(site=v.principal.site_id, book=book_id)
    if v.session.scalar(text("""
        SELECT book_id FROM source_workbooks WHERE site_id=:site AND book_id=:book FOR UPDATE
    """), where) is None:
        raise _not_found()
    return v.session.scalar(text("""
        SELECT max(version) FROM source_workbook_versions WHERE site_id=:site AND book_id=:book
    """), where)


def append_version(v, book_id, current, content, checksum):
    """Append under the caller's authorized book lock."""
    original = read_version(v, book_id, current)
    if original["sha256"] == checksum:
        return original
    v.session.execute(text("""
        INSERT INTO source_workbook_versions(site_id,book_id,version,sha256,content,created_by)
        VALUES (:site,:book,:version,:sha,:content,:actor)
    """), dict(site=v.principal.site_id, book=book_id, version=current + 1, sha=checksum,
               content=content, actor=v.principal.user_id))
    _audit(v, "source_workbooks", book_id, "save_version",
           dict(version=current + 1, base_version=current, sha256=checksum))
    return read_version(v, book_id, current + 1)


def store_original(v, filename: str, content: bytes) -> tuple[dict, bool]:
    require_editor(v)
    name = _checked(filename, content)
    params = dict(site=v.principal.site_id, actor=v.principal.user_id, name=name, sha=sha256(content).hexdigest())
    with _edit(v, roles=("chief_engineer",), exact_roles=True, permission="edit_source_workbook"):
        book_id = v.session.scalar(text("""
            INSERT INTO source_workbooks (site_id,filename,original_sha256)
            VALUES (:site,:name,:sha)
            ON CONFLICT (site_id,original_sha256) DO NOTHING
            RETURNING book_id
        """), params)
        inserted = book_id is not None
        if inserted:
            v.session.execute(text("""
                INSERT INTO source_workbook_versions (site_id,book_id,version,sha256,content,created_by)
                VALUES (:site,:book_id,1,:sha,:content,:actor)
            """), dict(params, book_id=book_id, content=content))
            _audit(v, "source_workbooks", book_id, "upload", {"version": 1, "sha256": params["sha"]})
        else:
            book_id = v.session.scalar(text("""
                SELECT book_id FROM source_workbooks WHERE site_id=:site AND original_sha256=:sha
            """), params)
        return read_version(v, book_id, 1), inserted


def register_routes(app, views):
    @app.get(BASE, response_model=WorkbookPage)
    def list_workbooks(response: Response, offset: int = Query(0, ge=0, le=1_000_000), v=Depends(views)):
        _read_guard(v)
        response.headers.update(CACHE)
        params = dict(site=v.principal.site_id, offset=offset)
        items = v.session.execute(text(f"""
            SELECT {_FIELDS}
            FROM (SELECT * FROM source_workbooks WHERE site_id=:site
                  ORDER BY created_at DESC,book_id LIMIT 25 OFFSET :offset) b
            JOIN LATERAL (SELECT version,sha256,size_bytes,created_by,created_at FROM source_workbook_versions
                          WHERE site_id=b.site_id AND book_id=b.book_id ORDER BY version DESC LIMIT 1) w ON true
            ORDER BY b.created_at DESC,b.book_id
        """), params).mappings().all()
        total = v.session.scalar(text("SELECT count(*) FROM source_workbooks WHERE site_id=:site"), params)
        return dict(items=[dict(row) for row in items], total=total)

    @app.post(BASE, status_code=201, response_model=WorkbookVersion)
    def upload_workbook(response: Response, file: UploadFile = File(...), v=Depends(views)):
        require_editor(v)
        result, inserted = store_original(v, file.filename or "", file.file.read(MAX_FILE + 1))
        response.headers.update(CACHE)
        if not inserted:
            response.status_code = 200
        return result

    @app.post(BASE + "/from-catalog/{catalog_id}", status_code=201, response_model=WorkbookVersion)
    def open_catalog(catalog_id: UUID, response: Response, v=Depends(views)):
        require_editor(v)
        found = v.session.execute(text("""
            SELECT filename,source_file FROM regulation_catalog_imports
            WHERE site_id=:site AND import_id=:catalog_id
        """), dict(site=v.principal.site_id, catalog_id=catalog_id)).mappings().first()
        if found is None:
            raise HTTPException(404, "Каталог не найден.")
        result, inserted = store_original(v, found["filename"], bytes(found["source_file"]))
        response.headers.update(CACHE)
        if not inserted:
            response.status_code = 200
            latest = v.session.scalar(text("""
                SELECT max(version) FROM source_workbook_versions WHERE site_id=:site AND book_id=:book
            """), dict(site=v.principal.site_id, book=result["book_id"]))
            return read_version(v, result["book_id"], latest)
        return result

    @app.get(BASE + "/{book_id}/versions", response_model=WorkbookPage)
    def list_versions(book_id: UUID, response: Response, offset: int = Query(0, ge=0, le=1_000_000), v=Depends(views)):
        _read_guard(v)
        response.headers.update(CACHE)
        params = dict(site=v.principal.site_id, book_id=book_id, offset=offset)
        total = v.session.scalar(text("""
            SELECT count(*) FROM source_workbook_versions WHERE site_id=:site AND book_id=:book_id
        """), params)
        if not total:
            raise _not_found()
        items = v.session.execute(text(f"""
            SELECT {_FIELDS} FROM source_workbooks b JOIN source_workbook_versions w USING(site_id,book_id)
            WHERE b.site_id=:site AND b.book_id=:book_id ORDER BY w.version DESC LIMIT 25 OFFSET :offset
        """), params).mappings().all()
        return dict(items=[dict(row) for row in items], total=total)

    @app.post(BASE + "/{book_id}/versions/from-file", status_code=201, response_model=WorkbookVersion)
    def append_file(book_id: UUID, response: Response, file: UploadFile = File(...),
                    expected_version: int = Form(ge=1, le=2_147_483_647),
                    idempotency_key: UUID = Form(...), v=Depends(views)):
        require_editor(v)
        content = file.file.read(MAX_FILE + 1)
        _checked(file.filename or "", content)
        checksum = sha256(content).hexdigest()
        response.headers.update(CACHE)
        intent = dict(base_version=expected_version, sha256=checksum)
        identity = uuid5(NAMESPACE_URL, f"fixrate:workbook-file:{v.principal.site_id}:{v.principal.user_id}:{book_id}:{idempotency_key}")
        with _edit(v, roles=("chief_engineer",), exact_roles=True, permission="edit_source_workbook"):
            current = lock_book(v, book_id)
            previous = v.rows("audit_events", audit_event_id=identity)
            if previous:
                event = previous[0].after_snapshot
                if event["intent"] != intent:
                    raise HTTPException(409, "Ключ повторной записи использован с другим файлом или версией.")
                response.status_code = 200
                return read_version(v, book_id, event["version"])
            if current != expected_version:
                raise HTTPException(409, "Версия книги уже изменилась. Проверьте последнюю версию.")
            result = append_version(v, book_id, current, content, checksum)
            if result["version"] == current:
                response.status_code = 200
            v.repo.add("audit_events", audit_event_id=identity, site_id=v.principal.site_id, actor_type="user",
                       actor_user_id=v.principal.user_id, entity_type="source_workbooks", entity_id=book_id,
                       action="save_from_file", after_snapshot=dict(intent=intent, version=result["version"]))
            return result

    @app.get(BASE + "/{book_id}/versions/{version}/xlsx")
    def download_workbook(book_id: UUID, version: int = Path(ge=1, le=2_147_483_647), v=Depends(views)):
        _read_guard(v)
        row = read_version(v, book_id, version, include_content=True)
        filename = row["filename"] if version == 1 else f"{row['filename'][:-5]}-v{version}.xlsx"
        return Response(bytes(row["content"]), media_type=XLSX_MIME, headers={
            **CACHE, "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"""attachment; filename="workbook.xlsx"; filename*=UTF-8''{quote(filename, safe="")}""",
        })

    @app.get(BASE + "/{book_id}/versions/{version}", response_model=WorkbookVersion)
    def version_details(book_id: UUID, response: Response, version: int = Path(ge=1, le=2_147_483_647), v=Depends(views)):
        _read_guard(v)
        response.headers.update(CACHE)
        return read_version(v, book_id, version)

    @app.post(BASE + "/{book_id}/versions/{version}/catalog", status_code=201, response_model=CatalogSaved)
    def catalog_from_version(book_id: UUID, response: Response, version: int = Path(ge=1, le=2_147_483_647), v=Depends(views)):
        require_editor(v)
        row = read_version(v, book_id, version, include_content=True)
        content = bytes(row["content"])
        data = inspect_catalog(content)
        with _edit(v, roles=("chief_engineer",), exact_roles=True, permission="edit_source_workbook"):
            result = persist_draft(v, row["filename"], content, data)
        response.headers.update(CACHE)
        if result["already_saved"]:
            response.status_code = 200
        return result
