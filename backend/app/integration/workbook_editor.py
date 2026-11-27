from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request, Response
import httpx
from sqlalchemy import text

from app.onlyoffice import OfficeCommandRejected, OfficeSettings, fetch_snapshot, request_forcesave, sign_office_token, signed_payload
from app.schemas.workbooks import EditorCommit, EditorInput, EditorSession, EditorSnapshot, EditorStatus, WorkbookVersion
from app.security.sessions import role_is_enabled
from app.workbooks import XLSX_MIME, editor_workbook, has_connections, validate_xlsx
from .management import _edit
from .workbooks import BASE, CACHE, append_version, lock_book, read_version, require_editor


INTERNAL = "/api/internal/workbook-editor"
PENDING_TIMEOUT = timedelta(seconds=45)
SESSION_DURATION = timedelta(hours=2)
_STATUS = "session_id,base_version,state,snapshot_request_id,snapshot_sha256,expires_at"


def _config() -> OfficeSettings:
    try:
        settings = OfficeSettings.configured()
    except ValueError:
        settings = None
    if settings is None:
        raise HTTPException(503, "Локальный редактор Excel не настроен. Книгу можно скачать.")
    return settings


def _now():
    return datetime.now(timezone.utc)


def _owner_session(v, book_id, identity, *, lock=False, include_snapshot=False):
    fields = _STATUS + ",snapshot_requested_at,commit_key,committed_version"
    if include_snapshot:
        fields += ",snapshot"
    stmt = f"""SELECT {fields} FROM source_workbook_editor_sessions
        WHERE site_id=:site AND book_id=:book AND session_id=:id AND user_id=:user"""
    row = v.session.execute(text(stmt + (" FOR UPDATE" if lock else "")),
                            dict(site=v.principal.site_id, book=book_id, id=identity, user=v.principal.user_id)).mappings().first()
    if row is None:
        raise HTTPException(404, "Сессия редактирования не найдена.")
    if row["expires_at"] <= _now() and row["state"] != "saved":
        raise HTTPException(409, "Сессия редактирования истекла. Откройте книгу заново.")
    return dict(row)


def _service_session(db, identity):
    if not role_is_enabled("chief_engineer"):
        raise HTTPException(403, "Недоступна роль редактора Excel.")
    row = db.execute(text("""
        SELECT e.site_id,e.book_id,e.base_version,e.session_id,e.state,e.snapshot_request_id
        FROM source_workbook_editor_sessions e
        JOIN sites s ON s.site_id=e.site_id AND s.is_active
        JOIN site_memberships m ON m.site_id=e.site_id AND m.user_id=e.user_id
                                 AND m.is_active AND m.role='chief_engineer'
        JOIN users u ON u.user_id=e.user_id AND u.is_active
        WHERE e.session_id=:id AND e.expires_at > now()
    """), dict(id=identity)).mappings().first()
    if row is None:
        raise HTTPException(404, "Сессия редактора не найдена или недоступна.")
    return row


def _office_claims(request, settings, operation):
    try:
        return signed_payload(settings, request.headers.get("authorization", ""), operation)
    except (ValueError, TypeError):
        raise HTTPException(403, "Не удалось подтвердить запрос локального редактора.") from None


