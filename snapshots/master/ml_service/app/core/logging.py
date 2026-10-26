"""Настройка логирования ML Service FixRate AI.

Обеспечивает единый формат сообщений с поддержкой сквозного X-Request-ID.
"""
import logging
import sys


class RequestIdFilter(logging.Filter):
    """Фильтр, гарантирующий наличие атрибута request_id во всех логах."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """Конфигурирует корневой логгер приложения."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [req_id:%(request_id)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Очищаем существующие обработчики во избежание дублирования логов
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Настраиваем уровень сторонних библиотек
    logging.getLogger("uvicorn.access").setLevel(numeric_level)
    logging.getLogger("PIL").setLevel(logging.WARNING)
