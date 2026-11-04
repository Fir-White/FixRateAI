"""Unit and integration tests for Computer Vision module (FX26-ML04, FX26-ML05)."""
from __future__ import annotations

import io
from uuid import UUID
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from ml_service.app.cv.classifier import CLIPZeroShotClassifier
from ml_service.app.cv.guardrails import VisualGuardrailPolicy
from ml_service.app.cv.quality import ImageQualityGuard
from ml_service.app.cv.service import review_photos
from ml_service.app.schemas import ChecklistItem, PhotoReviewRequest


def make_test_jpeg(kind: str = "sharp") -> bytes:
    """Helper creating synthetic test JPEG images."""
    if kind == "dark":
        img = Image.new("RGB", (150, 150), color=(5, 5, 5))
    elif kind == "bright":
        img = Image.new("RGB", (150, 150), color=(252, 252, 252))
    elif kind == "blur":
        img = Image.new("RGB", (150, 150), color=(128, 128, 128))
        draw = ImageDraw.Draw(img)
        for i in range(10, 140, 10):
            draw.rectangle([i, i, i + 8, i + 8], fill=(255, 255, 255))
        img = img.filter(ImageFilter.GaussianBlur(radius=10))
    elif kind == "clean_serviced":
        # Sharp high-brightness clean surface
        img = Image.new("RGB", (150, 150), color=(190, 190, 190))
        draw = ImageDraw.Draw(img)
        for i in range(10, 140, 10):
            draw.rectangle([i, 10, i + 5, 140], fill=(245, 245, 245))
            draw.line([0, i, 150, i], fill=(20, 20, 20), width=1)
    else:  # dirty / initial state
        img = Image.new("RGB", (150, 150), color=(80, 80, 80))
        draw = ImageDraw.Draw(img)
        for i in range(10, 140, 10):
            draw.rectangle([i, 10, i + 5, 140], fill=(30, 30, 30))
            draw.line([0, i, 150, i], fill=(160, 160, 160), width=1)

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_quality_guard_sharpness_and_blur():
    """Verify ImageQualityGuard distinguishes sharp edges from blurred images."""
    guard = ImageQualityGuard()
    sharp_bytes = make_test_jpeg("clean_serviced")
    blur_bytes = make_test_jpeg("blur")

    sharp_res = guard.assess_bytes(sharp_bytes)
    blur_res = guard.assess_bytes(blur_bytes)

    assert sharp_res.is_acceptable is True
    assert sharp_res.laplacian_var >= 100.0
    assert sharp_res.issue is None

    assert blur_res.is_acceptable is False
    assert blur_res.laplacian_var < 100.0
    assert "смазано" in blur_res.issue


def test_quality_guard_lighting_checks():
    """Verify ImageQualityGuard rejects pitch black and washed-out overexposed images."""
    guard = ImageQualityGuard()
    dark_bytes = make_test_jpeg("dark")
    bright_bytes = make_test_jpeg("bright")

    dark_res = guard.assess_bytes(dark_bytes)
    bright_res = guard.assess_bytes(bright_bytes)

    assert dark_res.is_acceptable is False
    assert "Недостаточная освещённость" in dark_res.issue

    assert bright_res.is_acceptable is False
    assert "Пересвет" in bright_res.issue or "смазано" in bright_res.issue


def test_pair_consistency_rejects_identical_photos(canonical_photo_review_request: PhotoReviewRequest):
    """Verify S11: Identical photo bytes or matching SHA-256 are flagged as inconsistent."""
    guard = ImageQualityGuard()
    p1 = canonical_photo_review_request.photos[0]
    p2 = canonical_photo_review_request.photos[1]
    same_bytes = make_test_jpeg("clean_serviced")

    # Byte-level duplicate
    ok, issue = guard.verify_pair_consistency(p1, p2, same_bytes, same_bytes)
    assert ok is False
    assert "тождественное содержимое" in issue or "идентичные" in issue


def test_pair_consistency_rejects_view_key_mismatch(canonical_photo_review_request: PhotoReviewRequest):
    """Verify S11: Different view angles are flagged as inconsistent."""
    guard = ImageQualityGuard()
    p1 = canonical_photo_review_request.photos[0]
    p2 = canonical_photo_review_request.photos[1]

    # Modify view_key
    p2_modified = p2.model_copy(update={"view_key": "valve-angle-right-45"})
    b1 = make_test_jpeg("dirty")
    b2 = make_test_jpeg("clean_serviced")

    ok, issue = guard.verify_pair_consistency(p1, p2_modified, b1, b2)
    assert ok is False
    assert "Несовпадающий ракурс" in issue


