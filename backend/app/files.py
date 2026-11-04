"""One validation policy for private evidence; client filenames never become paths."""
import io
from pathlib import PurePosixPath
from PIL import Image

MAX_BYTES = 10_485_760
MAX_PIXELS = 20_000_000
FORMATS = {"JPEG": ("image/jpeg", {".jpg", ".jpeg"}), "PNG": ("image/png", {".png"}),
           "WEBP": ("image/webp", {".webp"})}

def inspect_image(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Invalid image size")
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in FORMATS or image.width * image.height > MAX_PIXELS:
            raise ValueError("Invalid image")
        mime, extensions = FORMATS[image.format]
        width, height = image.size
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
    return mime, extensions, width, height

def validate_upload(data, filename, content_type):
    if not filename or len(filename) > 255 or any(c in filename for c in ("/", "\\", "\x00")):
        raise ValueError("Invalid filename")
    mime, extensions, _, _ = inspect_image(data)
    if content_type != mime or PurePosixPath(filename).suffix.lower() not in extensions:
        raise ValueError("Image type mismatch")
    return mime
