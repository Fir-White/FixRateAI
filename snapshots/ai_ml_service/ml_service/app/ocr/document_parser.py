"""Парсер документов с сохранением привязки к страницам и источникам."""
import io
from pathlib import Path
from typing import BinaryIO
from app.ocr.schemas import DocumentExtractionResult, ExtractedDocumentPageDTO


class DocumentParser:
    """Парсер текстовых и структурированных документов."""

    def parse_document(
        self,
        file_input: str | Path | bytes | BinaryIO,
        document_id: str = "doc-1",
        file_name: str = "document.pdf",
    ) -> DocumentExtractionResult:
        """Извлекает страницы с сохранением номеров и структуры."""
        text_content = ""
        if isinstance(file_input, (str, Path)):
            p = Path(file_input)
            if p.is_file():
                file_name = p.name
                text_content = p.read_text(encoding="utf-8", errors="ignore")
            else:
                text_content = str(file_input)
        elif isinstance(file_input, bytes):
            text_content = file_input.decode("utf-8", errors="ignore")
        else:
            text_content = file_input.read().decode("utf-8", errors="ignore")

        # Разделяем по маркерам страниц или абзацев
        pages: list[ExtractedDocumentPageDTO] = []
        raw_pages = text_content.split("\f")  # Form Feed разделитель страниц
        if len(raw_pages) <= 1:
            raw_pages = [text_content]

        for idx, page_str in enumerate(raw_pages, start=1):
            cleaned = page_str.strip()
            pages.append(
                ExtractedDocumentPageDTO(
                    page_number=idx,
                    text=cleaned,
                    tables=[],
                    confidence=1.0 if cleaned else None,
                )
            )

        return DocumentExtractionResult(
            document_id=document_id,
            file_name=file_name,
            total_pages=len(pages),
            pages=pages,
            warnings=[],
        )
