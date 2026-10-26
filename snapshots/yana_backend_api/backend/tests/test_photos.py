"""Приёмочные проверки валидации и устойчивого локального хранения фото."""
import io
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import UploadFile
from PIL import Image

from app.core.config import Settings
from app.core.errors import AppError
from app.models.requests import RepairRequest
from app.services.photo_service import PhotoService

REQUEST_ID = UUID("d5000000-0000-4000-8000-000000000001")


def image_bytes(format_name: str = "JPEG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, format=format_name)
    return output.getvalue()


class FakeDb:
    def __init__(self) -> None:
        self.photo = None

    def get(self, model, identifier):
        if model is RepairRequest:
            return RepairRequest(request_id=REQUEST_ID)
        return self.photo

    def add(self, photo) -> None:
        self.photo = photo

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_upload_and_get_survive_new_storage_instance(tmp_path: Path):
    db = FakeDb()
    settings = Settings(storage_dir=str(tmp_path))
    service = PhotoService(db, settings)
    upload = UploadFile(
        file=io.BytesIO(image_bytes()),
        filename="defect.jpg",
        headers={"content-type": "image/jpeg"},
    )

    photo = await service.upload(REQUEST_ID, upload)
    assert photo.file_size > 0
    assert photo.storage_key != photo.processed_storage_key
    assert (tmp_path / photo.storage_key).is_file()
    assert (tmp_path / photo.processed_storage_key).is_file()

    restarted = PhotoService(db, settings)
    _, processed_path = restarted.get(photo.photo_id)
    assert processed_path.is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type", "payload"),
    [
        ("defect.exe", "application/octet-stream", b"not an image"),
        ("../defect.jpg", "image/jpeg", image_bytes()),
        ("defect.jpg", "image/jpeg", b"corrupted"),
        ("defect.jpg", "image/png", image_bytes()),
    ],
    ids=[
        "unsupported-extension",
        "path-traversal-filename",
        "corrupted-image",
        "mime-extension-mismatch",
    ],
)
async def test_invalid_upload_is_rejected_without_database_write(
    tmp_path: Path, filename: str, content_type: str, payload: bytes
):
    db = FakeDb()
    service = PhotoService(db, Settings(storage_dir=str(tmp_path)))
    upload = UploadFile(
        file=io.BytesIO(payload),
        filename=filename,
        headers={"content-type": content_type},
    )

    with pytest.raises(AppError):
        await service.upload(REQUEST_ID, upload)
    assert db.photo is None
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
