"""Bounded wait and response validation for backend photo-review integrations."""
from queue import Queue, Empty
from threading import BoundedSemaphore, Thread
import math
import time
from datetime import datetime, timezone
from uuid import uuid4
from ml_service.app.schemas import PhotoReviewRequest, PhotoReviewResult
from .service import review_photos, STANDARD_LIMITATIONS


_slots = BoundedSemaphore(2)

def invoke_review(request: PhotoReviewRequest, photo_loader, *, timeout_seconds=20.0,
                  comparability_confirmed=None, provider=None, expected_model_ref=None):
    """Bound wait and concurrent providers; timed-out daemon workers cannot persist data."""
    started = time.monotonic()
    def failure(code):
        return PhotoReviewResult(schema_version="maintenance-0.1", data_origin=request.data_origin,
            ai_review_id=uuid4(), execution_id=request.execution_id,
            operation_version_id=request.operation.operation_version_id, status="failed", model_ref=None,
            prompt_set_version=request.prompt_set_version, input_photo_ids=[p.photo_id for p in request.photos],
            item_results=[], limitations=STANDARD_LIMITATIONS, error_code=code, elapsed_ms=int((time.monotonic()-started)*1000),
            created_at=datetime.now(timezone.utc))
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        return failure("INVALID_TIMEOUT")
    slots = _slots
    if not slots.acquire(blocking=False):
        return failure("PROVIDER_BUSY")
    queue = Queue(maxsize=1)
    provider_request = request.model_copy(deep=True)
    def run():
        try:
            raw = (review_photos(provider_request, photo_loader, comparability_confirmed=comparability_confirmed)
                   if provider is None else provider(provider_request, photo_loader))
            queue.put((True, raw))
        except BaseException:
            queue.put((False, None))
        finally:
            slots.release()
    try:
        Thread(target=run, daemon=True, name="fixrate-photo-review").start()
    except Exception:
        slots.release()
        return failure("PROVIDER_ERROR")
    try:
        ok, raw = queue.get(timeout=timeout_seconds)
    except Empty:
        return failure("TIMEOUT")
    if not ok:
        return failure("PROVIDER_ERROR")
    try:
        if isinstance(raw, PhotoReviewResult):
            result = PhotoReviewResult.model_validate_json(raw.model_dump_json())
        elif isinstance(raw, (str, bytes)):
            result = PhotoReviewResult.model_validate_json(raw)
        else:
            result = PhotoReviewResult.model_validate(raw)
        if (result.execution_id != request.execution_id or result.operation_version_id != request.operation.operation_version_id
                or result.data_origin != request.data_origin or result.prompt_set_version != request.prompt_set_version
                or len(result.input_photo_ids) != len(request.photos)
                or set(result.input_photo_ids) != {p.photo_id for p in request.photos}
                or (result.model_ref and expected_model_ref and result.model_ref != expected_model_ref)):
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
    except Exception:
        return failure("INVALID_RESPONSE")
