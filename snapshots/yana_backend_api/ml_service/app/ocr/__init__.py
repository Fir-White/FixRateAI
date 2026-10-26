"""Пакет извлечения данных из документов и OCR."""
from app.ocr.schemas import ExtractedDocumentPageDTO, DocumentExtractionResult
from app.ocr.protocol import DocumentParserProtocol
from app.ocr.document_parser import DocumentParser

__all__ = [
    "ExtractedDocumentPageDTO",
    "DocumentExtractionResult",
    "DocumentParserProtocol",
    "DocumentParser",
]
