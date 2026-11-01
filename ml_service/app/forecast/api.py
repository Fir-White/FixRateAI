"""Explicit JSON boundary for condition recommendations and pluggable providers."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Callable
from pydantic import ValidationError
from .condition import ConditionRequest, Recommendation, DataQuality, assess_condition


def invoke(payload: str, provider: Callable[[ConditionRequest], object] | None = None,
           timeout_seconds: float = 5.0) -> Recommendation:
    """Validate provider output. Timeout limits waiting; it does not stop the worker."""
    empty = DataQuality(sufficient=False, available=[], missing=[], limitations=["Вход или ответ не обработан"])
    def failure(code: str) -> Recommendation:
        return Recommendation(status="failed", rationale="Рекомендация недоступна.", data_quality=empty,
                              uncertainty="Не оценена", error=code)
    try:
        request = ConditionRequest.model_validate_json(payload)
    except (ValidationError, ValueError):
        return failure("INVALID_INPUT")
    if timeout_seconds <= 0:
        return failure("INVALID_TIMEOUT")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(provider or assess_condition, request)
    try:
        result = future.result(timeout=timeout_seconds)
        if isinstance(result, Recommendation):
            return Recommendation.model_validate_json(result.model_dump_json())
        if isinstance(result, (str, bytes)):
            return Recommendation.model_validate_json(result)
        return Recommendation.model_validate(result)
    except TimeoutError:
        future.cancel()
        return failure("TIMEOUT")
    except (ValidationError, ValueError, TypeError):
        return failure("INVALID_RESPONSE")
    except Exception:
        return failure("PROVIDER_ERROR")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
