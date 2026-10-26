"""Семантический чанкер строительной нормативной документации (СП, ГОСТ, СНиП).

Разбивает документы на логические статьи/пункты с сохранением контекста,
структурных локаторов (source_locator), метаданных дефектов и криптографического
хэша содержимого (SHA-256) для проверки неизменности и защиты от дублирования.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field


class ParsedChunk(BaseModel):
    """Смысловой фрагмент строительного норматива, готовый к сохранению в pgvector."""

    chunk_index: int = Field(ge=0, description="Индекс чанка в рамках документа/источника")
    content: str = Field(min_length=1, description="Текстовое содержание фрагмента норматива")
    content_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9A-Fa-f]{64}$",
        description="SHA-256 хэш содержимого для идемпотентности и защиты от изменений",
    )
    source_locator: dict[str, Any] = Field(
        default_factory=dict,
        description="Структурная локация (документ, раздел, пункт, заголовок)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Доменные метаданные (применимые дефекты, ключевые слова, уровень опасности)",
    )
    rate_code: Optional[str] = Field(
        default=None,
        description="Связанный шифр расценки (например DEMO-FACADE-CRACK-01), если применим",
    )


class ParsedDocument(BaseModel):
    """Разобранный нормативный документ с набором смысловых чанков."""

    title: str = Field(description="Наименование нормативного документа")
    edition: Optional[str] = Field(default=None, description="Редакция норматива")
    source_id: str = Field(description="Идентификатор norm_sources (UUID)")
    document_reference: Optional[str] = Field(
        default=None, description="Официальная справка / шифр норматива"
    )
    rate_code: Optional[str] = Field(
        default=None, description="Шифр расценки по умолчанию для данного документа"
    )
    applicable_defects: list[str] = Field(
        default_factory=list, description="Список типов дефектов, к которым применим норматив"
    )
    chunks: list[ParsedChunk] = Field(
        default_factory=list, description="Список смысловых чанков документа"
    )


class NormativeChunker:
    """Парсер и семантический чанкер строительных документов."""

    RE_HEADING = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    RE_CLAUSE_HEADING = re.compile(
        r"^(?:#{1,4}\s+)?(?:Пункт|Статья|Раздел|Таблица)\s+([\d\.\-]+)\.?\s*(.*)$",
        re.IGNORECASE,
    )
    RE_METADATA_LINE = re.compile(r"^\*\*(.+?):\*\*\s*(.+)$")

    @staticmethod
    def compute_content_hash(text: str) -> str:
        """Вычисляет канонический SHA-256 хэш строки после btrim."""
        normalized = text.strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def parse_markdown_file(
        self,
        file_path: Path | str,
        default_source_id: str = "d0000000-0000-4000-8000-000000000001",
    ) -> ParsedDocument:
        """Считывает и парсит файл разметки норматива в структурированный документ."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Файл норматива не найден: {path}")

        raw_content = path.read_text(encoding="utf-8")
        return self.parse_markdown_text(
            raw_content,
            default_source_id=default_source_id,
            file_name=path.name,
        )

    def parse_markdown_text(
        self,
        text: str,
        default_source_id: str = "d0000000-0000-4000-8000-000000000001",
        file_name: Optional[str] = None,
    ) -> ParsedDocument:
        """Разбивает текст строительного регламента на смысловые статьи с метаданными."""
        lines = [line.rstrip() for line in text.splitlines()]
        
        # 1. Извлекаем метаданные документа из шапки
        doc_title = "Строительный норматив"
        edition: Optional[str] = None
        source_id = default_source_id
        document_reference: Optional[str] = None
        default_rate_code: Optional[str] = None
        applicable_defects: list[str] = []
        
        header_end_idx = 0
        for i, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("# ") and doc_title == "Строительный норматив":
                doc_title = line_str[2:].strip()
                continue
            meta_match = self.RE_METADATA_LINE.match(line_str)
            if meta_match:
                key = meta_match.group(1).lower().strip()
                val = meta_match.group(2).strip()
                if "редакц" in key or "edition" in key:
                    edition = val
                elif "источник" in key or "source" in key:
                    source_id = val
                elif "область" in key or "reference" in key or "справка" in key:
                    document_reference = val
                elif "расценк" in key or "rate" in key:
                    default_rate_code = val
                elif "дефект" in key or "defect" in key:
                    applicable_defects = [d.strip() for d in val.split(",") if d.strip()]
            elif line_str.startswith("---"):
                header_end_idx = i + 1
                break

        # 2. Разбиваем тело документа на секции/пункты
        body_lines = lines[header_end_idx:] if header_end_idx > 0 else lines
        raw_sections: list[tuple[str, list[str]]] = []
        current_heading = doc_title
        current_content_lines: list[str] = []

        for line in body_lines:
            heading_match = self.RE_HEADING.match(line)
            if heading_match and heading_match.group(1) in ("##", "###", "####"):
                if current_content_lines:
                    text_block = "\n".join(current_content_lines).strip()
                    if text_block:
                        raw_sections.append((current_heading, current_content_lines))
                    current_content_lines = []
                current_heading = heading_match.group(2).strip()
            else:
                current_content_lines.append(line)

        if current_content_lines:
            text_block = "\n".join(current_content_lines).strip()
            if text_block:
                raw_sections.append((current_heading, current_content_lines))

        # 3. Формируем ParsedChunk с заполнением source_locator и SHA-256
        chunks: list[ParsedChunk] = []
        for idx, (heading, section_lines) in enumerate(raw_sections):
            section_text = "\n".join(section_lines).strip()
            if not section_text:
                continue

            # Разбор номера пункта из заголовка (например "Пункт 7.2.13. Допустимые величины")
            clause_no: Optional[str] = None
            clause_title: str = heading
            clause_match = self.RE_CLAUSE_HEADING.match(heading)
            if clause_match:
                clause_no = clause_match.group(1).strip().rstrip(".")
                if clause_match.group(2):
                    clause_title = clause_match.group(2).strip()

            # Формируем канонический текст чанка с упоминанием норматива для релевантности RAG
            full_content = f"{doc_title}. {heading}\n{section_text}".strip()
            content_hash = self.compute_content_hash(full_content)

            # Определяем уровень опасности (safety flag)
            hazard_level = "normal"
            if any(term in full_content.lower() for term in ["аварий", "2.0 мм", "2 мм", "сквозн", "обрушен", "недопустим"]):
                hazard_level = "structural_hazard"

            locator = {
                "document": doc_title,
                "edition": edition,
                "section_heading": heading,
                "clause": clause_no,
                "title": clause_title,
                "file_name": file_name,
            }

            meta = {
                "applicable_defects": applicable_defects,
                "hazard_level": hazard_level,
                "source_title": doc_title,
                "chunk_size_chars": len(full_content),
            }

            chunks.append(
                ParsedChunk(
                    chunk_index=idx,
                    content=full_content,
                    content_hash=content_hash,
                    source_locator=locator,
                    metadata=meta,
                    rate_code=default_rate_code,
                )
            )

        return ParsedDocument(
            title=doc_title,
            edition=edition,
            source_id=source_id,
            document_reference=document_reference,
            rate_code=default_rate_code,
            applicable_defects=applicable_defects,
            chunks=chunks,
        )
