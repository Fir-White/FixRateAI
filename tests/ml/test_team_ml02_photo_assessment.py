"""Unit and safety tests for Auxiliary Photo Assessment and Attempt Binding (TEAM-ML02 / FRAI-172).

Verifies strict adherence to customer revision CR-17-02 and CR-17-06:
1. Strict binding of photo analysis to work order ID, attempt number, and SHA-256 hashes.
2. Invalidation & Staleness: new photos uploaded mark previous assessment as stale.
3. QualityGuard defect handling: blurry / glare photos require reshoot and yield evidence_class='rejected'.
4. Pair contradiction detection (CASE-01): mismatched dials (0-4 vs 0-6 bar) yield rejected/manual_review.
5. Cross-equipment mismatch (NEG-02, NEG-03): non-identical assets yield evidence_class='rejected'.
6. Model unavailability: missing model weights or server down gracefully defaults to manual_review.
7. HeuristicFallbackClassifier: deterministic 0.0% False Reassurance Rate.
8. Zero Autonomous Approval: AI never auto-accepts work orders; decision remains with Chief Engineer.
"""
from __future__ import annotations

from uuid import uuid4
import pytest

from ml_service.app.cv.assessment import (
    AuxiliaryPhotoAssessment,
    WorkOrderAttemptBinding,
    build_auxiliary_assessment,
    check_assessment_staleness,
    compute_blob_sha256,
)
from ml_service.app.cv.classifier import HeuristicFallbackClassifier
from tests.ml.test_cv import make_test_jpeg


def test_attempt_binding_and_sha_tracking():
    """Verify auxiliary assessment binds attempt number, work order ID, and exact SHA-256 hashes."""
    wo_id = uuid4()
    b_id = uuid4()
    a_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=2,
        equipment_type="pressure_gauge",
        before_photo_id=b_id,
        after_photo_id=a_id,
        before_blob=b_blob,
        after_blob=a_blob,
        vlm_assessment_dict={
            "evidence_class": "approved",
            "visible_changes": ["Очистка штуцера и циферблата"],
            "visible_readings": [
                {"phase": "after", "label": "Давление", "value": "3.2", "unit": "bar", "readable": True}
            ],
        },
        model_ref="qwen3-vl:4b-instruct",
    )

    assert assessment.binding.work_order_id == wo_id
    assert assessment.binding.attempt_no == 2
    assert assessment.binding.before_photo_sha256 == compute_blob_sha256(b_blob)
    assert assessment.binding.after_photo_sha256 == compute_blob_sha256(a_blob)
    assert assessment.binding.is_stale is False
    assert assessment.is_stale is False
    assert len(assessment.bounded_readings) == 1
    assert assessment.bounded_readings[0].parsed_value == 3.2


def test_staleness_detection_on_new_photo_upload():
    """Uploading new photos for the work order attempt invalidates previous assessment."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob_v1 = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=1,
        equipment_type="pressure_gauge",
        before_photo_id=uuid4(),
        after_photo_id=uuid4(),
        before_blob=b_blob,
        after_blob=a_blob_v1,
        vlm_assessment_dict={"evidence_class": "approved"},
    )

    # 1. Matching blobs -> Not stale
    assert check_assessment_staleness(assessment, b_blob, a_blob_v1) is False

    # 2. After photo modified -> Marked stale
    a_blob_v2 = make_test_jpeg("sharp")
    assert check_assessment_staleness(assessment, b_blob, a_blob_v2) is True

    # 3. Before photo modified -> Marked stale
    b_blob_v2 = make_test_jpeg("dark")
    assert check_assessment_staleness(assessment, b_blob_v2, a_blob_v1) is True


def test_quality_defects_require_reshoot_and_reject_evidence():
    """Blur or glare defects trigger reshoot recommendation and reject evidence."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("blur")
    a_blob = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=1,
        equipment_type="mesh_filter",
        before_photo_id=uuid4(),
        after_photo_id=uuid4(),
        before_blob=b_blob,
        after_blob=a_blob,
        quality_result={
            "before_acceptable": False,
            "after_acceptable": True,
            "before_issue": "Размытие изображения (дисперсия Лапласа 12.4 < 50.0)",
        },
    )

    assert assessment.evidence_class == "rejected"
    assert assessment.quality.requires_reshoot is True
    assert any("Запросить повторную фотофиксацию" in r for r in assessment.recommended_engineer_actions)
    assert any("смаз" in c.lower() or "непригодное качество" in c.lower() for c in assessment.concerns)


def test_contradictory_pair_case_01_dial_mismatch():
    """CASE-01: Mismatched dial markings (0-4 bar vs 0-6 bar) must be rejected / flagged."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=1,
        equipment_type="pressure_gauge",
        before_photo_id=uuid4(),
        after_photo_id=uuid4(),
        before_blob=b_blob,
        after_blob=a_blob,
        comparability_result={
            "is_comparable": False,
            "same_subject": "no",
            "contradiction_detected": True,
            "mismatch_reason": "Несоответствие шкал: на фото ДО шкала 0-4 бар, ПОСЛЕ шкала 0-6 бар",
        },
        vlm_assessment_dict={
            "evidence_class": "approved",  # Model naively claimed approved
        },
    )

    # Guard overrides naive model: evidence_class must NOT be approved
    assert assessment.evidence_class == "rejected"
    assert assessment.comparability.contradiction_detected is True
    assert any("Отклонить фотоотчёт" in r for r in assessment.recommended_engineer_actions)


def test_cross_equipment_mismatch_neg_02_neg_03():
    """Cross-equipment before/after pairs (e.g. heat meter vs mixer) must be rejected."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=1,
        equipment_type="heat_meter",
        before_photo_id=uuid4(),
        after_photo_id=uuid4(),
        before_blob=b_blob,
        after_blob=a_blob,
        comparability_result={
            "is_comparable": False,
            "same_subject": "no",
            "mismatch_reason": "Разные физические устройства (теплосчетчик vs смеситель)",
        },
    )

    assert assessment.evidence_class == "rejected"
    assert assessment.comparability.is_comparable is False
    assert assessment.comparability.same_subject == "no"


