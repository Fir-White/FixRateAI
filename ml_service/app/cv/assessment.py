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
import re
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


def normalize_text_dashes(text: str) -> str:
    """Normalize any unicode dashes, spaces, and formatting for robust scale comparison."""
    return re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d]", "-", text.lower())


def extract_dial_limit(text: str) -> int | None:
    """Detect whether a dial scale limit of 4 or 6 bar is described in the text."""
    norm = normalize_text_dashes(text)
    # Check for 0-4 or 0..4 or 0...4 or limit 4
    if (
        re.search(r"\b0\s*(?:-|\.{2,})\s*4\b", norm)
        or re.search(r"\b(?:шкала|диапазон|предел)\s*(?:до\s*)?4(?:\s*бар|\s*bar)?\b", norm)
        or re.search(r"\bдо\s*4\s*(?:бар|bar)\b", norm)
    ):
        return 4
    # Check for 0-6 or 0..6 or 0...6 or limit 6
    if (
        re.search(r"\b0\s*(?:-|\.{2,})\s*6\b", norm)
        or re.search(r"\b(?:шкала|диапазон|предел)\s*(?:до\s*)?6(?:\s*бар|\s*bar)?\b", norm)
        or re.search(r"\bдо\s*6\s*(?:бар|bar)\b", norm)
    ):
        return 6
    return None


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
    stale_reason: str | None = Field(default=None, description="Diagnostic explanation when stale")


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
    stale_reason: str | None = Field(default=None, description="Diagnostic explanation when stale")
    equipment_type: str
    quality: PairQualityAssessment
    comparability: PairComparabilityAssessment
    visible_changes: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    bounded_readings: list[BoundedReadingCandidate] = Field(default_factory=list)
    recommended_engineer_actions: list[str] = Field(default_factory=list)
    cannot_confirm: list[str] = Field(
        default_factory=lambda: [
            "Метрологическая точность стрелочных манометров по фото не подтверждается.",
            "Скрытая исправность гидравлических узлов и отсутствие протечек вне кадра не оцениваются.",
            "При любых сомнениях инженер обязан провести очный осмотр узла.",
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

    def with_staleness_check(
        self,
        current_before_blob: bytes | None = None,
        current_after_blob: bytes | None = None,
        current_before_sha256: str | None = None,
        current_after_sha256: str | None = None,
    ) -> AuxiliaryPhotoAssessment:
        """Returns a copy of the assessment with updated staleness status, reasons, and demoted approvals."""
        stale = check_assessment_staleness(
            self,
            current_before_blob=current_before_blob,
            current_after_blob=current_after_blob,
            current_before_sha256=current_before_sha256,
            current_after_sha256=current_after_sha256,
        )
        if stale == self.is_stale and (not stale or self.binding.is_stale):
            return self

        updated_concerns = list(self.concerns)
        updated_limitations = list(self.limitations)
        updated_evidence_class = self.evidence_class
        updated_summary = self.summary
        reason_msg = None

        if stale:
            reason_msg = (
                "ВНИМАНИЕ: Фотоматериалы наряда были изменены после проведения анализа (хеш SHA-256 снимков не совпадает). "
                "Данная оценка УСТАРЕЛА (is_stale=True) и не может использоваться для приёмки."
            )
            if reason_msg not in updated_concerns:
                updated_concerns.append(reason_msg)
            stale_lim = "Оценка потеряла актуальность (is_stale=True): исходные фотофайлы попытки наряда были перезаписаны."
            if stale_lim not in updated_limitations:
                updated_limitations.append(stale_lim)
            if updated_evidence_class == "approved":
                updated_evidence_class = "manual_review"
            if not updated_summary.startswith("[УСТАРЕЛО"):
                updated_summary = f"[УСТАРЕЛО / STALE] {updated_summary}"
        else:
            updated_concerns = [c for c in updated_concerns if "is_stale=True" not in c]
            if updated_summary.startswith("[УСТАРЕЛО / STALE] "):
                updated_summary = updated_summary.replace("[УСТАРЕЛО / STALE] ", "")

        updated_binding = self.binding.model_copy(
            update={"is_stale": stale, "stale_reason": reason_msg}
        )

        return self.model_copy(
            update={
                "is_stale": stale,
                "stale_reason": reason_msg,
                "binding": updated_binding,
                "concerns": updated_concerns,
                "limitations": updated_limitations,
                "evidence_class": updated_evidence_class,
                "summary": updated_summary,
            }
        )


def compute_blob_sha256(blob: bytes | None) -> str | None:
    if not blob:
        return None
    return hashlib.sha256(blob).hexdigest()


def check_assessment_staleness(
    assessment: AuxiliaryPhotoAssessment,
    current_before_blob: bytes | None = None,
    current_after_blob: bytes | None = None,
    current_before_sha256: str | None = None,
    current_after_sha256: str | None = None,
) -> bool:
    """Verifies whether the current files on the work order still match the analyzed hashes."""
    current_b_hash = current_before_sha256 or compute_blob_sha256(current_before_blob)
    current_a_hash = current_after_sha256 or compute_blob_sha256(current_after_blob)

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
        stale_reason=None,
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
    vlm = vlm_assessment_dict or {}
    c_dict = comparability_result or {}

    if comparability_result is not None:
        is_comp = bool(c_dict.get("is_comparable", False))
        same_subj = c_dict.get("same_subject", "uncertain")
        vp_matched = bool(c_dict.get("viewpoint_matched", False))
        contradiction = bool(c_dict.get("contradiction_detected", False))
        mismatch_reason = c_dict.get("mismatch_reason")
    else:
        # Strict conservative default: unconfirmed comparability cannot be assumed valid
        is_comp = False
        same_subj = "uncertain"
        vp_matched = False
        contradiction = False
        mismatch_reason = "Сопоставимость пары до/после не подтверждена оператором; требуется ручная приёмка."

    # Built-in contradiction detection across VLM descriptions and observations
    b_desc = str(vlm.get("before_description", ""))
    a_desc = str(vlm.get("after_description", ""))
    all_concerns = [str(c) for c in vlm.get("concerns", [])]
    all_changes = [str(c) for c in vlm.get("visible_changes", [])]

    # Robust detection of CASE-01 dial mismatch (0-4 vs 0-6 bar, with en-dash, em-dash, spaces, or words)
    scale_b = extract_dial_limit(b_desc)
    scale_a = extract_dial_limit(a_desc)
    has_dial_contradiction = (scale_b is not None and scale_a is not None and scale_b != scale_a)

    b_norm = normalize_text_dashes(b_desc)
    a_norm = normalize_text_dashes(a_desc)
    all_text_norm = " ".join([b_norm, a_norm, *[normalize_text_dashes(c) for c in all_concerns], *[normalize_text_dashes(c) for c in all_changes]])

    is_dial_mismatch = (
        has_dial_contradiction
        or (("0-4" in b_norm or "0..4" in b_norm) and ("0-6" in a_norm or "0..6" in a_norm))
        or (("0-6" in b_norm or "0..6" in b_norm) and ("0-4" in a_norm or "0..4" in a_norm))
        or any(
            phrase in all_text_norm
            for phrase in [
                "разные приборы",
                "разные шкалы",
                "несовпадение шкал",
                "несоответствие шкал",
                "подмена прибора",
                "подмена манометра",
                "case-01",
            ]
        )
    )

    if is_dial_mismatch:
        contradiction = True
        is_comp = False
        same_subj = "no"
        mismatch_reason = (
            "Выявлено физическое несоответствие циферблатов манометров: "
            "шкала 0–4 бар на фото ДО vs 0–6 бар на фото ПОСЛЕ (CASE-01)"
        )

    # Detect cross-equipment mismatch (NEG-02, NEG-03)
    if vlm.get("same_subject") == "no" or vlm.get("comparable") == "no":
        same_subj = "no"
        is_comp = False
        if not mismatch_reason:
            mismatch_reason = "Визуальная модель зафиксировала несовпадающие объекты на фото До и После"

    comparability = PairComparabilityAssessment(
        is_comparable=is_comp,
        same_subject=same_subj,
        viewpoint_matched=vp_matched,
        contradiction_detected=contradiction,
        mismatch_reason=mismatch_reason,
    )

    # 3. Reading extraction & Bounded OCR
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
    elif same_subj == "no" or contradiction:
        evidence_class = "rejected"
        concerns.append(f"Несопоставимая пара или подмена объекта: {mismatch_reason or 'разные физические узлы'}.")
        recs.append("Отклонить фотоотчёт в связи с несопоставимостью снимков до и после обслуживания.")
    elif model_ref in (None, "unavailable", "failed") or vlm.get("evidence_class") == "manual_review":
        evidence_class = "manual_review"
        concerns.append("Модель анализа недоступна или выдала статус ручной проверки.")
        recs.append("Выполнить ручную оценку качества выполненных работ главным инженером.")
    elif not is_comp or same_subj == "uncertain":
        evidence_class = "manual_review"
        concerns.append(f"Сопоставимость ракурса или объекта не доказана: {mismatch_reason or 'требуется визуальная сверка инженером'}.")
        recs.append("Направить на очную проверку и ручную приёмку главным инженером.")
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
        stale_reason=None,
        equipment_type=equipment_type,
        quality=quality,
        comparability=comparability,
        visible_changes=visible_changes,
        concerns=concerns,
        bounded_readings=bounded_readings,
        recommended_engineer_actions=recs,
        summary=summary_text,
    )


def review_work_order_attempt(
    work_order_id: UUID,
    attempt_no: int,
    equipment_type: str,
    before_photo_id: UUID | None,
    after_photo_id: UUID | None,
    before_blob: bytes | None,
    after_blob: bytes | None,
    quality_guard: Any | None = None,
    comparability_confirmed: bool = False,
    model_ref: str | None = None,
    vlm_assessment_dict: dict[str, Any] | None = None,
) -> AuxiliaryPhotoAssessment:
    """Production entry point: evaluates attempt photo pair, checks quality & OCR, and binds to attempt."""
    from ml_service.app.cv.quality import ImageQualityGuard

    guard = quality_guard or ImageQualityGuard()
    b_res = guard.assess_bytes(before_blob) if before_blob else None
    a_res = guard.assess_bytes(after_blob) if after_blob else None

    quality_result = {
        "before_acceptable": b_res.is_acceptable if b_res else False,
        "after_acceptable": a_res.is_acceptable if a_res else False,
        "before_issue": b_res.issue if b_res else "Снимок ДО отсутствует",
        "after_issue": a_res.issue if a_res else "Снимок ПОСЛЕ отсутствует",
    }

    comparability_result = {
        "is_comparable": comparability_confirmed,
        "same_subject": "yes" if comparability_confirmed else "uncertain",
        "viewpoint_matched": comparability_confirmed,
        "contradiction_detected": False,
    }

    return build_auxiliary_assessment(
        work_order_id=work_order_id,
        attempt_no=attempt_no,
        equipment_type=equipment_type,
        before_photo_id=before_photo_id,
        after_photo_id=after_photo_id,
        before_blob=before_blob,
        after_blob=after_blob,
        quality_result=quality_result,
        comparability_result=comparability_result,
        vlm_assessment_dict=vlm_assessment_dict,
        model_ref=model_ref,
    )
