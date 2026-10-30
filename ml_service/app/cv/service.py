"""Photo review service orchestrating image quality checks, guardrails, and CLIP Zero-Shot reasoning."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

from ml_service.app.core.config import settings
from ml_service.app.cv.classifier import CLIPZeroShotClassifier
from ml_service.app.cv.guardrails import VisualGuardrailPolicy
from ml_service.app.cv.quality import ImageQualityGuard
from ml_service.app.schemas import (
    ItemPhotoReview,
    PhotoReport,
    PhotoReviewRequest,
    PhotoReviewResult,
)

# Shared singleton instances
_QUALITY_GUARD = ImageQualityGuard()
_CLASSIFIER = CLIPZeroShotClassifier()

STANDARD_LIMITATIONS = [
    "Значения и фото показывают формат; результат зависит от освещения, фокуса и ракурса.",
    "Разница оценок нейросети не подтверждает скрытые операции, точность приборов или безопасность.",
    "Заключение AI не заменяет человеческое решение: окончательную приёмку выполняет инженер.",
    "Совпадение view_key не подтверждает совпадение объекта или ракурса; требуется проверка человеком.",
]


def review_photos(
    request: PhotoReviewRequest,
    photo_loader: Callable[[UUID], bytes],
    quality_guard: ImageQualityGuard | None = None,
    classifier: CLIPZeroShotClassifier | None = None,
) -> PhotoReviewResult:
    """Analyze execution photo reports against operation checklist and return structured PhotoReviewResult.

    Guarantees:
    - Never raises unhandled exceptions to caller (returns status='failed' with error_code).
    - Automatically marks hidden/metrological operations as 'not_verifiable'.
    - Flags blurry, poor lighting, or identical photos as 'uncertain'.
    - Returns structured scores and observable limitations.
    """
    start_time = time.perf_counter()
    q_guard = quality_guard or _QUALITY_GUARD
    clf = classifier or _CLASSIFIER

    item_results: list[ItemPhotoReview] = []

    try:
        # Group photos by checklist item
        photos_by_item: dict[UUID, list[PhotoReport]] = {}
        for photo in request.photos:
            photos_by_item.setdefault(photo.checklist_item_id, []).append(photo)

        # Process each checklist item in operation
        for item in request.operation.checklist:
            item_photos = photos_by_item.get(item.checklist_item_id, [])

            # 1. Guardrail for hidden / metrological operations
            if request.operation.code in ("1.5", "1.6") or not VisualGuardrailPolicy.is_item_verifiable(item):
                before_id = next((p.photo_id for p in item_photos if p.phase == "before"), None)
                after_id = next((p.photo_id for p in item_photos if p.phase == "after"), None)
                review = VisualGuardrailPolicy.create_not_verifiable_review(
                    checklist_item_id=item.checklist_item_id,
                    before_photo_id=before_id,
                    after_photo_id=after_id,
                )
                item_results.append(review)
                continue

            # 2. Check for required photo pairs
            before_photos = [p for p in item_photos if p.phase == "before"]
            after_photos = [p for p in item_photos if p.phase == "after"]

            if not before_photos or not after_photos:
                review = ItemPhotoReview(
                    checklist_item_id=item.checklist_item_id,
                    verdict="uncertain",
                    before_photo_id=before_photos[0].photo_id if before_photos else None,
                    after_photo_id=after_photos[0].photo_id if after_photos else None,
                    observation="Отсутствует обязательная пара фотографий 'до' и 'после' для пункта чек-листа.",
                    scores=[],
                )
                item_results.append(review)
                continue

            # Match first pair (support matching by view_key)
            before_p = before_photos[0]
            after_p = after_photos[0]
            for ap in after_photos:
                if ap.view_key == before_p.view_key:
                    after_p = ap
                    break

            # 3. Load photo bytes
            try:
                b_bytes = photo_loader(before_p.photo_id)
                a_bytes = photo_loader(after_p.photo_id)
            except Exception as load_err:
                review = ItemPhotoReview(
                    checklist_item_id=item.checklist_item_id,
                    verdict="uncertain",
                    before_photo_id=before_p.photo_id,
                    after_photo_id=after_p.photo_id,
                    observation=f"Не удалось загрузить файл из хранилища: {type(load_err).__name__}",
                    scores=[],
                )
                item_results.append(review)
                continue

            # 4. Consistency checks (identical photos, view_key mismatch)
            is_consistent, issue_msg = q_guard.verify_pair_consistency(
                before_report=before_p,
                after_report=after_p,
                before_bytes=b_bytes,
                after_bytes=a_bytes,
            )
            if not is_consistent:
                review = ItemPhotoReview(
                    checklist_item_id=item.checklist_item_id,
                    verdict="uncertain",
                    before_photo_id=before_p.photo_id,
                    after_photo_id=after_p.photo_id,
                    observation=f"Нарушение согласованности пары фото: {issue_msg}",
                    scores=[],
                )
                item_results.append(review)
                continue

            # 5. Technical image quality assessment (sharpness, lighting)
            b_qual = q_guard.assess_bytes(b_bytes)
            if not b_qual.is_acceptable:
                review = ItemPhotoReview(
                    checklist_item_id=item.checklist_item_id,
                    verdict="uncertain",
                    before_photo_id=before_p.photo_id,
                    after_photo_id=after_p.photo_id,
                    observation=f"Брак фото 'ДО': {b_qual.issue}",
                    scores=[],
                )
                item_results.append(review)
                continue

            a_qual = q_guard.assess_bytes(a_bytes)
            if not a_qual.is_acceptable:
                review = ItemPhotoReview(
                    checklist_item_id=item.checklist_item_id,
                    verdict="uncertain",
                    before_photo_id=before_p.photo_id,
                    after_photo_id=after_p.photo_id,
                    observation=f"Брак фото 'ПОСЛЕ': {a_qual.issue}",
                    scores=[],
                )
                item_results.append(review)
                continue

            # 6. Run Zero-Shot CLIP analysis
            if not clf.is_torch_active:
                return PhotoReviewResult(
                    schema_version="maintenance-0.1", data_origin=request.data_origin,
                    ai_review_id=uuid4(), execution_id=request.execution_id,
                    operation_version_id=request.operation.operation_version_id,
                    status="unavailable", model_ref=None,
                    prompt_set_version=settings.prompt_set_version,
                    input_photo_ids=[p.photo_id for p in request.photos], item_results=[],
                    limitations=STANDARD_LIMITATIONS, error_code="MODEL_NOT_READY",
                    elapsed_ms=max(1, int((time.perf_counter() - start_time) * 1000)),
                    created_at=datetime.now(timezone.utc),
                )
            item_review = clf.evaluate_pair(
                checklist_item_id=item.checklist_item_id,
                before_photo_id=before_p.photo_id,
                after_photo_id=after_p.photo_id,
                before_bytes=b_bytes,
                after_bytes=a_bytes,
            )
            item_results.append(item_review)

        # Determine overall review status
        if any(r.verdict == "uncertain" for r in item_results):
            overall_status = "uncertain"
        elif all(r.verdict == "not_verifiable" for r in item_results):
            overall_status = "not_verifiable"
        else:
            overall_status = "completed"

        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))

        return PhotoReviewResult(
            schema_version="maintenance-0.1",
            data_origin=request.data_origin,
            ai_review_id=uuid4(),
            execution_id=request.execution_id,
            operation_version_id=request.operation.operation_version_id,
            status=overall_status,
            model_ref=clf.model_ref if any(r.scores for r in item_results) else None,
            prompt_set_version=clf.prompt_set_version,
            input_photo_ids=[p.photo_id for p in request.photos],
            item_results=item_results,
            limitations=STANDARD_LIMITATIONS,
            error_code=None,
            elapsed_ms=elapsed_ms,
            created_at=datetime.now(timezone.utc),
        )

    except Exception as exc:
        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return PhotoReviewResult(
            schema_version="maintenance-0.1",
            data_origin=request.data_origin,
            ai_review_id=uuid4(),
            execution_id=request.execution_id,
            operation_version_id=request.operation.operation_version_id,
            status="failed",
            model_ref=None,
            prompt_set_version=request.prompt_set_version,
            input_photo_ids=[p.photo_id for p in request.photos],
            item_results=[],
            limitations=STANDARD_LIMITATIONS,
            error_code="PHOTO_REVIEW_FAILED",
            elapsed_ms=elapsed_ms,
            created_at=datetime.now(timezone.utc),
        )
