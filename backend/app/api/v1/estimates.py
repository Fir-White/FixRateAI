"""API запуска и получения черновых смет по заявкам."""
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.adapters.ml_pipeline import MLPipelineAdapter
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.core import User
from app.schemas.estimate import EstimateRunResult
from app.services.estimate_service import EstimateService

router = APIRouter(prefix="/estimates", tags=["Estimates"])


def estimate_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EstimateService:
    settings = get_settings()
    return EstimateService(
        db,
        user.user_id,
        MLPipelineAdapter(settings.ml_base_url, settings.ml_timeout_seconds),
    )


@router.post(
    "/requests/{request_id}",
    response_model=EstimateRunResult,
    status_code=status.HTTP_201_CREATED,
    summary="Запустить MVP-пайплайн и сформировать черновик сметы",
)
def create_estimate(
    request_id: UUID = Path(...),
    estimates: EstimateService = Depends(estimate_service),
) -> EstimateRunResult:
    return estimates.run(request_id)


@router.get(
    "/requests/{request_id}",
    response_model=EstimateRunResult,
    summary="Получить последнюю смету заявки",
)
def get_estimate(
    request_id: UUID = Path(...),
    estimates: EstimateService = Depends(estimate_service),
) -> EstimateRunResult:
    return estimates.latest(request_id)
