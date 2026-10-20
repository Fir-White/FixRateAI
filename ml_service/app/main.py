"""Точка входа ML Service FixRate AI.

Запуск:
    uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
"""
import logging
import re
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.health import router as health_router
from app.api.v1 import api_v1_router
from app.core.config import get_settings
from app.core.errors import AppError, error_response
from app.core.logging import setup_logging

SAFE_REQUEST_ID_RE = re.compile(r"^[0-9a-zA-Z\-_]{1,64}$")
logger = logging.getLogger("app.main")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware для установки и проброса заголовка X-Request-ID."""

    async def dispatch(self, request: Request, call_next):
        header_rid = request.headers.get("X-Request-ID")
        if header_rid and SAFE_REQUEST_ID_RE.match(header_rid):
            rid = header_rid
        else:
            rid = str(uuid4())

        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрация обработчиков исключений для приведения к единому формату FixRate AI."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        return error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for err in exc.errors():
            loc = [str(part) for part in err.get("loc", ())]
            field = ".".join(loc[1:] if loc and loc[0] in {"body", "query", "path", "header"} else loc)
            details.append({"field": field, "issue": err.get("msg", "invalid")})
        return error_response(request, 422, "VALIDATION_ERROR", "Некорректные параметры запроса", details)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        logger.error(
            "Необработанное исключение: %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
            extra={"request_id": rid},
        )
        return error_response(
            request, 500, "INTERNAL_ERROR", "Внутренняя ошибка сервиса. Сообщите request_id администратору.", request_id=rid
        )


def create_app() -> FastAPI:
    """Фабрика создания приложения FastAPI."""
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="FixRate AI — ML Service для детекции дефектов, RAG-поиска и детерминированного сметного расчёта",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)

    # Роутеры
    app.include_router(health_router)          # /health
    app.include_router(api_v1_router)          # /api/v1/...

    logger.info("ML Service инициализирован (env=%s, version=%s)", settings.app_env, settings.app_version)
    return app


app = create_app()
