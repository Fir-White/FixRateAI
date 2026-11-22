"""Auxiliary photo assessment for chief engineer review.

Provides structured decision support for chief engineers:
- Strict binding of photo analysis to work order attempt and SHA-256 photo hashes.
- Invalidation / staleness detection: uploading new photos marks previous analysis as stale.
- Pair comparability analysis, catching contradictory pairs (e.g. CASE-01 mismatched dials).
- Bounded OCR reading extraction for analog gauges and heat meters.
- Explicit disclaimers: AI NEVER auto-accepts work orders or approves maintenance;
  all final verdicts remain with the chief engineer.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ml_service.app.cv.ocr import BoundedOCRValidator, BoundedReadingCandidate


CHIEF_ENGINEER_DISCLAIMER = (
    "Вспомогательный анализ сформирован ИИ для поддержки принятия решения главным инженером. "
    "Модель анализирует только видимые изменения на снимках. "
    "Скрытые работы, внутренняя исправность, электробезопасность и герметичность по фото не "
    "подтверждаются. Решение о приёмке или возврате работы принимает исключительно главный инженер."
)


class WorkOrderAttemptBinding(BaseModel):
    """Binds analysis artifact to a specific work order attempt and input files."""
    model_config = ConfigDict(frozen=True)

    work_order_id: UUID
    attempt_no: int = Field(default=1, ge=1)
    before_photo_id: UUID | None = None
    after_photo_id: UUID | None = None
    before_photo_sha256: str | None = None
    after_photo_sha256: str | None = None
    model_ref: str | None = None
    prompt_set_version: str = "maintenance-assessment-v2"
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_stale: bool = Field(default=False, description="True if subsequent photos were uploaded")


class PairQualityAssessment(BaseModel):
    """Image quality evaluation across the pair."""
    before_acceptable: bool = True
    after_acceptable: bool = True
    before_issue: str | None = None
    after_issue: str | None = None
    requires_reshoot: bool = False
    details: list[str] = Field(default_factory=list)


class PairComparabilityAssessment(BaseModel):
    """Verification that before and after photos represent the same physical asset and viewpoint."""
    is_comparable: bool = True
    same_subject: Literal["yes", "no", "uncertain"] = "yes"
    viewpoint_matched: bool = True
    contradiction_detected: bool = False
    mismatch_reason: str | None = None


class AuxiliaryPhotoAssessment(BaseModel):
    """Structured auxiliary decision-support report for Chief Engineer."""
    model_config = ConfigDict(frozen=True)

    assessment_id: UUID = Field(default_factory=uuid4)
    binding: WorkOrderAttemptBinding
    evidence_class: Literal["approved", "manual_review", "rejected"] = Field(
        ..., description="Suitability of photo evidence (not work acceptance)"
    )
    is_stale: bool = Field(
        default=False, description="Flagged as stale if input photos no longer match attempt"
    )
    equipment_type: str
    quality: PairQualityAssessment
    comparability: PairComparabilityAssessment
    visible_changes: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    bounded_readings: list[BoundedReadingCandidate] = Field(default_factory=list)
    recommended_engineer_actions: list[str] = Field(default_factory=list)
    cannot_confirm: list[str] = Field(
        default_factory=lambda: [
            "Скрытые внутренние работы и электробезопасность по фото не подтверждаются.",
            "Метрологическая точность приборов и калибровка требуют инструментальной поверки.",
            "Герметичность соединений под рабочим давлением подтверждается актом опрессовки.",
        ]
    )
    limitations: list[str] = Field(
        default_factory=lambda: [
            CHIEF_ENGINEER_DISCLAIMER,
            "ИИ не принимает решение о закрытии заказ-наряда: решение принимает главный инженер.",
            "При расхождении показаний или ракурсов обязателен очный осмотр узла инженером.",
        ]
    )
    summary: str


def compute_blob_sha256(blob: bytes | None) -> str | None:
    if not blob:
        return None
    return hashlib.sha256(blob).hexdigest()


def check_assessment_staleness(
    assessment: AuxiliaryPhotoAssessment,
    current_before_blob: bytes | None,
    current_after_blob: bytes | None,
) -> bool:
    """Verifies whether the current files on the work order still match the analyzed hashes."""
    current_b_hash = compute_blob_sha256(current_before_blob)
    current_a_hash = compute_blob_sha256(current_after_blob)

    if assessment.binding.before_photo_sha256 != current_b_hash:
        return True
    if assessment.binding.after_photo_sha256 != current_a_hash:
        return True
    return False


def build_auxiliary_assessment(
    work_order_id: UUID,
    attempt_no: int,
    equipment_type: str,
    before_photo_id: UUID | None,
    after_photo_id: UUID | None,
    before_blob: bytes | None,
    after_blob: bytes | None,
    quality_result: dict[str, Any] | None = None,
    comparability_result: dict[str, Any] | None = None,
    vlm_assessment_dict: dict[str, Any] | None = None,
    model_ref: str | None = None,
) -> AuxiliaryPhotoAssessment:
    """Constructs a validated auxiliary photo assessment for the chief engineer."""
    b_hash = compute_blob_sha256(before_blob)
    a_hash = compute_blob_sha256(after_blob)

    binding = WorkOrderAttemptBinding(
        work_order_id=work_order_id,
        attempt_no=attempt_no,
        before_photo_id=before_photo_id,
        after_photo_id=after_photo_id,
        before_photo_sha256=b_hash,
        after_photo_sha256=a_hash,
        model_ref=model_ref,
        prompt_set_version="maintenance-assessment-v2",
        analyzed_at=datetime.now(timezone.utc),
        is_stale=False,
    )

    # 1. Quality evaluation
    q_dict = quality_result or {}
    b_acc = q_dict.get("before_acceptable", True)
    a_acc = q_dict.get("after_acceptable", True)
    b_issue = q_dict.get("before_issue")
    a_issue = q_dict.get("after_issue")
    req_reshoot = not (b_acc and a_acc)
    q_details = []
    if not b_acc:
        q_details.append(f"Дефект фото ДО: {b_issue or 'непригодное качество'}")
    if not a_acc:
        q_details.append(f"Дефект фото ПОСЛЕ: {a_issue or 'непригодное качество'}")

    quality = PairQualityAssessment(
        before_acceptable=b_acc,
        after_acceptable=a_acc,
        before_issue=b_issue,
        after_issue=a_issue,
        requires_reshoot=req_reshoot,
        details=q_details,
    )

    # 2. Comparability evaluation
    c_dict = comparability_result or {}
    is_comp = c_dict.get("is_comparable", True)
    same_subj = c_dict.get("same_subject", "yes")
    vp_matched = c_dict.get("viewpoint_matched", True)
    contradiction = c_dict.get("contradiction_detected", False)
    mismatch_reason = c_dict.get("mismatch_reason")

    comparability = PairComparabilityAssessment(
        is_comparable=is_comp,
        same_subject=same_subj,
        viewpoint_matched=vp_matched,
        contradiction_detected=contradiction,
        mismatch_reason=mismatch_reason,
    )

    # 3. Reading extraction & Bounded OCR
    vlm = vlm_assessment_dict or {}
    raw_readings = vlm.get("visible_readings", [])
    bounded_readings = BoundedOCRValidator.filter_and_validate(
        raw_readings=raw_readings,
        equipment_type=equipment_type,
    )

    # 4. Formulate evidence class and recommendations
    visible_changes = [str(x) for x in vlm.get("visible_changes", []) if str(x).strip()]
    concerns = [str(x) for x in vlm.get("concerns", []) if str(x).strip()]
    recs = [str(x) for x in vlm.get("recommended_actions", []) if str(x).strip()]

    # Decision logic for evidence_class (NOT work order approval!)
    if req_reshoot:
        evidence_class = "rejected"
        concerns.append("Снимки не соответствуют стандартам технического качества (смаз, блик или недостаточная освещённость).")
        recs.append("Запросить повторную фотофиксацию у исполнителя с соблюдением требований к резкости и освещению.")
    elif not is_comp or same_subj == "no" or contradiction:
        evidence_class = "rejected"
        concerns.append(f"Несопоставимая пара или подмена объекта: {mismatch_reason or 'разные физические узлы'}.")
        recs.append("Отклонить фотоотчёт в связи с несопоставимостью снимков до и после обслуживания.")
    elif any(r.reading_status.value in ("out_of_range", "unsupported_unit") for r in bounded_readings):
        evidence_class = "manual_review"
        concerns.append("Выявлены аномальные или неподдерживаемые показания приборов, требующие сверки.")
        recs.append("Провести ручную сверку показаний по исполнительному протоколу и очному журналу.")
    elif model_ref in (None, "unavailable", "failed") or vlm.get("evidence_class") == "manual_review":
        evidence_class = "manual_review"
        recs.append("Выполнить ручную оценку качества выполненных работ главным инженером.")
    elif vlm.get("evidence_class") == "approved":
        evidence_class = "approved"
        recs.append("Фотодоказательство пригодно для рассмотрения. Главный инженер принимает решение о приёмке.")
    else:
        evidence_class = "manual_review"
        recs.append("Окончательное решение принимается главным инженером на основе акта и фотоотчёта.")

    summary_text = (
        f"Вспомогательный анализ попытки {attempt_no} по объекту '{equipment_type}'. "
        f"Класс доказательства: {evidence_class}. "
        f"Качество: {'допустимо' if not req_reshoot else 'требуется пересъёмка'}. "
        f"Сопоставимость пары: {'подтверждена' if is_comp and not contradiction else 'нарушена'}. "
        f"Выделено показаний приборов: {len(bounded_readings)}. "
        "Автоматическое закрытие наряда исключено: решение принимает главный инженер."
    )

    return AuxiliaryPhotoAssessment(
        binding=binding,
        evidence_class=evidence_class,
        is_stale=False,
        equipment_type=equipment_type,
        quality=quality,
        comparability=comparability,
        visible_changes=visible_changes,
        concerns=concerns,
        bounded_readings=bounded_readings,
        recommended_engineer_actions=recs,
        summary=summary_text,
    )
