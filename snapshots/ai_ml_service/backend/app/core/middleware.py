"""Middleware: X-Request-ID + access-лог.

Реализован как «чистый» ASGI-middleware (не BaseHTTPMiddleware), чтобы не ломать
contextvars и порядок обработчиков исключений.

Поведение:
- входящий заголовок X-Request-ID принимается, если он безопасный (<=64 символов,
  буквы/цифры/-/_); иначе генерируется новый UUID4;
- request_id кладётся в scope["state"] (доступен как request.state.request_id),
  в ContextVar для логов и возвращается клиенту в заголовке ответа X-Request-ID;
- на каждый HTTP-запрос пишется одна строка: метод, путь, статус, время.
"""
import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
logger = logging.getLogger("app.access")


def _extract_request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            if _SAFE_ID.match(candidate):
                return candidate
    return str(uuid.uuid4())


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _extract_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500  # если приложение упадёт до ответа

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %s (%.1f ms)",
                scope["method"],
                scope["path"],  # только путь: query-строку не логируем (там могут быть секреты)
                status_code,
                elapsed_ms,
            )
            request_id_ctx.reset(token)