def test_visual_guardrail_hidden_operations():
    """Verify S12 / P0-16: Hidden operations (not_verifiable) are unconditionally isolated."""
    hidden_item = ChecklistItem(
        checklist_item_id=UUID("00000000-0000-4000-8000-000000000099"),
        text="Выпустить воздух из системы отопления",
        answer_kind="boolean",
        unit=None,
        required=True,
        visual_verifiability="not_verifiable",
        photo_required=False,
    )

    assert VisualGuardrailPolicy.is_item_verifiable(hidden_item) is False

    review = VisualGuardrailPolicy.create_not_verifiable_review(hidden_item.checklist_item_id)
    assert review.verdict == "not_verifiable"
    assert review.scores == []
    assert "скрытого характера" in review.observation


def test_review_photos_successful_flow(canonical_photo_review_request: PhotoReviewRequest):
    """Verify S10 / P0-16: End-to-end photo review for cleaning operation."""
    dirty_bytes = make_test_jpeg("dirty")
    clean_bytes = make_test_jpeg("clean_serviced")

    # In-memory photo storage
    storage = {
        canonical_photo_review_request.photos[0].photo_id: dirty_bytes,
        canonical_photo_review_request.photos[1].photo_id: clean_bytes,
    }

    class FakeClassifier:
        is_torch_active = True
        model_name = "test:fake-classifier"
        prompt_set_version = "test-v1"

        def evaluate_pair(self, **kwargs):
            from ml_service.app.schemas import ItemPhotoReview
            return ItemPhotoReview(checklist_item_id=kwargs["checklist_item_id"], verdict="visible_change",
                                   before_photo_id=kwargs["before_photo_id"], after_photo_id=kwargs["after_photo_id"],
                                   observation="Тестовый ответ", scores=[])

    result = review_photos(canonical_photo_review_request, photo_loader=lambda pid: storage[pid], classifier=FakeClassifier(), comparability_confirmed=lambda before, after: True)

    assert result.status == "completed"
    assert result.model_ref is None  # no model scores in fake response
    assert result.error_code is None
    assert len(result.item_results) == 1
    assert result.item_results[0].verdict in ("visible_change", "no_visible_change")
    assert result.item_results[0].scores == []
    assert len(result.limitations) >= 1
    assert result.elapsed_ms >= 0


def test_same_view_key_alone_does_not_prove_comparability(canonical_photo_review_request):
    from ml_service.app.schemas import ItemPhotoReview
    class Classifier:
        is_torch_active = True
        prompt_set_version = "test-v1"
        def evaluate_pair(self, **kw):
            return ItemPhotoReview(checklist_item_id=kw["checklist_item_id"], verdict="visible_change",
                before_photo_id=kw["before_photo_id"], after_photo_id=kw["after_photo_id"],
                observation="test", scores=[])
    photos = canonical_photo_review_request.photos
    data = {photos[0].photo_id: make_test_jpeg("dirty"), photos[1].photo_id: make_test_jpeg("clean_serviced")}
    result = review_photos(canonical_photo_review_request, lambda pid: data[pid], classifier=Classifier())
    assert result.status == "uncertain" and result.item_results[0].verdict == "uncertain"


def test_missing_clip_is_unavailable(canonical_photo_review_request):
    class MissingClassifier:
        is_torch_active = False
    photos = canonical_photo_review_request.photos
    storage = {photos[0].photo_id: make_test_jpeg("dirty"), photos[1].photo_id: make_test_jpeg("clean_serviced")}
    result = review_photos(canonical_photo_review_request, lambda pid: storage[pid], classifier=MissingClassifier())
    assert result.status == "unavailable"
    assert result.error_code == "MODEL_NOT_READY"
    assert result.model_ref is None


def test_real_classifier_with_missing_weights_is_unavailable(canonical_photo_review_request):
    photos = canonical_photo_review_request.photos
    data = {photos[0].photo_id: make_test_jpeg("dirty"), photos[1].photo_id: make_test_jpeg("clean_serviced")}
    classifier = CLIPZeroShotClassifier(model_name="missing-local-model-for-test", revision="missing")
    result = review_photos(canonical_photo_review_request, lambda pid: data[pid], classifier=classifier)
    assert result.status == "unavailable" and result.error_code == "MODEL_NOT_READY"
    assert result.model_ref is None


def test_mismatched_view_is_uncertain_at_service_boundary(canonical_photo_review_request):
    req = canonical_photo_review_request
    photos = [req.photos[0], req.photos[1].model_copy(update={"view_key": "other-angle"})]
    req = req.model_copy(update={"photos": photos})
    data = {photos[0].photo_id: make_test_jpeg("dirty"), photos[1].photo_id: make_test_jpeg("clean_serviced")}
    result = review_photos(req, lambda pid: data[pid])
    assert result.status == "uncertain" and result.item_results[0].verdict == "uncertain"


