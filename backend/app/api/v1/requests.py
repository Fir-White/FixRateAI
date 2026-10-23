"""HTTP API заявок на ремонт."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User
from app.schemas.request import PhotoOut, RequestCreate, RequestListOut, RequestOut, RequestStatus, RequestUpdate
from app.schemas.estimate import EstimateRunResult
from app.adapters.ml_pipeline import MLPipelineAdapter
from app.core.config import get_settings
from app.services.estimate_service import EstimateService
from app.services.request_service import RequestService
from app.services.photo_service import PhotoService

router = APIRouter(prefix="/requests", tags=["Requests"])


def photo_service(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PhotoService:
    return PhotoService(db, get_settings())


def service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RequestService:
    return RequestService(db, user)


@router.post("", response_model=RequestOut, status_code=status.HTTP_201_CREATED, summary="Создать заявку")
def create_request(data: RequestCreate, requests: RequestService = Depends(service)) -> RequestOut:
    return requests.create(data)


@router.post("/{request_id}/photos", response_model=PhotoOut, status_code=status.HTTP_201_CREATED)
async def upload_photo(
    request_id: UUID = Path(...),
    file: UploadFile = File(...),
    photos: PhotoService = Depends(photo_service),
) -> PhotoOut:
    return await photos.upload(request_id, file)


@router.get("", response_model=RequestListOut, summary="Получить список заявок")
def list_requests(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    request_status: RequestStatus | None = Query(default=None, alias="status"),
    building_id: UUID | None = Query(default=None),
    requests: RequestService = Depends(service),
) -> RequestListOut:
    items, total = requests.list(
        limit=limit, offset=offset, status=request_status, building_id=building_id
    )
    return RequestListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/{request_id}", response_model=RequestOut, summary="Получить заявку по ID")
def get_request(
    request_id: UUID = Path(...),
    requests: RequestService = Depends(service),
) -> RequestOut:
    return requests.get(request_id)


@router.patch("/{request_id}", response_model=RequestOut, summary="Изменить заявку")
def update_request(
    data: RequestUpdate,
    request_id: UUID = Path(...),
    requests: RequestService = Depends(service),
) -> RequestOut:
    return requests.update(request_id, data)


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
    "/{request_id}/estimate",
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
    "/{request_id}/estimate",
    response_model=EstimateRunResult,
    summary="Получить последнюю смету заявки",
)
def get_estimate(
    request_id: UUID = Path(...),
    estimates: EstimateService = Depends(estimate_service),
) -> EstimateRunResult:
    return estimates.latest(request_id)
