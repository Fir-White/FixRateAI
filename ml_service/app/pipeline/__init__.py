"""Пакет оркестрации и сквозной обработки FixRate AI."""
from app.pipeline.state import PipelineStage, InternalPipelineContext
from app.pipeline.merge import merge_defect_sources
from app.pipeline.validation import validate_defect_completeness, ValidationResult
from app.pipeline.orchestrator import PipelineOrchestrator

__all__ = [
    "PipelineStage",
    "InternalPipelineContext",
    "merge_defect_sources",
    "validate_defect_completeness",
    "ValidationResult",
    "PipelineOrchestrator",
]
