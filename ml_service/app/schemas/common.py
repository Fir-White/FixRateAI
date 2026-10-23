"""Базовые типы, перечисления и provenance-схемы ML Service."""
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class SourceType(str, Enum):
    """Источник происхождения данных (соответствует схеме БД FixRate AI)."""
    USER = "user"    # Введено пользователем / оператором напрямую
    OCR = "ocr"      # Извлечено из акта / документа
    CV = "cv"        # Распознано моделью компьютерного зрения
    CALC = "calc"    # Вычислено детерминированным расчётным модулем
    RAG = "rag"      # Подобрано поисковой подсистемой RAG


class PipelineStatus(str, Enum):
    """Итоговый статус выполнения сквозного пайплайна."""
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_REVIEW = "needs_review"
    NOT_FOUND = "not_found"
    FAILED = "failed"


class ValidationStatus(str, Enum):
    """Статус валидации отдельного атрибута."""
    VALID = "valid"
    MISSING = "missing"
    CONFLICT = "conflict"
    OUT_OF_RANGE = "out_of_range"


class UnitCode(str, Enum):
    """Канонические единицы измерения."""
    M = "m"          # Метры
    M2 = "m2"        # Квадратные метры
    M3 = "m3"        # Кубические метры
    MM = "mm"        # Миллиметры
    PCS = "pcs"      # Штуки
    KG = "kg"        # Килограммы


class ExtractedField(BaseModel, Generic[T]):
    """Поле с сохранением происхождения (Data Provenance), единицы и уверенности."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    field_name: str
    value: T | None = None
    unit: str | None = None
    source_type: SourceType = SourceType.USER
    source_ref: str | None = None  # Имя файла, страница акта, номер детекции
    confidence: float | None = None  # None для детерминированных/пользовательских данных
    validation_status: ValidationStatus = ValidationStatus.VALID
    warnings: list[str] = Field(default_factory=list)
