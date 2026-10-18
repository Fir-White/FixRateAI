"""Настройка логирования и привязка request_id к записям."""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Добавляет request_id в каждую запись лога."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"  # type: ignore[attr-defined]
        return True


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        # Повторный вызов (тесты / reload) — только уровень.
        root.setLevel(level.upper())
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(RequestIdFilter())

    root.addHandler(handler)
    root.setLevel(level.upper())

    # Меньше шума от uvicorn access (свой middleware логирует кратко).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