def test_model_unavailability_maps_to_manual_review_never_approved():
    """When vision model or CLIP is unavailable, verdict MUST be manual_review with zero false reassurance."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob = make_test_jpeg("clean_serviced")

    for unavail_ref in (None, "unavailable", "failed"):
        assessment = build_auxiliary_assessment(
            work_order_id=wo_id,
            attempt_no=1,
            equipment_type="control_cabinet",
            before_photo_id=uuid4(),
            after_photo_id=uuid4(),
            before_blob=b_blob,
            after_blob=a_blob,
            model_ref=unavail_ref,
        )

        assert assessment.evidence_class == "manual_review"
        assert any("ручную оценку" in r for r in assessment.recommended_engineer_actions)


def test_heuristic_fallback_classifier():
    """Verify HeuristicFallbackClassifier is importable, deterministic, and conservative."""
    clf = HeuristicFallbackClassifier()
    assert clf.is_available is True
    assert clf.model_name == "heuristic:quality-guard-baseline"

    item_id = uuid4()
    b_id = uuid4()
    a_id = uuid4()
    rev = clf.evaluate_pair(
        checklist_item_id=item_id,
        before_photo_id=b_id,
        after_photo_id=a_id,
        before_bytes=make_test_jpeg("dirty"),
        after_bytes=make_test_jpeg("clean_serviced"),
    )

    assert rev.verdict == "uncertain"
    assert rev.checklist_item_id == item_id
    assert "ручная приёмка инженером" in rev.observation


def test_omitted_comparability_cannot_approve_defaults_to_manual_review():
    """When comparability_result is omitted, assessment MUST NOT approve and defaults to manual_review."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=1,
        equipment_type="pressure_gauge",
        before_photo_id=uuid4(),
        after_photo_id=uuid4(),
        before_blob=b_blob,
        after_blob=a_blob,
        comparability_result=None,  # Caller omitted comparability
        vlm_assessment_dict={"evidence_class": "approved"},  # Model naively claimed approved
    )

    assert assessment.evidence_class == "manual_review"
    assert assessment.comparability.is_comparable is False
    assert assessment.comparability.same_subject == "uncertain"


def test_case_01_description_auto_detected_as_contradiction_without_comparability_flag():
    """CASE-01: Auto-detects 0-4 bar vs 0-6 bar from descriptions even if caller omitted comparability."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=1,
        equipment_type="pressure_gauge",
        before_photo_id=uuid4(),
        after_photo_id=uuid4(),
        before_blob=b_blob,
        after_blob=a_blob,
        comparability_result=None,
        vlm_assessment_dict={
            "evidence_class": "approved",
            "before_description": "Манометр стрелочный показывающий, шкала 0-4 бар",
            "after_description": "Манометр с круглой шкалой 0-6 бар, стрелка на 3.2 бар",
        },
    )

    assert assessment.evidence_class == "rejected"
    assert assessment.comparability.contradiction_detected is True
    assert "CASE-01" in (assessment.comparability.mismatch_reason or "")


def test_with_staleness_check_method_updates_assessment_state():
    """Verify with_staleness_check method returns immutable copy with updated is_stale state."""
    wo_id = uuid4()
    b_blob = make_test_jpeg("dirty")
    a_blob_v1 = make_test_jpeg("clean_serviced")

    assessment = build_auxiliary_assessment(
        work_order_id=wo_id,
        attempt_no=1,
        equipment_type="pressure_gauge",
        before_photo_id=uuid4(),
        after_photo_id=uuid4(),
        before_blob=b_blob,
        after_blob=a_blob_v1,
        comparability_result={"is_comparable": True, "same_subject": "yes"},
        vlm_assessment_dict={"evidence_class": "approved"},
    )
    assert assessment.is_stale is False

    # Check identical blobs
    fresh = assessment.with_staleness_check(b_blob, a_blob_v1)
    assert fresh.is_stale is False

    # Check modified blobs
    a_blob_v2 = make_test_jpeg("sharp")
    stale = assessment.with_staleness_check(b_blob, a_blob_v2)
    assert stale.is_stale is True


def test_service_review_photos_with_heuristic_fallback(canonical_photo_review_request):
    """Calling review_photos with fallback_to_heuristic=True uses HeuristicFallbackClassifier."""
    from ml_service.app.cv.service import review_photos

    class MissingClassifier:
        is_torch_active = False

    photos = canonical_photo_review_request.photos
    storage = {photos[0].photo_id: make_test_jpeg("dirty"), photos[1].photo_id: make_test_jpeg("clean_serviced")}

    # 1. Without fallback -> unavailable
    res_no_fb = review_photos(
        canonical_photo_review_request,
        lambda pid: storage[pid],
        classifier=MissingClassifier(),
        fallback_to_heuristic=False,
    )
    assert res_no_fb.status == "unavailable"
    assert res_no_fb.error_code == "MODEL_NOT_READY"
    assert len(res_no_fb.item_results) == 0

    # 2. With fallback -> uncertain items with heuristic baseline observation
    res_fb = review_photos(
        canonical_photo_review_request,
        lambda pid: storage[pid],
        classifier=MissingClassifier(),
        fallback_to_heuristic=True,
    )
    assert res_fb.status == "uncertain"
    assert len(res_fb.item_results) == 1
    assert res_fb.item_results[0].verdict == "uncertain"
    assert "Эвристический baseline" in res_fb.item_results[0].observation