def register_routes(app, views, db):
    editor_path = BASE + "/{book_id}/editor-sessions"

    @app.post(editor_path, status_code=201, response_model=EditorSession)
    def start(book_id: UUID, command: EditorInput, response: Response, v=Depends(views)):
        require_editor(v)
        settings = _config()
        with _edit(v, roles=("chief_engineer",), exact_roles=True, permission="edit_source_workbook"):
            if lock_book(v, book_id) != command.expected_version:
                raise HTTPException(409, "Версия книги уже изменилась. Откройте последнюю версию.")
            book = read_version(v, book_id, command.expected_version, include_content=True)
            params = dict(site=v.principal.site_id, book=book_id, version=command.expected_version, user=v.principal.user_id)
            existing = v.session.execute(text(f"""
                SELECT {_STATUS},user_id FROM source_workbook_editor_sessions
                WHERE site_id=:site AND book_id=:book AND base_version=:version AND state<>'saved' AND expires_at>now()
                ORDER BY created_at DESC LIMIT 1
            """), params).mappings().first()
            if existing and existing["user_id"] != v.principal.user_id:
                raise HTTPException(409, "Книга уже открыта на редактирование другим инженером.")
            if existing:
                session = dict(existing)
            else:
                session = dict(v.session.execute(text(f"""
                    INSERT INTO source_workbook_editor_sessions (site_id,book_id,base_version,user_id,expires_at)
                    VALUES (:site,:book,:version,:user,:expires) RETURNING {_STATUS}
                """), dict(params, expires=_now() + SESSION_DURATION)).mappings().one())
        private = f"{settings.callback_origin}{INTERNAL}/{session['session_id']}"
        config = dict(
            documentType="cell", type="desktop", width="100%", height="100%", title="Редактор Excel",
            document=dict(fileType="xlsx", key=str(session["session_id"]), title=book["filename"],
                          url=private + "/xlsx", permissions=dict(edit=True, print=False, review=False)),
            editorConfig=dict(
                mode="edit", lang="ru", callbackUrl=private + "/callback",
                user=dict(id=str(v.principal.user_id), name=v.principal.name),
                coEditing=dict(mode="fast", change=False),
                customization=dict(autosave=True, forcesave=False, macros=False, plugins=False, chat=False),
            ),
        )
        config["token"] = sign_office_token(settings.secret, config)
        response.headers.update(CACHE)
        return dict(session, api_url=settings.browser_origin + "/web-apps/apps/api/documents/api.js",
                    document_config=config, detached_connections=has_connections(bytes(book["content"])))

    @app.get(editor_path + "/{session_id}", response_model=EditorStatus)
    def status(book_id: UUID, session_id: UUID, response: Response, v=Depends(views)):
        require_editor(v)
        row = _owner_session(v, book_id, session_id)
        if row["state"] == "pending" and row["snapshot_requested_at"] < _now() - PENDING_TIMEOUT:
            row["state"] = "failed"
        response.headers.update(CACHE)
        return row

    @app.post(editor_path + "/{session_id}/snapshot", status_code=202, response_model=EditorStatus)
    def snapshot(book_id: UUID, session_id: UUID, command: EditorSnapshot, response: Response, v=Depends(views)):
        require_editor(v)
        settings = _config()
        where = dict(id=session_id, request_id=command.request_id)
        response.headers.update(CACHE)
        with _edit(v, roles=("chief_engineer",), exact_roles=True, permission="edit_source_workbook"):
            row = _owner_session(v, book_id, session_id, lock=True)
            if row["state"] == "saved":
                raise HTTPException(409, "Версия уже сохранена. Откройте новую версию для продолжения.")
            expired = row["state"] == "pending" and row["snapshot_requested_at"] <= _now() - PENDING_TIMEOUT
            if row["snapshot_request_id"] == command.request_id:
                if expired:
                    row["state"] = "failed"
                return row
            if row["state"] == "ready" or (row["state"] == "pending" and not expired):
                raise HTTPException(409, "Снимок уже запрошен в другой вкладке. Переоткройте редактор, чтобы завершить сохранение.")
            row = dict(v.session.execute(text(f"""
                UPDATE source_workbook_editor_sessions
                SET state='pending',snapshot_requested_at=now(),snapshot_request_id=:request_id,
                    snapshot_sha256=NULL,snapshot=NULL WHERE session_id=:id RETURNING {_STATUS}
            """), where).mappings().one())
        try:
            requested = request_forcesave(settings, str(session_id), str(where["request_id"]))
        except OfficeCommandRejected:
            state = "failed"
        except (httpx.HTTPError, ValueError):
            # An accepted command can still deliver a signed callback when its reply is lost.
            state = None
        else:
            state = None if requested else "unchanged"
        if state:
            with _edit(v, roles=("chief_engineer",), exact_roles=True, permission="edit_source_workbook"):
                v.session.execute(text("""
                    UPDATE source_workbook_editor_sessions SET state=:state
                    WHERE session_id=:id AND snapshot_request_id=:request_id AND state='pending'
                """), dict(where, state=state))
                row = _owner_session(v, book_id, session_id)
        return row

    @app.post(BASE + "/{book_id}/versions", status_code=201, response_model=WorkbookVersion)
    def commit(book_id: UUID, command: EditorCommit, response: Response, v=Depends(views)):
        require_editor(v)
        response.headers.update(CACHE)
        with _edit(v, roles=("chief_engineer",), exact_roles=True, permission="edit_source_workbook"):
            current = lock_book(v, book_id)
            session = _owner_session(v, book_id, command.session_id, lock=True, include_snapshot=True)
            if session["base_version"] != command.expected_version:
                raise HTTPException(409, "Сессия не соответствует версии книги.")
            if session["state"] == "saved":
                previous = read_version(v, book_id, session["committed_version"])
                if session["commit_key"] != command.idempotency_key or previous["sha256"] != command.snapshot_sha256:
                    raise HTTPException(409, "Изменения этой сессии уже сохранены.")
                response.status_code = 200
                return previous
            if current != command.expected_version:
                raise HTTPException(409, "Версия книги уже изменилась. Сохранение не выполнено.")
            if session["state"] != "ready" or session["snapshot_sha256"] != command.snapshot_sha256:
                raise HTTPException(409, "Снимок редактора не готов или изменился.")
            result = append_version(v, book_id, current, bytes(session["snapshot"]), command.snapshot_sha256)
            if result["version"] == current:
                v.session.execute(text("""
                    UPDATE source_workbook_editor_sessions SET state='unchanged',snapshot=NULL,snapshot_sha256=NULL WHERE session_id=:id
                """), dict(id=command.session_id))
                response.status_code = 200
                return result
            v.session.execute(text("""
                UPDATE source_workbook_editor_sessions SET state='saved',commit_key=:key,committed_version=:version,
                    snapshot=NULL,snapshot_sha256=NULL WHERE session_id=:id
            """), dict(key=command.idempotency_key, version=result["version"], id=command.session_id))
            return result

    @app.get(INTERNAL + "/{session_id}/xlsx", include_in_schema=False)
    def editor_source(session_id: UUID, request: Request, session=Depends(db)):
        settings = _config()
        payload = _office_claims(request, settings, "download")
        if payload.get("url") != f"{settings.callback_origin}{INTERNAL}/{session_id}/xlsx":
            raise HTTPException(403, "Запрос не относится к этой сессии редактора.")
        row = _service_session(session, session_id)
        if row["state"] == "saved":
            raise HTTPException(409, "Сессия редактирования завершена.")
        content = session.scalar(text("""
            SELECT content FROM source_workbook_versions WHERE site_id=:site AND book_id=:book AND version=:version
        """), dict(site=row["site_id"], book=row["book_id"], version=row["base_version"]))
        return Response(editor_workbook(bytes(content)), media_type=XLSX_MIME,
                        headers={**CACHE, "X-Content-Type-Options": "nosniff"})

    @app.post(INTERNAL + "/{session_id}/callback", include_in_schema=False)
    def editor_callback(session_id: UUID, payload: dict, request: Request, session=Depends(db)):
        settings = _config()
        signed = _office_claims(request, settings, "callback")
        if (any(payload.get(k) != signed.get(k) for k in ("status", "key", "url", "userdata"))
                or signed.get("key") != str(session_id) or type(signed.get("status")) is not int):
            raise HTTPException(403, "Обратный вызов не соответствует подписанной сессии.")
        row = _service_session(session, session_id)
        if signed["status"] not in (6, 7):
            return {"error": 0}
        if not row["snapshot_request_id"] or str(row["snapshot_request_id"]) != signed.get("userdata"):
            return {"error": 0}
        if row["state"] != "pending":
            return {"error": 0}
        params = dict(id=session_id, request_id=row["snapshot_request_id"])
        try:
            if signed["status"] != 6 or not isinstance(signed.get("url"), str):
                raise ValueError("ONLYOFFICE did not return the requested snapshot")
            content = fetch_snapshot(settings, signed["url"])
            validate_xlsx(content)
            if has_connections(content):
                raise ValueError("Editor snapshot must not contain data connections")
        except (httpx.HTTPError, ValueError):
            session.execute(text("""
                UPDATE source_workbook_editor_sessions SET state='failed'
                WHERE session_id=:id AND snapshot_request_id=:request_id AND state='pending'
            """), params)
            return {"error": 1}
        _service_session(session, session_id)
        session.execute(text("""
            UPDATE source_workbook_editor_sessions SET state='ready',snapshot_sha256=:sha,snapshot=:content
            WHERE session_id=:id AND snapshot_request_id=:request_id AND state='pending'
        """), dict(params, sha=sha256(content).hexdigest(), content=content))
        return {"error": 0}
