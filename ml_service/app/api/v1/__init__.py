"""API v1 routers."""
from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.process import router as process_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(process_router)

__all__ = ["health_router", "api_v1_router"]
