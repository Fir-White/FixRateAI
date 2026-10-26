"""Состояния и внутренний контекст сквозного пайплайна FixRate AI."""
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from app.cv.schemas import CVInferenceResult
from app.llm.schemas import NormalizedDefectDescription
from app.rag.hybrid import CandidateRateResult
from app.schemas.common import PipelineStatus
from app.schemas.request import JobRequestDTO
from app.schemas.response import (
    ClarificationQuestionDTO,
    DetectedDefectDTO,
    EstimateItemDTO,
    JobResponseDTO,
)


class PipelineStage(str, Enum):
    """Этапы жизненного цикла обработки задачи."""
    RECEIVED = "received"
    PREPROCESSING = "preprocessing"
    CV_INFERENCE = "cv_inference"
    TEXT_NORMALIZATION = "text_normalization"
    DATA_MERGE = "data_merge"
    VALIDATION = "validation"
    RAG_RETRIEVAL = "rag_retrieval"
    APPLICABILITY_CHECK = "applicability_check"
    CALCULATION = "calculation"
    QA_AUDIT = "qa_audit"
    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    FAILED = "failed"


class InternalPipelineContext(BaseModel):
    """Внутреннее состояние сквозной обработки задачи."""
    request: JobRequestDTO
    stage: PipelineStage = PipelineStage.RECEIVED
    status: PipelineStatus = PipelineStatus.COMPLETED
    cv_result: CVInferenceResult | None = None
    text_norm: NormalizedDefectDescription | None = None
    merged_defects: list[DetectedDefectDTO] = Field(default_factory=list)
    estimate_items: list[EstimateItemDTO] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestionDTO] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_trail: list[str] = Field(default_factory=list)
    processing_time_ms: int = 0