def test_invalid_model_response_returns_failed(canonical_photo_review_request):
    class InvalidClassifier:
        is_torch_active = True
        def evaluate_pair(self, **kwargs):
            return {"verdict": "not-a-valid-verdict"}
    photos = canonical_photo_review_request.photos
    data = {photos[0].photo_id: make_test_jpeg("dirty"), photos[1].photo_id: make_test_jpeg("clean_serviced")}
    result = review_photos(canonical_photo_review_request, lambda pid: data[pid], classifier=InvalidClassifier())
    assert result.status == "failed" and result.error_code == "PHOTO_REVIEW_FAILED"


def test_review_adapter_timeout_and_invalid_json(canonical_photo_review_request):
    import time
    from ml_service.app.cv.api import invoke_review
    def slow(*args):
        time.sleep(0.05)
    req = canonical_photo_review_request
    assert invoke_review(req, lambda _: b"", provider=slow, timeout_seconds=0.001).error_code == "TIMEOUT"
    assert invoke_review(req, lambda _: b"", provider=lambda *args: "{broken").error_code == "INVALID_RESPONSE"


def test_review_photos_blurry_yields_uncertain(canonical_photo_review_request: PhotoReviewRequest):
    """Verify S11: Blurry photo produces item verdict 'uncertain' and overall 'uncertain'."""
    dirty_bytes = make_test_jpeg("dirty")
    blurry_bytes = make_test_jpeg("blur")

    storage = {
        canonical_photo_review_request.photos[0].photo_id: dirty_bytes,
        canonical_photo_review_request.photos[1].photo_id: blurry_bytes,
    }

    result = review_photos(canonical_photo_review_request, photo_loader=lambda pid: storage[pid])

    assert result.status == "uncertain"
    assert result.item_results[0].verdict == "uncertain"
    assert "смазано" in result.item_results[0].observation


def test_review_photos_missing_phase(canonical_photo_review_request: PhotoReviewRequest):
    """Verify missing before/after pair produces verdict 'uncertain'."""
    # Modify request so both photos are phase 'before'
    photos_same_phase = [
        canonical_photo_review_request.photos[0],
        canonical_photo_review_request.photos[1].model_copy(update={"phase": "before"}),
    ]
    req_modified = canonical_photo_review_request.model_copy(update={"photos": photos_same_phase})

    storage = {
        p.photo_id: make_test_jpeg("clean_serviced") for p in photos_same_phase
    }

    result = review_photos(req_modified, photo_loader=lambda pid: storage[pid])

    assert result.status == "uncertain"
    assert result.item_results[0].verdict == "uncertain"
    assert "Отсутствует обязательная пара" in result.item_results[0].observation


def test_review_photos_with_hidden_checklist_item(canonical_photo_review_request: PhotoReviewRequest):
    """Verify operation with hidden checklist item yields 'not_verifiable'."""
    hidden_item = ChecklistItem(
        checklist_item_id=UUID("00000000-0000-4000-8000-000000000007"),
        text="Проверка приборов измерения температуры и давления",
        answer_kind="number",
        unit="bar",
        required=True,
        visual_verifiability="not_verifiable",
        photo_required=False,
    )
    op_modified = canonical_photo_review_request.operation.model_copy(
        update={"checklist": [hidden_item]}
    )
    req_modified = canonical_photo_review_request.model_copy(update={"operation": op_modified})

    storage = {
        p.photo_id: make_test_jpeg("clean_serviced") for p in req_modified.photos
    }

    result = review_photos(req_modified, photo_loader=lambda pid: storage[pid])

    assert result.status == "not_verifiable"
    assert result.item_results[0].verdict == "not_verifiable"
    assert "скрытого характера" in result.item_results[0].observation


def test_review_photos_loader_failure_handling(canonical_photo_review_request: PhotoReviewRequest):
    """Verify storage load error returns 'uncertain' without 500 unhandled crash."""
    def broken_loader(pid: UUID):
        raise FileNotFoundError("Storage disk disconnected")

    result = review_photos(canonical_photo_review_request, photo_loader=broken_loader)

    assert result.status == "uncertain"
    assert result.item_results[0].verdict == "uncertain"
    assert "Не удалось загрузить" in result.item_results[0].observation


def test_quality_guard_large_image_downscaling():
    """Verify ImageQualityGuard downscales oversized images (>1280px) safely to preserve memory."""
    img = Image.new("RGB", (1600, 1400), color=(180, 180, 180))
    draw = ImageDraw.Draw(img)
    for i in range(100, 1300, 100):
        draw.line([(i, 0), (i, 1400)], fill=(20, 20, 20), width=4)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    large_bytes = buf.getvalue()

    guard = ImageQualityGuard()
    res = guard.assess_bytes(large_bytes)
    assert res.is_acceptable is True
    assert res.laplacian_var > 100.0
    assert 50.0 <= res.mean_brightness <= 220.0


