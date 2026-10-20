"""ORM-модели FixRate AI, повторяющие DDL v3.1 из `db/001_init.sql`.

Импорт этого пакета регистрирует все 18 таблиц в `Base.metadata`.
Схема создаётся только SQL-миграциями; `create_all()` не используется.
"""
from app.db.base import Base
from app.models.ai import AiResult, AiRun
from app.models.audit import AuditEvent
from app.models.core import Building, DefectType, NormSource, User
from app.models.defects import Defect, DefectMeasurement, DefectPhoto
from app.models.estimates import Estimate, EstimateItem, EstimateMaterial
from app.models.norms import NormativeChunk, Rate
from app.models.requests import RepairRequest, RequestClarification, RequestPhoto

__all__ = [
    "AiResult",
    "AiRun",
    "AuditEvent",
    "Base",
    "Building",
    "Defect",
    "DefectMeasurement",
    "DefectPhoto",
    "DefectType",
    "Estimate",
    "EstimateItem",
    "EstimateMaterial",
    "NormSource",
    "NormativeChunk",
    "Rate",
    "RepairRequest",
    "RequestClarification",
    "RequestPhoto",
    "User",
]
