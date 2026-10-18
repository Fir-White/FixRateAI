"""Единый контракт ошибок API и обработчики исключений."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx


def error_body(
    *,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id or request_id_ctx.get() or "-",
        }
    }


def _status_to_code(status_code: int) -> str:
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_ERROR",
        503: "DB_UNAVAILABLE",
        504: "UPSTREAM_TIMEOUT",
    }
    return mapping.get(status_code, "INTERNAL_ERROR")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = []
        for err in exc.errors():
            loc = err.get("loc", ())
            field = ".".join(str(part) for part in loc if part != "body")
            details.append(
                {
                    "field": field or None,
                    "issue": err.get("msg", "invalid"),
                }
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body(
                code="VALIDATION_ERROR",
                message="Ошибка валидации входных данных",
                details=details,
                request_id=getattr(request.state, "request_id", None),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            code = str(detail["code"])
            message = str(detail["message"])
            details = detail.get("details") or []
        else:
            code = _status_to_code(exc.status_code)
            message = str(detail) if detail else code
            details = []
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                code=code,
                message=message,
                details=details if isinstance(details, list) else [],
                request_id=getattr(request.state, "request_id", None),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # Traceback только в логах сервера, клиенту — короткий JSON.
        import logging

        logging.getLogger("app.errors").exception(
            "Unhandled exception: %s", type(exc).__name__
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body(
                code="INTERNAL_ERROR",
                message="Внутренняя ошибка сервера",
                request_id=getattr(request.state, "request_id", None),
            ),
        )