def test_pair_consistency_different_lengths(canonical_photo_review_request: PhotoReviewRequest):
    """Verify pair consistency passes when photos differ in byte length without redundant hashing."""
    guard = ImageQualityGuard()
    p1 = canonical_photo_review_request.photos[0]
    p2 = canonical_photo_review_request.photos[1]
    b1 = make_test_jpeg("dirty")
    b2 = make_test_jpeg("clean_serviced")
    assert len(b1) != len(b2)

    ok, issue = guard.verify_pair_consistency(p1, p2, b1, b2)
    assert ok is True
    assert issue is None


def test_classifier_warmup_and_batch_api():
    """Verify classifier warmup and batch inference error handling."""
    classifier = CLIPZeroShotClassifier(model_name="missing-local-model", revision="missing")
    assert classifier.warmup() is False
    assert classifier._infer_batch([]) == []
    with pytest.raises(RuntimeError, match="CLIP model unavailable"):
        classifier._infer_batch([b"fake-bytes"])


def test_review_adapter_bounds_hung_providers_and_recovers(canonical_photo_review_request,monkeypatch):
    from threading import BoundedSemaphore,Event
    import ml_service.app.cv.api as adapter
    slots=BoundedSemaphore(2)
    monkeypatch.setattr(adapter,'_slots',slots)
    release=Event()
    req=canonical_photo_review_request
    def blocked(*args):
        release.wait(2)
        return '{invalid}'
    try:
        for _ in range(2):
            result=adapter.invoke_review(req,lambda _:b'',provider=blocked,timeout_seconds=.005)
            assert result.error_code=='TIMEOUT' and not result.item_results and result.model_ref is None
        result=adapter.invoke_review(req,lambda _:b'',provider=blocked,timeout_seconds=.005)
        assert result.error_code=='PROVIDER_BUSY'
    finally:
        release.set()
    assert slots.acquire(timeout=2)
    assert slots.acquire(timeout=2)
    slots.release(); slots.release()
    def broken(*args): raise RuntimeError('private-provider-token')
    result=adapter.invoke_review(req,lambda _:b'',provider=broken)
    assert result.error_code=='PROVIDER_ERROR'
    assert 'private-provider-token' not in result.model_dump_json()
    assert adapter.invoke_review(req,lambda _:b'',provider=lambda *a:'{invalid}').error_code=='INVALID_RESPONSE'


def test_review_adapter_rejects_different_prompt_version(canonical_photo_review_request):
    from datetime import datetime,timezone
    from uuid import uuid4
    from ml_service.app.cv.api import invoke_review
    from ml_service.app.schemas import PhotoReviewResult
    req=canonical_photo_review_request
    result=PhotoReviewResult(schema_version=req.schema_version,data_origin=req.data_origin,
        ai_review_id=uuid4(),execution_id=req.execution_id,operation_version_id=req.operation.operation_version_id,
        status='unavailable',model_ref=None,prompt_set_version='unapproved-prompts-v999',
        input_photo_ids=[p.photo_id for p in req.photos],item_results=[],limitations=['Test-only provider'],
        error_code='MODEL_NOT_READY',elapsed_ms=1,created_at=datetime.now(timezone.utc))
    actual=invoke_review(req,lambda _:b'',provider=lambda *a:result)
    assert actual.error_code=='INVALID_RESPONSE'
    assert actual.prompt_set_version==req.prompt_set_version


def test_review_adapter_rejects_unapproved_model_version(canonical_photo_review_request):
    from datetime import datetime,timezone
    from uuid import uuid4
    from ml_service.app.cv.api import invoke_review
    from ml_service.app.schemas import PhotoReviewResult
    req=canonical_photo_review_request
    result=PhotoReviewResult(schema_version=req.schema_version,data_origin=req.data_origin,
        ai_review_id=uuid4(),execution_id=req.execution_id,operation_version_id=req.operation.operation_version_id,
        status='uncertain',model_ref='unapproved-model@999',prompt_set_version=req.prompt_set_version,
        input_photo_ids=[p.photo_id for p in req.photos],item_results=[],limitations=['Test-only provider'],
        error_code=None,elapsed_ms=1,created_at=datetime.now(timezone.utc))
    actual=invoke_review(req,lambda _:b'',provider=lambda *a:result,expected_model_ref='approved-model@1')
    assert actual.error_code=='INVALID_RESPONSE' and actual.model_ref is None
