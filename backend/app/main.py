"""Точка входа FixRate AI API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware

API_DESCRIPTION = """
**FixRate AI** — помощник инженера-сметчика.

API возвращает **черновик** ведомости объёмов работ (ВОР) и предварительную смету
по фото/тексту дефекта. Результат **не является** финальным нормативным расчётом:
сметчик проверяет объёмы, расценки и подтверждает итог.

Источники цен в MVP могут иметь тип `DEMO` (демонстрационный прайс).

Демо интерфейса до появления фронтенда — этот Swagger (`/docs`).
"""


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="FixRate AI API",
        version="0.1.0",
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    # Служебный health снаружи /api/v1; бизнес-API — под префиксом v1.
    app.include_router(health_router)

    # Задел под следующие карточки (роутеры подключать здесь).
    # app.include_router(..., prefix="/api/v1")

    return app


app = create_app()
