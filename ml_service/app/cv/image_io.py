"""Модуль безопасного чтения, валидации и нормализации изображений.

Предотвращает уязвимости (Decompression Bomb OOM), корректирует ориентацию EXIF
и гарантирует перевод изображения в цветовое пространство RGB.
"""
import io
from pathlib import Path
from typing import BinaryIO
from PIL import Image, ImageOps

from app.core.config import get_settings
from app.core.errors import InvalidImageError

# Поддерживаемые форматы изображений
ALLOWED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP"}


def configure_image_limits() -> None:
    """Устанавливает лимит максимального разрешения изображения (защита от Decompression Bomb)."""
    settings = get_settings()
    Image.MAX_IMAGE_PIXELS = settings.cv_max_image_pixels


def load_image(image_input: str | Path | bytes | BinaryIO) -> tuple[Image.Image, int, int]:
    """Безопасно загружает изображение, нормализует EXIF-ориентацию и возвращает в формате RGB.
    
    Args:
        image_input: Путь к файлу, байты или файловый объект.
        
    Returns:
        Кортеж (PIL.Image в режиме RGB, ширина в пикселях, высота в пикселях).
        
    Raises:
        InvalidImageError: Если файл повреждён, превышает лимиты или не является валидным изображением.
    """
    configure_image_limits()

    try:
        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.is_file():
                raise InvalidImageError(f"Файл изображения не найден: {path}")
            raw_bytes = path.read_bytes()
            stream = io.BytesIO(raw_bytes)
        elif isinstance(image_input, bytes):
            if len(image_input) == 0:
                raise InvalidImageError("Передан пустой поток байтов изображения")
            stream = io.BytesIO(image_input)
        else:
            raw_bytes = image_input.read()
            if len(raw_bytes) == 0:
                raise InvalidImageError("Передан пустой файловый объект изображения")
            stream = io.BytesIO(raw_bytes)

        with Image.open(stream) as img:
            img.verify()

        # Повторно открываем после verify(), т.к. verify() закрывает поток метаданных
        stream.seek(0)
        with Image.open(stream) as img:
            fmt = (img.format or "").upper()
            if fmt and fmt not in ALLOWED_FORMATS:
                raise InvalidImageError(f"Неподдерживаемый формат изображения: {fmt}. Разрешены: {ALLOWED_FORMATS}")

            # Коррекция поворота камеры по EXIF (если есть)
            transposed = ImageOps.exif_transpose(img)
            if transposed is None:
                transposed = img

            # Конвертируем в чистый RGB (удаляя альфа-канал RGBA и палитры P)
            rgb_image = transposed.convert("RGB")
            width, height = rgb_image.size

            if width <= 0 or height <= 0:
                raise InvalidImageError(f"Недопустимый размер изображения: {width}x{height}")

            return rgb_image, width, height

    except Image.DecompressionBombError as e:
        raise InvalidImageError(f"Изображение превышает максимальный безопасный лимит пикселей: {e}") from e
    except InvalidImageError:
        raise
    except Exception as e:
        raise InvalidImageError(f"Ошибка декодирования файла изображения: {e}") from e
