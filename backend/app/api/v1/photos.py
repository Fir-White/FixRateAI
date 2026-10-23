"""Получение обработанных фотографий по безопасному идентификатору."""
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse

from app.api.v1.requests import photo_service
from app.services.photo_service import PhotoService

router = APIRouter(prefix="/photos", tags=["Photos"])


@router.get("/{photo_id}", response_class=FileResponse, summary="Получить фотографию по ID")
def get_photo(
    photo_id: UUID = Path(...),
    photos: PhotoService = Depends(photo_service),
) -> FileResponse:
    photo, path = photos.get(photo_id)
    return FileResponse(path, media_type="image/jpeg")
