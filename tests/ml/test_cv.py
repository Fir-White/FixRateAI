"""Unit and integration tests for Computer Vision module (AI Tunnel vision, quality guards, and boundaries)."""
from __future__ import annotations

import io
from uuid import UUID
import pytest
from PIL import Image, ImageDraw, ImageFilter

from ml_service.app.cv.aitunnel import review_cloud_photos
from ml_service.app.cv.api import invoke_review
from ml_service.app.cv.guardrails import VisualGuardrailPolicy
from ml_service.app.cv.quality import ImageQualityGuard
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
        img = Image.new("RGB", (150, 150), color=(190, 190, 190))
        draw = ImageDraw.Draw(img)
        for i in range(10, 140, 10):
            draw.rectangle([i, 10, i + 5, 140], fill=(245, 245, 245))
            draw.line([0, i, 150, i], fill=(20, 20, 20), width=1)
    else:
        img = Image.new("RGB", (150, 150), color=(80, 80, 80))
        draw = ImageDraw.Draw(img)
        for i in range(10, 140, 10):
            draw.rectangle([i, 10, i + 5, 140], fill=(30, 30, 30))
            draw.line([0, i, 150, i], fill=(160, 160, 160), width=1)

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_quality_guard_sharpness_and_blur():
    guard = ImageQualityGuard()
    sharp_res = guard.assess_bytes(make_test_jpeg("clean_serviced"))
    blur_res = guard.assess_bytes(make_test_jpeg("blur"))
    assert sharp_res.is_acceptable is True and sharp_res.laplacian_var >= 100.0
    assert blur_res.is_acceptable is False and "смазано" in blur_res.issue


def test_quality_guard_lighting_checks():
    guard = ImageQualityGuard()
    dark_res = guard.assess_bytes(make_test_jpeg("dark"))
    bright_res = guard.assess_bytes(make_test_jpeg("bright"))
    assert dark_res.is_acceptable is False and "Недостаточная освещённость" in dark_res.issue
    assert bright_res.is_acceptable is False and ("Пересвет" in bright_res.issue or "смазано" in bright_res.issue)


def test_pair_consistency_rejects_identical_photos(canonical_photo_review_request: PhotoReviewRequest):
    guard = ImageQualityGuard()
    p1, p2 = canonical_photo_review_request.photos[:2]
    same_bytes = make_test_jpeg("clean_serviced")
    ok, issue = guard.verify_pair_consistency(p1, p2, same_bytes, same_bytes)
    assert ok is False and ("тождественное содержимое" in issue or "идентичные" in issue)


def test_pair_consistency_rejects_view_key_mismatch(canonical_photo_review_request: PhotoReviewRequest):
    guard = ImageQualityGuard()
    p1, p2 = canonical_photo_review_request.photos[:2]
    p2_modified = p2.model_copy(update={"view_key": "valve-angle-right-45"})
    ok, issue = guard.verify_pair_consistency(p1, p2_modified, make_test_jpeg("dirty"), make_test_jpeg("clean_serviced"))
    assert ok is False and "Несовпадающий ракурс" in issue


def test_pair_consistency_rejects_different_equipment(canonical_photo_review_request: PhotoReviewRequest):
    guard = ImageQualityGuard()
    p1, p2 = canonical_photo_review_request.photos[:2]
    p2_other = p2.model_copy(update={"equipment_id": UUID("00000000-0000-4000-8000-000000000999")})
    ok, issue = guard.verify_pair_consistency(p1, p2_other, make_test_jpeg("dirty"), make_test_jpeg("clean_serviced"))
    assert ok is False and "разному оборудованию" in issue


def test_visual_guardrail_hidden_operations():
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
    assert review.verdict == "not_verifiable" and review.scores == [] and "скрытого характера" in review.observation


def test_invoke_review_without_provider_returns_unavailable_never_clip(canonical_photo_review_request: PhotoReviewRequest):
    result = invoke_review(canonical_photo_review_request, lambda _: make_test_jpeg("dirty"), provider=None)
    assert result.status == "unavailable"
    assert result.error_code == "MODEL_NOT_READY"
    assert result.model_ref is None
    assert result.item_results == []


