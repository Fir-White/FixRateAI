"""Роутер проверки работоспособности сервиса."""
from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Проверка доступности ML Service."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "cv_provider": settings.cv_provider,
        "llm_provider": settings.llm_provider,
    }
