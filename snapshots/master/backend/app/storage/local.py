"""Безопасное локальное хранилище оригиналов и обработанных изображений."""
import os
import tempfile
from pathlib import Path

from app.core.errors import AppError


class LocalPhotoStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.originals = self.root / "originals"
        self.processed = self.root / "processed"
        try:
            self.originals.mkdir(parents=True, exist_ok=True)
            self.processed.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppError(503, "STORAGE_UNAVAILABLE", "Хранилище фотографий недоступно.") from exc

    def _safe_path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise AppError(404, "NOT_FOUND", "Файл фотографии не найден.") from exc
        return candidate

    def save(self, photo_id: str, extension: str, original: bytes, processed: bytes) -> tuple[str, str]:
        original_key = f"originals/{photo_id}{extension}"
        processed_key = f"processed/{photo_id}.jpg"
        original_path = self._safe_path(original_key)
        processed_path = self._safe_path(processed_key)
        try:
            self._atomic_write(original_path, original)
            self._atomic_write(processed_path, processed)
        except OSError as exc:
            self.delete(original_key, processed_key)
            raise AppError(503, "STORAGE_UNAVAILABLE", "Хранилище фотографий недоступно.") from exc
        return original_key, processed_key

    def delete(self, *keys: str) -> None:
        for key in keys:
            path = self._safe_path(key)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def processed_path(self, key: str) -> Path:
        path = self._safe_path(key)
        if not path.is_file():
            raise AppError(404, "NOT_FOUND", "Файл фотографии не найден.")
        return path

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
