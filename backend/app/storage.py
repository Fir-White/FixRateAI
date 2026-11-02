"""Validation and safe path handling for locally stored photo evidence."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PIL.Image import DecompressionBombError, UnidentifiedImageError


MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
PHOTO_TYPES = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
}


class PhotoValidationError(ValueError):
    """Raised when an uploaded photo is not an allowed JPEG or PNG."""


def validate_photo(data: bytes, filename: str | None, content_type: str | None) -> str:
    """Validate size, filename extension, declared MIME and image contents."""
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise PhotoValidationError("Размер фото должен быть от 1 байта до 10 МиБ")
    if not filename or Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise PhotoValidationError("Имя файла должно быть простым именем")

    media = PHOTO_TYPES.get(Path(filename).suffix.lower())
    if media is None or content_type != media[0]:
        raise PhotoValidationError("Разрешены только JPEG и PNG с корректным MIME-типом")

    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != media[1] or image.width * image.height > MAX_PHOTO_PIXELS:
                raise PhotoValidationError("Недопустимое изображение")
            image.verify()
    except (DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise PhotoValidationError("Недопустимое изображение") from None
    return media[0]


def safe_storage_path(root: Path, storage_key: str) -> Path:
    """Resolve a storage key and reject paths outside the configured root."""
    resolved_root = root.resolve()
    path = (resolved_root / storage_key).resolve()
    if not path.is_relative_to(resolved_root):
        raise ValueError("storage key escapes the configured root")
    return path
