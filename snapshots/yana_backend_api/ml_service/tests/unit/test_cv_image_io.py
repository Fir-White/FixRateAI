"""Unit-тесты безопасной работы с изображениями (Pillow, EXIF, лимиты)."""
import io
import pytest
from PIL import Image
from app.cv.image_io import load_image
from app.core.errors import InvalidImageError


def create_test_image_bytes(width: int = 100, height: int = 100, fmt: str = "JPEG", color: str = "red") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_load_valid_jpeg_bytes():
    raw = create_test_image_bytes(200, 150, "JPEG")
    img, width, height = load_image(raw)
    assert width == 200
    assert height == 150
    assert img.mode == "RGB"


def test_load_valid_png_bytes():
    raw = create_test_image_bytes(50, 80, "PNG")
    img, width, height = load_image(raw)
    assert width == 50
    assert height == 80


def test_load_empty_bytes_raises():
    with pytest.raises(InvalidImageError, match="пустой поток байтов"):
        load_image(b"")


def test_load_corrupted_bytes_raises():
    corrupted = b"not_an_image_header_random_junk_bytes_12345"
    with pytest.raises(InvalidImageError, match="Ошибка декодирования"):
        load_image(corrupted)


def test_load_non_existent_file_raises(tmp_path):
    missing_file = tmp_path / "non_existent.jpg"
    with pytest.raises(InvalidImageError, match="Файл изображения не найден"):
        load_image(missing_file)


def test_load_valid_from_file_path(tmp_path):
    raw = create_test_image_bytes(120, 90, "JPEG")
    img_file = tmp_path / "test_photo.jpg"
    img_file.write_bytes(raw)

    img, width, height = load_image(img_file)
    assert width == 120
    assert height == 90
