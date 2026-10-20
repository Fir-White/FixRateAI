"""Проверка живости сервера.

Эндпоинт подключается в корень (`/health`), а не под `/api/v1`: его дёргают
Docker/балансировщики/QA, ему не нужна версия бизнес-API.
Он НЕ ходит в БД и не зависит от ML — только «процесс жив».
Проверка БД появится отдельно в `/ready` (карточка 7).
"""
from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка живости сервера",
    description="Возвращает `{\"status\": \"ok\"}`, если процесс API запущен. БД не проверяется.",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
