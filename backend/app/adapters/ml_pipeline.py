"""HTTP-адаптер к ML Service.

Backend не знает реализаций CV, NLP и RAG: он передаёт версионированный JSON
контракт и сохраняет ответ ML без подмены отсутствующих данных.
"""
from typing import Any

import httpx

from app.core.errors import AppError


class MLPipelineAdapter:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            raise AppError(503, "UPSTREAM_UNAVAILABLE", "ML Service не настроен.")
        try:
            response = httpx.post(
                f"{self.base_url}/api/v1/process",
                json=payload,
                timeout=self.timeout_seconds,
            )
        except httpx.RequestError as exc:
            raise AppError(
                503,
                "UPSTREAM_UNAVAILABLE",
                "ML Service временно недоступен.",
            ) from exc
        if response.status_code >= 500:
            raise AppError(503, "UPSTREAM_UNAVAILABLE", "ML Service вернул ошибку.")
        if response.status_code >= 400:
            raise AppError(
                502,
                "UPSTREAM_INVALID_RESPONSE",
                "ML Service отклонил контракт обработки.",
            )
        try:
            result = response.json()
        except ValueError as exc:
            raise AppError(
                502,
                "UPSTREAM_INVALID_RESPONSE",
                "ML Service вернул некорректный JSON.",
            ) from exc
        if not isinstance(result, dict):
            raise AppError(502, "UPSTREAM_INVALID_RESPONSE", "Ответ ML Service не является объектом.")
        return result
