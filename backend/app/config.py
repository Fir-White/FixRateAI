"""Validated non-secret runtime options, with repository-relative private storage."""
from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import FrozenSet

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
    forecast_provider: str = "rf"
    active_roles: FrozenSet[str] = frozenset()
    assistant_agent_version: str = "v4"
    assistant_v3_pipeline: str = "v3"
    assistant_operator_steps: int = 8
    assistant_operator_output_tokens: int = 6000

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
        if provider not in {"clip", "ollama", "aitunnel"}:
            raise ValueError("PHOTO_REVIEW_PROVIDER must be clip, ollama or aitunnel")
        forecast_provider = os.environ.get("FORECAST_PROVIDER", "rf").strip().lower()
        if forecast_provider not in {"rf", "aitunnel"}:
            raise ValueError("FORECAST_PROVIDER must be rf or aitunnel")
        if provider == "aitunnel" or forecast_provider == "aitunnel":
            from ml_service.app.providers.aitunnel import AITunnelConfig
            if provider == "aitunnel":
                AITunnelConfig.from_environment("vision")
            if forecast_provider == "aitunnel":
                AITunnelConfig.from_environment("forecast")
        configured_roles = os.environ.get("FIXRATE_ACTIVE_ROLES", "").strip()
        active_roles = frozenset(
            role.strip() for role in configured_roles.split(",") if role.strip()
        )
        unknown_roles = active_roles.difference(
            {"director", "chief_engineer", "engineer", "admin", "dispatcher", "executor"}
        )
        if unknown_roles:
            raise ValueError(
                "FIXRATE_ACTIVE_ROLES contains unsupported roles: "
                + ", ".join(sorted(unknown_roles))
            )
        agent_version = os.environ.get("FIXRATE_ASSISTANT_AGENT_VERSION", "v4").strip().lower()
        if agent_version not in {"v2", "v3", "v4"}:
            raise ValueError("FIXRATE_ASSISTANT_AGENT_VERSION must be v2, v3 or v4")
        pipeline = os.environ.get("FIXRATE_ASSISTANT_V3_PIPELINE", "v3").strip().lower()
        if pipeline not in {"v3", "llm_dynamic", "erp_operator"} or (pipeline != "v3" and agent_version != "v3"):
            raise ValueError("FIXRATE_ASSISTANT_V3_PIPELINE must be v3, llm_dynamic or erp_operator with Agent v3 enabled")
        return cls(secure == "true", storage, timeout,
            number("FORECAST_TIMEOUT_SECONDS", "90" if forecast_provider == "aitunnel" else "2", 120 if forecast_provider == "aitunnel" else 5),
            integer("PHOTO_REVIEW_MAX_FILES", "20", 2, 100),
            integer("PHOTO_REVIEW_MAX_BYTES", "52428800", 1, 524288000),
            provider, forecast_provider, active_roles, agent_version, pipeline,
            integer("FIXRATE_ASSISTANT_OPERATOR_STEPS", "8", 1, 24),
            integer("FIXRATE_ASSISTANT_OPERATOR_OUTPUT_TOKENS", "6000", 500, 24000))
