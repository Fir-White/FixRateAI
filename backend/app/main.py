"""Executable integrated API. Run from the repository: uvicorn app.main:app --app-dir backend."""
from __future__ import annotations
from app.security.sessions import has_role

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import logging
import os
import re
from pathlib import Path
import secrets
from typing import Literal
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import RuntimeSettings
from app.files import validate_upload
from app.db.models import map_schema
from app.db.session import make_engine, make_session_factory
from app.integration.projections import Views
from app.integration.calendar import preview_calendar
from app.integration.assignment import assignment_context, assignment_preview
from app.integration.assignments import save_assignment, lock_workers
from app.integration.maintenance_jobs import _job_payload, create_job, job_history
from app.maintenance_jobs import InvalidJobTransition, ensure_transition, public_status
from app.schemas.maintenance import AssignmentCommand, ErrorResponse
from app.schemas.maintenance_api import (
    MaintenanceJobCreate,
    MaintenanceJobHistoryItem,
    MaintenanceJobResponse,
    MaintenanceJobTransition,
)
from app.schemas.management import CancelTask
from app.integration.analyst import ReadingInput, ExecutionInput, validate_execution, validate_acceptance, notify_event
from app.security.authorization import AuthorizationError, require_any_role
from app.security.sessions import COOKIE, Principal, SQL_ROLES, authenticate, create_session, digest, verify_password
from app.storage import safe_storage_path

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def configured_cors_origins(value: str | None = None) -> list[str]:
    """Return explicit browser origins; credentials must never use a wildcard."""
    raw = os.environ.get("CORS_ORIGINS", "") if value is None else value
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if "*" in origins:
        raise ValueError("CORS_ORIGINS must contain explicit origins, not '*'")
    return origins


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Command):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    site_id: UUID | None = None


class Revision(Command):
    expected_revision: int = Field(gt=0)


class ReportEdit(Revision):
    narrative: str = Field(max_length=10000)
    answers: dict[UUID, str | None]
    readings: list[ReadingInput] = Field(default_factory=list,max_length=200)
    actual: ExecutionInput | None = None


class AssignmentPreview(Revision):
    start_local: datetime
    end_local: datetime
    crew_id: UUID | None = None
    executor_ids: list[UUID] | None = Field(default=None,min_length=1,max_length=100)
    individual_only: bool = False


class GenerateCalendar(Command):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    idempotency_key: UUID
    preview_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssignCrew(Revision):
    schema_version: Literal["maintenance-0.1"] = "maintenance-0.1"
    executor_ids: list[UUID] = Field(min_length=1, max_length=1000)
    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: str = Field(min_length=1, max_length=10000)
    crew_id: UUID | None = None


class Review(Revision):
    schema_version: Literal["maintenance-0.1"] = "maintenance-0.1"
    execution_id: UUID
    verdict: Literal["accepted", "rejected"]
    reason: str = Field(min_length=1, max_length=10000)
    reviewed_ai_result_id: UUID | None = None
    additional_evidence_refs: list[str] = Field(default_factory=list)
    late_reason: str | None = Field(default=None,max_length=2000)


def require_role(principal: Principal, *roles):
    try:
        if not has_role(principal.role, roles):
            raise AuthorizationError()
    except AuthorizationError:
        raise HTTPException(403, "Действие недоступно для текущей роли") from None


def check_revision(order, revision):
    if order.revision != revision:
        raise HTTPException(409, "REVISION_CONFLICT: обновите данные")


