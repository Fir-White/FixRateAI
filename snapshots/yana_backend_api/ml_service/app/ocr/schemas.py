"""Схемы данных извлечения текста и таблиц из документов (OCR)."""
from typing import Any
from pydantic import BaseModel, Field


class ExtractedDocumentPageDTO(BaseModel):
    """Извлечённый текст и таблицы отдельной страницы документа."""
    page_number: int
    text: str
    tables: list[list[list[str]]] = Field(
        default_factory=list,
        description="Таблицы страницы (список строк, содержащих ячейки)",
    )
    confidence: float | None = None


class DocumentExtractionResult(BaseModel):
    """Результат разбора многостраничного документа."""
    document_id: str
    file_name: str
    total_pages: int
    pages: list[ExtractedDocumentPageDTO] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
