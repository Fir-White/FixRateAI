"""Логирование с идентификатором запроса (request_id).

request_id хранится в ContextVar: его кладёт middleware, а фильтр подставляет
в каждую строку лога. Так любая строка лога внутри запроса связана с ответом клиенту.

Правило проекта: НЕ логируем пароли, JWT, содержимое .env, тела файлов и query-строки.
"""
import logging
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # если request_id передали явно (extra=...), не перетираем его
        if not hasattr(record, "request_id"):
            record.request_id = request_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()  # не дублировать строки при повторном вызове (тесты, reload)
    root.addHandler(handler)
    root.setLevel(level.upper())
    # стандартный access-лог uvicorn не знает про request_id — пишем свой в middleware
    logging.getLogger("uvicorn.access").disabled = True
