"""FixRate AI Backend Application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.database import check_database_connection, dispose_engine
from app.schemas.common import ErrorCode, ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown."""
    settings = get_settings()

    # Startup
    app.state.settings = settings

    # Check database connection
    if await check_database_connection():
        print("✓ Database connection established")
    else:
        print("⚠ Database connection failed - some features may not work")

    yield

    # Shutdown
    await dispose_engine()
    print("✓ Application shutdown complete")


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="FixRate AI Backend",
        description="ТО/ППР equipment maintenance system API",
        version="0.1.0",
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
        openapi_url="/api/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"]
        if settings.is_development
        else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(api_router)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unhandled exceptions."""
        print(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message="An internal error occurred",
                request_id=getattr(request.state, "request_id", "unknown"),
            ).model_dump(),
        )

    # Health check endpoint
    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint for monitoring."""
        db_ok = await check_database_connection()
        return {
            "status": "healthy" if db_ok else "degraded",
            "database": "connected" if db_ok else "disconnected",
        }

    return app


# Application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