def create_app(engine=None):
    runtime_settings = RuntimeSettings.from_environment()
    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = engine if engine is not None else make_engine()
        try:
            app.state.models = map_schema(app.state.engine)
            with app.state.engine.connect() as conn:
                if not conn.scalar(text("SELECT to_regclass('public.maintenance_notifications')")):
                    raise RuntimeError("Apply migrations through 009 before starting the API")
            app.state.factory = make_session_factory(app.state.engine)
            app.state.forecaster = None
            if runtime_settings.forecast_provider == "rf":
                try:
                    from ml_service.app.forecast.runtime import load_verified_forecaster
                    app.state.forecaster = load_verified_forecaster()
                except Exception as exc:
                    logger.error("RF artifact unavailable: %s", type(exc).__name__)
            import asyncio
            from app.integration.scheduler import run as run_scheduler
            scheduler=asyncio.create_task(run_scheduler(app)) if os.environ.get("MAINTENANCE_SCHEDULER","true").lower()=="true" and engine is None else None
            try:
                yield
            finally:
                if scheduler:
                    scheduler.cancel()
                    try: await scheduler
                    except asyncio.CancelledError: pass
        finally:
            if hasattr(app.state, "models"):
                app.state.models.registry.dispose()
            if engine is None:
                app.state.engine.dispose()

    app = FastAPI(title="FixRate AI", version="dev-0.1", lifespan=lifespan)
    cors_origins = configured_cors_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.settings = runtime_settings

    @app.middleware('http')
    async def request_identity(request,call_next):
        request.state.request_id=str(uuid4())
        origin = request.headers.get("origin")
        if request.url.path.startswith("/api/") and origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            response = error_response(request, 403, "Недопустимый origin")
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.error("Request failed id=%s type=%s", request.state.request_id, type(exc).__name__)
                response = error_response(request, 500, "Внутренняя ошибка сервера", code="INTERNAL_ERROR")
        response.headers['X-Request-ID']=request.state.request_id
        logger.info("%s %s -> %s request_id=%s", request.method, request.url.path,
                    response.status_code, request.state.request_id)
        return response

    def error_response(request,status,message,code=None,details=None,headers=None):
        default={401:'UNAUTHENTICATED',403:'ACCESS_DENIED',404:'NOT_FOUND',405:'METHOD_NOT_ALLOWED',409:'CONFLICT',422:'VALIDATION_ERROR',503:'DATABASE_UNAVAILABLE'}
        match=re.match(r'^([A-Z][A-Z0-9_]+)(?::|$)',message)
        body=ErrorResponse(schema_version='maintenance-0.1',detail=message,error=dict(
            code=code or (match.group(1) if match else default.get(status,'REQUEST_FAILED')),message=message,
            details=details or [],request_id=getattr(request.state,'request_id',str(uuid4()))))
        return JSONResponse(status_code=status,content=body.model_dump(mode='json'),headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request,exc):
        who=getattr(request.state,"principal",None)
        if who and exc.status_code in (403,409,422) and request.url.path.endswith(("/assign","/assignment-preview")):
            try:
                with request.app.state.factory() as failed:
                    failed.execute(text("INSERT INTO audit_events(site_id,actor_type,actor_user_id,entity_type,entity_id,action,after_snapshot) VALUES (:site,'user',:actor,'assignment',:entity,'denied',CAST(:details AS jsonb))"),dict(site=who.site_id,actor=who.user_id,entity=UUID(str(request.path_params.get("task_id",uuid4()))),details=__import__("json").dumps(dict(path=request.url.path,status=exc.status_code,reason=str(exc.detail)))))
                    failed.commit()
            except SQLAlchemyError:
                logger.error("Assignment denial audit unavailable")
        return error_response(request,exc.status_code,str(exc.detail),headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return error_response(request,422,'Проверьте заполнение полей формы',details=[dict(
            field='.'.join(map(str,error['loc'])) or 'request',issue=error['msg']) for error in exc.errors()])

    def db(request: Request):
        with request.app.state.factory() as session:
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def principal(request: Request, session=Depends(db)):
        who=authenticate(request, session)
        request.state.principal=who
        return who

    def views(request: Request, who=Depends(principal), session=Depends(db)):
        return Views(session, request.app.state.models, who)

    def audit(view, order, action):
        view.repo.add("audit_events", site_id=view.principal.site_id, actor_type="user",
                      actor_user_id=view.principal.user_id, entity_type="work_orders",
                      entity_id=order.work_order_id, action=action,
                      after_snapshot={"status": order.status, "revision": order.revision})

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return error_response(request,409,'Конфликт с сохранёнными данными')

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error("Database operation failed: %s request_id=%s", type(exc).__name__,
                     getattr(request.state, "request_id", "unknown"))
        return error_response(request,503,'База данных недоступна')

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.exception("Unhandled API error request_id=%s",
                         getattr(request.state, "request_id", "unknown"))
        return error_response(request, 500, "Внутренняя ошибка сервера", code="INTERNAL_ERROR")

    @app.get("/api/health")
    def health(session=Depends(db)):
        session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ready"}

    @app.post("/api/v1/auth/login")
    def login(payload: Login, response: Response, request: Request, session=Depends(db)):
        # Login is also same-origin; the session is not chosen by a role header.
        origin = request.headers.get("origin")
        same_origin = origin and origin.rstrip("/") == str(request.base_url).rstrip("/")
        if origin and not same_origin and origin.rstrip("/") not in cors_origins:
            raise HTTPException(403, "Недопустимый origin")
        user = session.execute(text("SELECT * FROM users WHERE lower(email)=lower(:email) AND is_active"),
                               {"email": payload.email}).mappings().first()
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(401, "Неверный email или пароль")
        memberships = session.execute(text("""SELECT m.site_id,m.role,s.name,s.timezone FROM site_memberships m
            JOIN sites s USING(site_id) WHERE m.user_id=:user AND m.is_active AND s.is_active"""),
            {"user": user["user_id"]}).mappings().all()
        if payload.site_id:
            memberships = [m for m in memberships if m["site_id"] == payload.site_id]
        if not memberships:
            raise HTTPException(403, "Нет доступа к объекту")
        if len(memberships) != 1:
            raise HTTPException(409, "Укажите site_id: у пользователя несколько объектов")
        member = memberships[0]
        old = request.cookies.get(COOKIE)
        if old:
            session.execute(text("DELETE FROM fixrate_sessions WHERE token_hash=:token"), {"token": digest(old)})
        token, csrf = create_session(session, user["user_id"], member["site_id"])
        # Commit before setting a successful cookie/response.
        session.commit()
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=28800,
                            secure=runtime_settings.cookie_secure, path="/")
        response.set_cookie("fixrate_csrf", csrf, httponly=False, samesite="lax", max_age=28800,
                            secure=runtime_settings.cookie_secure, path="/")
        who = Principal(user["user_id"], member["site_id"], SQL_ROLES[member["role"]], user["full_name"],
                        user["email"], member["name"], member["timezone"])
        return {"profile": who.profile(), "csrfToken": csrf}

    @app.get("/api/v1/auth/session")
    def current_session(who=Depends(principal)):
        return {"profile": who.profile()}

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(request: Request, response: Response, who=Depends(principal), session=Depends(db)):
        session.execute(text("DELETE FROM fixrate_sessions WHERE token_hash=:token"),
                        {"token": digest(request.cookies[COOKIE])})
        session.commit()
        response.delete_cookie(COOKIE, path="/")
        response.delete_cookie("fixrate_csrf", path="/")

    prefix = "/api/v1/maintenance"

    @app.get("/api/v1/maintenance_jobs", response_model=list[MaintenanceJobResponse], operation_id="maintenance_jobs_list")
    @app.get(prefix + "/jobs", response_model=list[MaintenanceJobResponse])
    def maintenance_job_list(status: str | None = None, v=Depends(views)):
        require_role(v.principal, "executive", "admin", "dispatcher", "engineer", "executor")
        if status is not None and status not in {
            "planned", "assigned", "in_progress", "submitted", "accepted", "rework",
        }:
            raise HTTPException(422, "Некорректный статус задания")
        orders = v.repo.orders(
            v.principal.site_id,
            user_id=v.principal.user_id if v.principal.role == "executor" else None,
        )
        return [
            _job_payload(v, order)
            for order in orders
            if (status is None or public_status(order.status) == status)
            and public_status(order.status) != "cancelled"
        ]

    @app.post("/api/v1/maintenance_jobs", status_code=201, response_model=MaintenanceJobResponse, operation_id="maintenance_jobs_create")
    @app.post(prefix + "/jobs", status_code=201, response_model=MaintenanceJobResponse)
    def maintenance_job_create(command: MaintenanceJobCreate, v=Depends(views)):
        require_role(v.principal, "admin", "dispatcher")
        order = create_job(
            v,
            command.schedule_entry_id,
            command.equipment_id,
            command.maintenance_rule_id,
            command.planned_start_at,
        )
        return _job_payload(v, order)

    @app.get("/api/v1/maintenance_jobs/{job_id}", response_model=MaintenanceJobResponse, operation_id="maintenance_jobs_read")
    @app.get(prefix + "/jobs/{job_id}", response_model=MaintenanceJobResponse)
    def maintenance_job_detail(job_id: UUID, v=Depends(views)):
        require_role(v.principal, "executive", "admin", "dispatcher", "engineer", "executor")
        return _job_payload(v, v.task(job_id))

    @app.post("/api/v1/maintenance_jobs/{job_id}/transitions", response_model=MaintenanceJobResponse, operation_id="maintenance_jobs_transition_post")
    @app.post(prefix + "/jobs/{job_id}/transitions", response_model=MaintenanceJobResponse)
    @app.patch("/api/v1/maintenance_jobs/{job_id}", response_model=MaintenanceJobResponse, operation_id="maintenance_jobs_transition_patch")
    @app.patch(prefix + "/jobs/{job_id}", response_model=MaintenanceJobResponse)
    def maintenance_job_transition(
        job_id: UUID, command: MaintenanceJobTransition, v=Depends(views), background_tasks: BackgroundTasks = None
    ):
        require_role(v.principal, "executive", "admin", "dispatcher", "engineer", "executor")
        order = v.task(job_id, lock=True)
        check_revision(order, command.expected_revision)
        _job_payload(v, order)
        try:
            ensure_transition(public_status(order.status), command.status)
        except InvalidJobTransition as exc:
            raise HTTPException(409, f"INVALID_STATUS_TRANSITION: {exc}") from None

        revision = Revision(expected_revision=command.expected_revision)
        if command.status == "assigned":
            raise HTTPException(409, "ASSIGNMENT_REQUIRED: подтвердите состав и интервал через команду назначения")
        if command.status == "in_progress":
            start(job_id, revision, v)
        elif command.status == "submitted":
            submit(job_id, revision, v, background_tasks)
        else:
            require_role(v.principal, "engineer")
            report = max(v.rows("work_reports", work_order_id=job_id),
                         key=lambda item: item.revision_no, default=None)
            if report is None:
                raise HTTPException(409, "Принимать можно только текущую отправленную попытку")
            reason = (command.reason or "").strip()
            if not reason or len(reason) > 10000:
                raise HTTPException(422, "Укажите причину решения длиной до 10000 символов")
            review(job_id, Review(expected_revision=command.expected_revision,
                                  execution_id=report.work_report_id,
                                  verdict="accepted" if command.status == "accepted" else "rejected",
                                  reason=reason), v)
        return _job_payload(v, order)

    @app.get("/api/v1/maintenance_jobs/{job_id}/history", response_model=list[MaintenanceJobHistoryItem], operation_id="maintenance_jobs_history")
    @app.get(prefix + "/jobs/{job_id}/history", response_model=list[MaintenanceJobHistoryItem])
    def maintenance_job_history(job_id: UUID, v=Depends(views)):
        require_role(v.principal, "executive", "admin", "dispatcher", "engineer", "executor")
        return job_history(v, job_id)

    @app.get(prefix + "/ui/equipment")
    def equipment_list(v=Depends(views)):
        visible = v.visible_equipment_ids() if v.principal.role == "executor" else None
        return [v.equipment(e) for e in v.rows("equipment") if visible is None or e.equipment_id in visible]

    @app.get(prefix + "/ui/equipment/{equipment_id}")
    def equipment_detail(equipment_id: UUID, v=Depends(views)):
        if v.principal.role == "executor" and equipment_id not in v.visible_equipment_ids():
            raise HTTPException(404, "Оборудование не найдено")
        return {"equipment": v.equipment(v.one("equipment", equipment_id=equipment_id)), "history": v.history(equipment_id)}

    @app.get(prefix + "/ui/tasks")
    def task_list(v=Depends(views)):
        orders = v.repo.orders(v.principal.site_id, user_id=v.principal.user_id if v.principal.role == "executor" else None)
        # orders() already limits executor results to active assignments at this site.
        v.prepare_task_views(orders)
        return [v.task_view(order) for order in orders]

    @app.get(prefix + "/ui/tasks/{task_id}")
    def task_detail(task_id: UUID, v=Depends(views)):
        return v.bundle(v.task(task_id))

    @app.get(prefix + "/ui/calendar")
    def calendar(year: int, month: int, v=Depends(views)):
        require_role(v.principal, "executive", "chief_engineer", "dispatcher", "engineer", "executor")
        if not 2000 <= year <= 2200 or not 1 <= month <= 12:
            raise HTTPException(422, "Некорректный месяц")
        return v.calendar(year, month)

    @app.get(prefix + "/ui/tasks/{task_id}/assignment-context")
    def crew_context(task_id: UUID, response: Response, v=Depends(views)):
        require_role(v.principal, "dispatcher")
        response.headers["Cache-Control"] = "private, no-store"
        return assignment_context(v, v.task(task_id))

    @app.post(prefix + "/tasks/{task_id}/assignment-preview")
    def crew_preview(task_id: UUID, command: AssignmentPreview, response: Response, v=Depends(views)):
        require_role(v.principal, "dispatcher")
        order = v.task(task_id)
        check_revision(order, command.expected_revision)
        response.headers["Cache-Control"] = "private, no-store"
        return assignment_preview(v, order, command.start_local, command.end_local, command.crew_id,command.executor_ids,command.individual_only)

    @app.post(prefix + "/tasks/{task_id}/assign")
    def assign_crew(task_id: UUID, command: AssignCrew, response: Response, v=Depends(views)):
        require_role(v.principal, "dispatcher")
        response.headers["Cache-Control"] = "private, no-store"
        canonical = AssignmentCommand.model_validate_json(command.model_dump_json(exclude={"crew_id"}))
        return save_assignment(v, task_id, canonical, command.crew_id)

    @app.post(prefix + "/tasks/{task_id}/cancel")
    def task_cancel(task_id:UUID,command:CancelTask,v=Depends(views)):
        from app.integration.assignments import cancel_task
        return cancel_task(v,task_id,command.expected_revision,command.reason)

    @app.get(prefix + "/ui/calendar/preview")
    def calendar_preview(year: int, month: int, response: Response, v=Depends(views)):
        require_role(v.principal, "dispatcher", "engineer")
        if not 2000 <= year <= 2100 or not 1 <= month <= 12:
            raise HTTPException(422, "Расчёт поддерживает месяцы с 2000 по 2100 год")
        response.headers["Cache-Control"] = "private, no-store"
        return preview_calendar(v, year, month)

    @app.post(prefix + "/calendar/generate")
    def calendar_generate(command: GenerateCalendar, response: Response, v=Depends(views)):
        from app.integration.planning import generate_tasks
        require_role(v.principal, "dispatcher")
        response.headers["Cache-Control"] = "private, no-store"
        return generate_tasks(v, command.year, command.month, command.idempotency_key, command.preview_token, app.state.forecaster,
                              forecast_timeout_seconds=app.state.settings.forecast_timeout_seconds)

    @app.get(prefix + "/ui/comparisons")
    def comparisons(v=Depends(views)):
        require_role(v.principal, "executive", "admin", "dispatcher", "engineer")
        return v.comparisons()

    @app.get(prefix + "/ui/comparisons/{run_id}")
    def comparison(run_id: UUID, v=Depends(views)):
        require_role(v.principal, "executive", "admin", "dispatcher", "engineer")
        run = next((r for r in v.comparisons() if r["runId"] == str(run_id)), None)
        if run is None:
            raise HTTPException(404, "Запуск не найден")
        return {"run": run}

    @app.get(prefix + "/ui/quality")
    def quality(v=Depends(views)):
        require_role(v.principal, "engineer")
        return [v.task_view(o) for o in v.rows("work_orders") if o.status in ("in_review", "rework")]

    @app.post(prefix + "/tasks/{task_id}/start")
    def start(task_id: UUID, payload: Revision, v=Depends(views)):
        require_role(v.principal, "executor")
        order = v.task(task_id, lock=True)
        check_revision(order, payload.expected_revision)
        if order.status not in ("assigned", "rework"):
            raise HTTPException(409, "Начать можно назначенное задание или новую попытку после доработки")
        lock_workers(v, {a.user_id for a in v.rows("work_assignments", work_order_id=task_id)
                         if a.status not in ("cancelled", "declined")})
        # Snapshot must be defined by the operation, never generated from UI assumptions.
        checklist = order.operation_snapshot.get("checklist")
        if not checklist:
            raise HTTPException(422, "MISSING_CHECKLIST: сначала согласуйте чек-лист операции")
        if order.schedule_entry_id:
            entry=v.one("schedule_entries",schedule_entry_id=order.schedule_entry_id)
            from zoneinfo import ZoneInfo
            if datetime.now(ZoneInfo(v.principal.timezone)).date() < (entry.earliest_date or entry.regulatory_deadline_on):
                raise HTTPException(409,"MAINTENANCE_WINDOW_NOT_OPEN: обязательство ещё нельзя выполнять")
        if not order.schedule_entry_id and order.operation_snapshot.get("earliest_date"):
            from datetime import date
            from zoneinfo import ZoneInfo
            if datetime.now(ZoneInfo(v.principal.timezone)).date()<date.fromisoformat(order.operation_snapshot["earliest_date"]):
                raise HTTPException(409,"MAINTENANCE_WINDOW_NOT_OPEN: окно работы ещё не открыто")
        if order.operation_snapshot.get("methodology_ref") and order.schedule_entry_id:
            approved=v.one("schedule_plans",schedule_plan_id=entry.schedule_plan_id)
            if approved.status!="approved": raise HTTPException(409,"PLAN_NOT_APPROVED: месячный план должен утвердить главный инженер")
        reports = v.rows("work_reports", work_order_id=task_id)
        v.repo.add("work_reports", site_id=v.principal.site_id, work_order_id=task_id,
                   revision_no=max((r.revision_no for r in reports), default=0)+1, submitted_by=v.principal.user_id,
                   checklist_snapshot=checklist)
        order.status, order.started_at = "in_progress", datetime.now(timezone.utc)
        order.revision += 1
        v.session.flush()
        audit(v, order, "start")
        result = v.bundle(order)
        v.session.commit()
        return result

    def editable(v, task_id, revision):
        require_role(v.principal, "executor")
        order = v.task(task_id, lock=True)
        check_revision(order, revision)
        reports = v.rows("work_reports", work_order_id=task_id)
        report = max(reports, key=lambda r: r.revision_no) if reports else None
        if (order.status != "in_progress" or not report or report.status != "draft"
                or report.submitted_by != v.principal.user_id):
            raise HTTPException(409, "Только автор может изменять текущий черновик")
        return order, report

    @app.put(prefix + "/tasks/{task_id}/report")
    def save_report(task_id: UUID, payload: ReportEdit, v=Depends(views)):
        order, report = editable(v, task_id, payload.expected_revision)
        items = {UUID(i["id"]): i for i in report.checklist_snapshot}
        if set(payload.answers) - set(items):
            raise HTTPException(422, "Ответ относится к другому чек-листу")
        existing = {a.checklist_template_id: a for a in v.rows("checklist_results", work_report_id=report.work_report_id)}
        for identity, answer in payload.answers.items():
            item = items[identity]
            if item["answerKind"] == "boolean" and answer not in (None, "done", "not_done", "not_applicable"):
                raise HTTPException(422, "Некорректный ответ checkbox")
            if item["answerKind"] == "number" and answer:
                from decimal import Decimal, InvalidOperation
                try:
                    if not Decimal(answer).is_finite():
                        raise ValueError()
                except (InvalidOperation, ValueError):
                    raise HTTPException(422, "Ожидается конечное число") from None
            if identity in existing:
                existing[identity].response_value = {"answer": answer}
            else:
                v.repo.add("checklist_results", site_id=v.principal.site_id, work_order_id=task_id,
                           work_report_id=report.work_report_id, checklist_template_id=identity,
                           question_snapshot=item["text"], response_value={"answer": answer})
        validate_execution(v,order,report,payload)
        report.comment = payload.narrative
        order.revision += 1
        v.session.flush()
        audit(v, order, "save_report")
        result = v.bundle(order)
        v.session.commit()
        return result

    storage = runtime_settings.photo_storage_root

    def photo_path(photo):
        # Source demo photo is read-only and served only through the same access check.
        if photo.storage_key == "database/demo/demo-photo.png":
            return ROOT / "data/demo/demo-photo.png"
        try:
            path = safe_storage_path(storage, photo.storage_key)
        except ValueError:
            raise HTTPException(404, "Файл не найден")
        return path

    @app.post(prefix + "/tasks/{task_id}/photos")
    def upload_photo(task_id: UUID, expected_revision: int = Form(...), checklist_item_id: UUID = Form(...),
                     phase: Literal["before", "after"] = Form(...), view_key: str = Form(...),
                     file: UploadFile = File(...), v=Depends(views)):
        order, report = editable(v, task_id, expected_revision)
        if str(checklist_item_id) not in {i["id"] for i in report.checklist_snapshot} or not view_key.strip() or len(view_key) > 200:
            raise HTTPException(422, "Укажите пункт чек-листа и ракурс")
        try:
            data = file.file.read(10_485_761)
            mime = validate_upload(data, file.filename, file.content_type)
        except Exception:
            raise HTTPException(422, "Недопустимое изображение") from None
        if order.operation_snapshot.get("methodology_ref"):
            from ml_service.app.cv.quality import ImageQualityGuard
            quality=ImageQualityGuard().assess_bytes(data)
            if not quality.is_acceptable:raise HTTPException(422,"PHOTO_QUALITY: "+str(quality.issue))
        links = v.rows("work_order_equipment", work_order_id=task_id)
        if len(links) != 1:
            raise HTTPException(422, "Фото API требует ровно одно оборудование в задании")
        identity = uuid4()
        key = f"{v.principal.site_id}/{identity}"
        try:
            path = safe_storage_path(storage, key)
        except ValueError:
            raise HTTPException(503, "PHOTO_STORAGE_UNAVAILABLE") from None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise HTTPException(503, "PHOTO_STORAGE_UNAVAILABLE") from None
        try:
            v.repo.add("evidence_files", evidence_file_id=identity, site_id=v.principal.site_id,
                work_order_id=task_id, work_report_id=report.work_report_id, uploaded_by=v.principal.user_id,
                stage=phase, storage_key=key, mime_type=mime, file_size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                checklist_item_id=checklist_item_id, view_key=view_key.strip(), equipment_id=links[0].equipment_id)
            order.revision += 1
            v.session.flush()
            audit(v, order, "upload_photo")
            result = v.bundle(order)
            v.session.commit()
        except BaseException:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.error("Photo cleanup failed")
            raise
        return result

    @app.get(prefix + "/photos/{photo_id}")
    @app.get(prefix + "/photos/{photo_id}/content")
    def download_photo(photo_id: UUID, v=Depends(views)):
        photo = v.one("evidence_files", evidence_file_id=photo_id)
        v.task(photo.work_order_id)
        path = photo_path(photo)
        if not path.is_file():
            raise HTTPException(404, "Файл отсутствует в хранилище")
        return FileResponse(path, media_type=photo.mime_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.post(prefix + "/tasks/{task_id}/submit")
    def submit(task_id: UUID, payload: Revision, v=Depends(views), background_tasks:BackgroundTasks=None):
        order, report = editable(v, task_id, payload.expected_revision)
        answers = {str(a.checklist_template_id): a.response_value.get("answer")
                   for a in v.rows("checklist_results", work_report_id=report.work_report_id)}
        photos = v.rows("evidence_files", work_report_id=report.work_report_id)
        for item in report.checklist_snapshot:
            answer = answers.get(item["id"])
            if item["required"] and (not answer or (item["answerKind"] == "boolean" and answer != "done")):
                raise HTTPException(422, "Заполните все обязательные пункты чек-листа")
            if item["photoRequired"]:
                pairs = {(p.stage, p.view_key) for p in photos if str(p.checklist_item_id) == item["id"]}
                if not any(("after", key) in pairs for stage, key in pairs if stage == "before"):
                    raise HTTPException(422, "Требуется пара фото до/после одного ракурса")
        validate_execution(v,order,report,None,submitting=True)
        report.status, report.submitted_at = "submitted", datetime.now(timezone.utc)
        order.status = "in_review"
        notify_event(v,order,"submitted",("engineer","chief_engineer"))
        order.revision += 1
        v.session.flush()
        audit(v, order, "submit")
        from app.integration.photo_evidence import has_photo_pair
        if has_photo_pair(photos):
            # Durable opt-in for this submission only; historical reports are not backfilled.
            report.execution_context=dict(report.execution_context,photo_analysis_requested_at=report.submitted_at.isoformat())
            if background_tasks is not None:
                background_tasks.add_task(app.state.automatic_photo_review,task_id,order.revision,v.principal)
        result = v.bundle(order)
        v.session.commit()
        return result

    @app.post(prefix + "/tasks/{task_id}/review")
    def review(task_id: UUID, payload: Review, v=Depends(views)):
        require_role(v.principal, "engineer")
        order = v.task(task_id, lock=True)
        check_revision(order, payload.expected_revision)
        reports = v.rows("work_reports", work_order_id=task_id)
        report = max(reports, key=lambda r: r.revision_no) if reports else None
        if order.status != "in_review" or not report or report.status != "submitted" or report.work_report_id != payload.execution_id:
            raise HTTPException(409, "Принимать можно только текущую отправленную попытку")
        if report.submitted_by == v.principal.user_id or any(a.user_id == v.principal.user_id
                for a in v.rows("work_assignments", work_order_id=task_id)):
            raise HTTPException(403, "Нельзя принимать собственную работу")
        if not payload.reason.strip():
            raise HTTPException(422, "Укажите причину решения")
        validate_acceptance(v,order,report,payload)
        if payload.reviewed_ai_result_id:
            v.one("ai_quality_checks", ai_quality_check_id=payload.reviewed_ai_result_id, work_report_id=report.work_report_id)
        v.repo.add("acceptance_reviews", site_id=v.principal.site_id, work_order_id=task_id,
                   work_report_id=report.work_report_id, reviewer_user_id=v.principal.user_id,
                   decision="accepted" if payload.verdict == "accepted" else "rework", comment=payload.reason.strip(),
                   decision_context={"reviewed_ai_result_id": str(payload.reviewed_ai_result_id) if payload.reviewed_ai_result_id else None,
                                     "additional_evidence_refs": payload.additional_evidence_refs,
                                     "performed_at": report.execution_context.get("performed_at"),
                                     "actual_person_hours": report.execution_context.get("person_hours"),
                                     "late_reason": payload.late_reason,
                                     "exception":order.exception_context})
        report.status = "reviewed"
        order.status = "completed" if payload.verdict == "accepted" else "rework"
        if payload.verdict=="accepted":
            order.completed_at=datetime.fromisoformat(report.execution_context["performed_at"]) if report.execution_context.get("performed_at") else report.submitted_at
        notify_event(v,order,"accepted" if payload.verdict=="accepted" else "rework",("executor","technician"))
        order.revision += 1
        v.session.flush()
        audit(v, order, "review")
        result = v.bundle(order)
        v.session.commit()
        return result

    from app.integration.management import register_routes
    register_routes(app,views,db)
    from app.integration.analyst import register_analyst_routes
    register_analyst_routes(app,views,photo_path,editable)
    from app.integration.incidents import register_incident_routes
    register_incident_routes(app,views)
    from app.integration.maintenance_api import register_routes as register_maintenance_api_routes
    register_maintenance_api_routes(app, views)
    from app.integration.ml import register_ml_routes
    register_ml_routes(app, views, photo_path, require_role, check_revision)

    dist = ROOT / "frontend/dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Маршрут не найден")
            return FileResponse(dist / "index.html")
    return app


app = create_app()
