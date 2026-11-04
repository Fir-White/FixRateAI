"""Validated non-secret runtime options, with repository-relative private storage."""
from dataclasses import dataclass
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class RuntimeSettings:
    cookie_secure: bool
    photo_storage_root: Path
    photo_review_timeout_seconds: float
    forecast_timeout_seconds: float
    photo_review_max_files: int
    photo_review_max_bytes: int
    photo_review_provider: str = "clip"

    @classmethod
    def from_environment(cls):
        secure = os.environ.get("COOKIE_SECURE", "false").strip().lower()
        if secure not in ("true", "false"):
            raise ValueError("COOKIE_SECURE must be true or false")
        raw = os.environ.get("PHOTO_STORAGE_ROOT", "var/photos").strip()
        if not raw:
            raise ValueError("PHOTO_STORAGE_ROOT must not be empty")
        storage = (ROOT / raw).resolve()
        if storage.is_relative_to((ROOT / "frontend/dist").resolve()):
            raise ValueError("PHOTO_STORAGE_ROOT must be outside public frontend files")
        try:
            timeout = float(os.environ.get("PHOTO_REVIEW_TIMEOUT_SECONDS", "20"))
        except ValueError:
            raise ValueError("PHOTO_REVIEW_TIMEOUT_SECONDS must be a number") from None
        if not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise ValueError("PHOTO_REVIEW_TIMEOUT_SECONDS must be in (0, 120]")
        def number(name, default, maximum):
            try:
                value = float(os.environ.get(name, default))
            except ValueError:
                raise ValueError(name + " must be a number") from None
            if not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError(name + " is outside the supported range")
            return value
        def integer(name, default, minimum, maximum):
            try:
                value = int(os.environ.get(name, default))
            except ValueError:
                raise ValueError(name + " must be an integer") from None
            if not minimum <= value <= maximum:
                raise ValueError(name + " is outside the supported range")
            return value
        provider = os.environ.get("PHOTO_REVIEW_PROVIDER", "clip").strip().lower()
        if provider not in {"clip", "ollama"}:
            raise ValueError("PHOTO_REVIEW_PROVIDER must be clip or ollama")
        return cls(secure == "true", storage, timeout,
            number("FORECAST_TIMEOUT_SECONDS", "2", 5),
            integer("PHOTO_REVIEW_MAX_FILES", "20", 2, 100),
            integer("PHOTO_REVIEW_MAX_BYTES", "52428800", 1, 524288000), provider)
