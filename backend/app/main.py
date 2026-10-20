"""Точка входа FixRate AI API.

Запуск (из каталога backend/):  uvicorn app.main:app --reload
"""
import logging

from fastapi import FastAPI

from app.api.v1 import health
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware

DESCRIPTION = """
**FixRate AI** — помощник инженера-сметчика.

Система принимает фото дефекта, текстовое описание и характеристики здания и формирует
**черновик ведомости объёмов работ (ВОР)** с расценками и ссылками на источники.

⚠️ Это **предварительный черновик**, а не утверждённая смета: результат обязан проверить сметчик.
Расценки в MVP — демонстрационные (`source_type=DEMO`), не промышленные ФЕР/ТЕР.
Если не хватает масштаба, норматива или цены, система запрашивает уточнение
и **не подставляет выдуманные числа**.

Формат ошибок единый: `{"error": {"code", "message", "details", "request_id"}}`.
"""


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router)  # /health
    app.include_router(api_v1_router)  # /api/v1/... (пока пусто)

    logging.getLogger("app").info(
        "Приложение создано: env=%s version=%s", settings.app_env, settings.app_version
    )
    return app


app = create_app()
