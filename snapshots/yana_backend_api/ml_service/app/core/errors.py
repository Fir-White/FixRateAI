"""Единый формат ошибок ML Service FixRate AI.

Формат полностью согласован со спецификацией проекта и модулем backend/app/core/errors.py:
    {"error": {"code": "...", "message": "...", "details": [{"field": "...", "issue": "..."}],
               "request_id": "..."}}

Стек вызовов (traceback) никогда не передаётся наружу клиентам.
"""
from typing import Any
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Базовое прикладное исключение сервиса."""

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


class NotFoundError(AppError):
    def __init__(self, message: str = "Ресурс не найден", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(404, "NOT_FOUND", message, details)


class ValidationError(AppError):
    def __init__(self, message: str = "Ошибка валидации входных данных", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(422, "VALIDATION_ERROR", message, details)


class InvalidImageError(AppError):
    def __init__(self, message: str = "Некорректный или повреждённый файл изображения", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(400, "INVALID_IMAGE", message, details)


class ModelUnavailableError(AppError):
    def __init__(self, message: str = "Модель или веса временно недоступны", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(503, "MODEL_UNAVAILABLE", message, details)


class UpstreamTimeoutError(AppError):
    def __init__(self, message: str = "Превышено время ожидания ответа сервиса", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(504, "UPSTREAM_TIMEOUT", message, details)


class ConflictError(AppError):
    def __init__(self, message: str = "Конфликт версий или данных", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(409, "CONFLICT", message, details)


def extract_request_id(request: Request | None) -> str:
    """Извлекает request_id из state запроса или возвращает дефолтное значение."""
    if request is not None and hasattr(request, "state"):
        return getattr(request.state, "request_id", "-")
    return "-"


def error_response(
    request: Request | None,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Формирует канонический JSON-ответ с ошибкой FixRate AI."""
    rid = request_id or extract_request_id(request)
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
        headers={"X-Request-ID": rid},
    )