def test_review_cloud_photos_missing_key_has_no_clip_fallback(canonical_photo_review_request: PhotoReviewRequest, monkeypatch):
    monkeypatch.delenv("AITUNNEL_API_KEY", raising=False)
    monkeypatch.delenv("AI_TUNNEL_API_KEY", raising=False)
    photos = canonical_photo_review_request.photos
    storage = {photos[0].photo_id: make_test_jpeg("dirty"), photos[1].photo_id: make_test_jpeg("clean_serviced")}
    result = review_cloud_photos(canonical_photo_review_request, lambda pid: storage[pid])
    assert result.status == "unavailable"
    assert result.error_code == "AITUNNEL_NOT_CONFIGURED"
    assert result.model_ref is None
    assert result.item_results == []


def test_review_cloud_photos_blurry_yields_uncertain_without_calling_model(canonical_photo_review_request: PhotoReviewRequest):
    from tests.ml.test_local_vision import FixtureClient
    client = FixtureClient()
    storage = {
        canonical_photo_review_request.photos[0].photo_id: make_test_jpeg("dirty"),
        canonical_photo_review_request.photos[1].photo_id: make_test_jpeg("blur"),
    }
    result = review_cloud_photos(canonical_photo_review_request, lambda pid: storage[pid], client=client)
    assert result.status == "uncertain" and client.calls == 0
    assert result.item_results[0].verdict == "uncertain"
    assert "смазано" in result.item_results[0].observation


def test_review_cloud_photos_missing_phase_for_required_item(canonical_photo_review_request: PhotoReviewRequest):
    from tests.ml.test_local_vision import FixtureClient
    photos_same = [
        canonical_photo_review_request.photos[0],
        canonical_photo_review_request.photos[1].model_copy(update={"phase": "before"}),
    ]
    req = canonical_photo_review_request.model_copy(update={"photos": photos_same})
    storage = {p.photo_id: make_test_jpeg("clean_serviced") for p in photos_same}
    result = review_cloud_photos(req, lambda pid: storage[pid], client=FixtureClient())
    assert result.status == "uncertain"
    assert result.item_results[0].verdict == "uncertain"


def test_review_cloud_photos_optional_single_photo_calls_assess_single(canonical_photo_review_request: PhotoReviewRequest):
    from tests.ml.test_local_vision import assessment, FixtureClient
    req = canonical_photo_review_request.model_copy(deep=True)
    req.operation.checklist[0].photo_required = False
    req = PhotoReviewRequest.model_validate_json(req.model_copy(update={"photos": [req.photos[0]]}).model_dump_json())

    class SingleClient(FixtureClient):
        single_calls = 0
        def assess_single(self, request, item, blob, phase):
            self.single_calls += 1
            return assessment(conclusion="insufficient_evidence", comparable="uncertain", summary="Виден корпус оборудования.")

    client = SingleClient()
    result = review_cloud_photos(req, lambda _: make_test_jpeg("dirty"), client=client)
    assert client.single_calls == 1
    assert result.status == "uncertain"
    assert result.item_results[0].visual_assessment is not None
    assert "Виден корпус оборудования" in result.item_results[0].observation


def test_review_adapter_timeout_and_invalid_json(canonical_photo_review_request):
    import time
    def slow(*args):
        time.sleep(0.05)
    req = canonical_photo_review_request
    assert invoke_review(req, lambda _: b"", provider=slow, timeout_seconds=0.001).error_code == "TIMEOUT"
    assert invoke_review(req, lambda _: b"", provider=lambda *args: "{broken").error_code == "INVALID_RESPONSE"


def test_quality_guard_large_image_downscaling():
    img = Image.new("RGB", (1600, 1400), color=(180, 180, 180))
    draw = ImageDraw.Draw(img)
    for i in range(100, 1300, 100):
        draw.line([(i, 0), (i, 1400)], fill=(20, 20, 20), width=4)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    res = ImageQualityGuard().assess_bytes(buf.getvalue())
    assert res.is_acceptable is True and res.laplacian_var > 100.0 and 50.0 <= res.mean_brightness <= 220.0


