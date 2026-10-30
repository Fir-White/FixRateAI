"""Bounded wait and response validation for backend photo-review integrations."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from uuid import uuid4
from ml_service.app.schemas import PhotoReviewRequest, PhotoReviewResult
from .service import review_photos, STANDARD_LIMITATIONS


def invoke_review(request: PhotoReviewRequest, photo_loader, *, timeout_seconds=20.0,
                  comparability_confirmed=None, provider=None):
    """Timeout bounds the caller's wait, not execution; provider needs its own cancellation."""
    def failure(code):
        return PhotoReviewResult(schema_version="maintenance-0.1", data_origin=request.data_origin,
            ai_review_id=uuid4(), execution_id=request.execution_id,
            operation_version_id=request.operation.operation_version_id, status="failed", model_ref=None,
            prompt_set_version=request.prompt_set_version, input_photo_ids=[p.photo_id for p in request.photos],
            item_results=[], limitations=STANDARD_LIMITATIONS, error_code=code, elapsed_ms=0,
            created_at=datetime.now(timezone.utc))
    if timeout_seconds <= 0:
        return failure("INVALID_TIMEOUT")
    executor = ThreadPoolExecutor(max_workers=1)
    if provider is None:
        future = executor.submit(review_photos, request, photo_loader, comparability_confirmed=comparability_confirmed)
    else:
        future = executor.submit(provider, request, photo_loader)
    try:
        raw = future.result(timeout=timeout_seconds)
        if isinstance(raw, PhotoReviewResult):
            result = PhotoReviewResult.model_validate_json(raw.model_dump_json())
        elif isinstance(raw, (str, bytes)):
            result = PhotoReviewResult.model_validate_json(raw)
        else:
            result = PhotoReviewResult.model_validate(raw)
        if (result.execution_id != request.execution_id or result.operation_version_id != request.operation.operation_version_id
                or result.data_origin != request.data_origin or set(result.input_photo_ids) != {p.photo_id for p in request.photos}):
            return failure("INVALID_RESPONSE")
        item_ids = {item.checklist_item_id for item in request.operation.checklist}
        photo_ids = {p.photo_id for p in request.photos}
        if (any(item.checklist_item_id not in item_ids
                or (item.before_photo_id is not None and item.before_photo_id not in photo_ids)
                or (item.after_photo_id is not None and item.after_photo_id not in photo_ids)
                for item in result.item_results)
                or (result.status == "completed" and (not result.model_ref or result.error_code or not result.item_results))
                or (result.status in ("failed", "unavailable") and not result.error_code)):
            return failure("INVALID_RESPONSE")
        return result
    except TimeoutError:
        future.cancel()
        return failure("TIMEOUT")
    except Exception:
        return failure("INVALID_RESPONSE")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
