"""Проверка, сохранение и выдача фотографий заявок."""
import hashlib
import io
import re
from pathlib import Path
from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.requests import RequestPhoto
from app.repositories.request_repository import RequestRepository
from app.storage.local import LocalPhotoStorage

ALLOWED = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
    ".webp": ("image/webp", "WEBP"),
}
SAFE_FILENAME = re.compile(r"^[^\x00-\x1f\x7f]+$")


class PhotoService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.repository = RequestRepository(db)
        self.storage = LocalPhotoStorage(settings.storage_dir)
        self.max_size = settings.storage_max_file_size
        Image.MAX_IMAGE_PIXELS = settings.storage_max_image_pixels

    async def upload(self, request_id: UUID, file: UploadFile) -> RequestPhoto:
        if self.repository.get(request_id) is None:
            raise AppError(404, "NOT_FOUND", "Заявка не найдена.")
        filename = self._validate_filename(file.filename)
        extension = PurePath(filename).suffix.lower()
        expected_mime, expected_format = ALLOWED[extension]
        if file.content_type != expected_mime:
            raise AppError(415, "UNSUPPORTED_MEDIA_TYPE", "Расширение и MIME-тип фотографии не совпадают.")

        data = await file.read(self.max_size + 1)
        if len(data) > self.max_size:
            raise AppError(413, "PAYLOAD_TOO_LARGE", "Фотография превышает допустимый размер.")
        processed = self._validate_and_process(data, expected_format)
        photo_id = uuid4()
        original_key, processed_key = self.storage.save(
            str(photo_id), extension, data, processed
        )
        photo = RequestPhoto(
            photo_id=photo_id,
            request_id=request_id,
            storage_key=original_key,
            processed_storage_key=processed_key,
            original_filename=filename,
            mime_type=expected_mime,
            file_size=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )
        try:
            self.db.add(photo)
            self.db.commit()
        except OperationalError as exc:
            self.db.rollback()
            self.storage.delete(original_key, processed_key)
            raise AppError(503, "DB_UNAVAILABLE", "База данных временно недоступна.") from exc
        except IntegrityError as exc:
            self.db.rollback()
            self.storage.delete(original_key, processed_key)
            raise AppError(409, "CONFLICT", "Метаданные фотографии конфликтуют с текущим состоянием.") from exc
        return photo

    def get(self, photo_id: UUID) -> tuple[RequestPhoto, Path]:
        photo = self.repository.photo(photo_id)
        if photo is None:
            raise AppError(404, "NOT_FOUND", "Фотография не найдена.")
        key = photo.processed_storage_key or photo.storage_key
        return photo, self.storage.processed_path(key)

    @staticmethod
    def _validate_filename(filename: str | None) -> str:
        if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
            raise AppError(422, "VALIDATION_ERROR", "Имя файла фотографии недопустимо.")
        if not SAFE_FILENAME.fullmatch(filename):
            raise AppError(422, "VALIDATION_ERROR", "Имя файла фотографии недопустимо.")
        extension = PurePath(filename).suffix.lower()
        if extension not in ALLOWED:
            raise AppError(415, "UNSUPPORTED_MEDIA_TYPE", "Разрешены только JPG, PNG и WEBP.")
        return filename

    @staticmethod
    def _validate_and_process(data: bytes, expected_format: str) -> bytes:
        try:
            with Image.open(io.BytesIO(data)) as image:
                actual_format = (image.format or "").upper()
                if actual_format != expected_format:
                    raise AppError(415, "UNSUPPORTED_MEDIA_TYPE", "Фактический формат фотографии не совпадает с расширением.")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                if normalized.width <= 0 or normalized.height <= 0:
                    raise AppError(422, "VALIDATION_ERROR", "Размер фотографии недопустим.")
                output = io.BytesIO()
                normalized.save(output, format="JPEG", quality=90, optimize=True)
                return output.getvalue()
        except AppError:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise AppError(422, "VALIDATION_ERROR", "Фотография повреждена или не является изображением.") from exc
