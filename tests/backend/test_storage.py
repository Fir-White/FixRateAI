import io
from pathlib import Path

import pytest
from PIL import Image

from app.storage import PhotoValidationError, safe_storage_path, validate_photo


def image_bytes(format_name: str) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(stream, format=format_name)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("filename", "content_type", "format_name"),
    [("photo.jpg", "image/jpeg", "JPEG"), ("photo.jpeg", "image/jpeg", "JPEG"),
     ("photo.PNG", "image/png", "PNG")],
)
def test_validate_photo_accepts_jpeg_and_png(filename, content_type, format_name):
    assert validate_photo(image_bytes(format_name), filename, content_type) == content_type


@pytest.mark.parametrize(
    ("filename", "content_type", "format_name"),
    [("photo.webp", "image/webp", "WEBP"), ("photo.jpg", "image/png", "JPEG"),
     ("photo.png", "image/png", "JPEG"), ("photo.txt", "image/jpeg", "JPEG")],
)
def test_validate_photo_rejects_wrong_type_or_extension(filename, content_type, format_name):
    with pytest.raises(PhotoValidationError):
        validate_photo(image_bytes(format_name), filename, content_type)


def test_validate_photo_rejects_path_like_filename():
    with pytest.raises(PhotoValidationError):
        validate_photo(image_bytes("PNG"), "..\\outside.png", "image/png")


def test_validate_photo_rejects_oversized_payload():
    with pytest.raises(PhotoValidationError, match="10 МиБ"):
        validate_photo(b"x" * (10 * 1024 * 1024 + 1), "photo.png", "image/png")


def test_safe_storage_path_rejects_path_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        safe_storage_path(tmp_path, "../outside.jpg")
    assert safe_storage_path(tmp_path, "site/photo").parent == tmp_path / "site"