def test_pair_consistency_different_lengths(canonical_photo_review_request: PhotoReviewRequest):
    guard = ImageQualityGuard()
    p1, p2 = canonical_photo_review_request.photos[:2]
    b1, b2 = make_test_jpeg("dirty"), make_test_jpeg("clean_serviced")
    assert len(b1) != len(b2) and guard.verify_pair_consistency(p1, p2, b1, b2) == (True, None)


def test_review_adapter_bounds_hung_providers_and_recovers(canonical_photo_review_request, monkeypatch):
    from threading import BoundedSemaphore, Event
    import ml_service.app.cv.api as adapter
    slots = BoundedSemaphore(2)
    monkeypatch.setattr(adapter, "_slots", slots)
    release = Event()
    req = canonical_photo_review_request
    def blocked(*args):
        release.wait(2)
        return "{invalid}"
    try:
        for _ in range(2):
            result = adapter.invoke_review(req, lambda _: b"", provider=blocked, timeout_seconds=0.005)
            assert result.error_code == "TIMEOUT" and not result.item_results and result.model_ref is None
        result = adapter.invoke_review(req, lambda _: b"", provider=blocked, timeout_seconds=0.005)
        assert result.error_code == "PROVIDER_BUSY"
    finally:
        release.set()
    assert slots.acquire(timeout=2) and slots.acquire(timeout=2)
    slots.release(); slots.release()
    def broken(*args): raise RuntimeError("private-provider-token")
    result = adapter.invoke_review(req, lambda _: b"", provider=broken)
    assert result.error_code == "PROVIDER_ERROR" and "private-provider-token" not in result.model_dump_json()
    assert adapter.invoke_review(req, lambda _: b"", provider=lambda *a: "{invalid}").error_code == "INVALID_RESPONSE"


def test_review_adapter_rejects_different_prompt_version(canonical_photo_review_request):
    from datetime import datetime, timezone
    from uuid import uuid4
    from ml_service.app.schemas import PhotoReviewResult
    req = canonical_photo_review_request
    result = PhotoReviewResult(schema_version=req.schema_version, data_origin=req.data_origin,
        ai_review_id=uuid4(), execution_id=req.execution_id, operation_version_id=req.operation.operation_version_id,
        status="unavailable", model_ref=None, prompt_set_version="unapproved-prompts-v999",
        input_photo_ids=[p.photo_id for p in req.photos], item_results=[], limitations=["Проверьте фотографии самостоятельно."],
        error_code="MODEL_NOT_READY", elapsed_ms=1, created_at=datetime.now(timezone.utc))
    actual = invoke_review(req, lambda _: b"", provider=lambda *a: result)
    assert actual.error_code == "INVALID_RESPONSE" and actual.prompt_set_version == req.prompt_set_version


def test_review_adapter_rejects_unapproved_model_version(canonical_photo_review_request):
    from datetime import datetime, timezone
    from uuid import uuid4
    from ml_service.app.schemas import PhotoReviewResult
    req = canonical_photo_review_request
    result = PhotoReviewResult(schema_version=req.schema_version, data_origin=req.data_origin,
        ai_review_id=uuid4(), execution_id=req.execution_id, operation_version_id=req.operation.operation_version_id,
        status="uncertain", model_ref="unapproved-model@999", prompt_set_version=req.prompt_set_version,
        input_photo_ids=[p.photo_id for p in req.photos], item_results=[], limitations=["Проверьте фотографии самостоятельно."],
        error_code=None, elapsed_ms=1, created_at=datetime.now(timezone.utc))
    actual = invoke_review(req, lambda _: b"", provider=lambda *a: result, expected_model_ref="approved-model@1")
    assert actual.error_code == "INVALID_RESPONSE" and actual.model_ref is None
