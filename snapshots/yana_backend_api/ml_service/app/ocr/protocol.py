"""Протокол парсера документов и OCR."""
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable
from app.ocr.schemas import DocumentExtractionResult


@runtime_checkable
class DocumentParserProtocol(Protocol):
    """Интерфейс извлечения текста и таблиц из документа."""

    def parse_document(
        self,
        file_input: str | Path | bytes | BinaryIO,
        document_id: str = "doc-1",
        file_name: str = "document.pdf",
    ) -> DocumentExtractionResult:
        """Извлекает страницы, текст и таблицы из документа."""
        ...
