"""Единый формат ошибок API (контракт — plan.md §8).

    {"error": {"code": "...", "message": "...", "details": [{"field": "...", "issue": "..."}],
               "request_id": "..."}}

Клиент НИКОГДА не получает traceback: подробности только в логах сервера.
Бизнес-код выбрасывает AppError (или подкласс) — обработчик сам соберёт ответ.
Нехватка данных для расчёта — это НЕ 500, а статус needs_clarification (позже, карточка 4).
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

# Коды из plan.md §8 (часть пока не используется — заведены, чтобы команда не придумывала свои)
HTTP_STATUS_TO_CODE = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    503: "DB_UNAVAILABLE",
    504: "UPSTREAM_TIMEOUT",
}


class AppError(Exception):
    """Базовая прикладная ошибка. Пример: raise AppError(404, "NOT_FOUND", "Заявка не найдена")."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    rid = _request_id(request)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": rid,
            }
        },
        # дублируем заголовок: ответ 500 формируется снаружи нашего middleware
        headers={"X-Request-ID": rid},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_STATUS_TO_CODE.get(exc.status_code, "HTTP_ERROR")
    messages = {404: "Ресурс не найден", 405: "Метод не поддерживается для этого пути"}
    message = messages.get(exc.status_code) or (
        exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
    )
    return error_response(request, exc.status_code, code, message)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ())]
        # убираем служебный префикс "body"/"query"/"path"/"header"
        field = ".".join(loc[1:] if loc and loc[0] in {"body", "query", "path", "header"} else loc)
        details.append({"field": field, "issue": err.get("msg", "invalid")})
    return error_response(
        request, 422, "VALIDATION_ERROR", "Некорректные входные данные", details
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Traceback — только в лог сервера, клиенту — безличное сообщение + request_id
    logger.error(
        "Необработанное исключение: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
        extra={"request_id": _request_id(request)},
    )
    return error_response(
        request, 500, "INTERNAL_ERROR", "Внутренняя ошибка сервера. Сообщите request_id команде."
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
