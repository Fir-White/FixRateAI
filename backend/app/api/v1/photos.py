"""API загрузки и получения фотографий дефектов."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Path, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.core import User
from app.schemas.request import PhotoOut
from app.services.photo_service import PhotoService
from sqlalchemy.orm import Session

router = APIRouter(prefix="/photos", tags=["Photos"])


def photo_service(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PhotoService:
    return PhotoService(db, get_settings())


@router.post(
    "/requests/{request_id}",
    response_model=PhotoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить фотографию заявки",
)
async def upload_photo(
    request_id: UUID = Path(...),
    file: UploadFile = File(...),
    photos: PhotoService = Depends(photo_service),
) -> PhotoOut:
    return await photos.upload(request_id, file)


@router.get("/{photo_id}", response_class=FileResponse, summary="Получить фотографию по ID")
def get_photo(
    photo_id: UUID = Path(...),
    photos: PhotoService = Depends(photo_service),
) -> FileResponse:
    photo, path = photos.get(photo_id)
    return FileResponse(path, media_type="image/jpeg")
