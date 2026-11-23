"""Markdown regulation extractor and tabular catalog chunker with strict hierarchical breadcrumbs."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .guardrails import PromptInjectionDefense
from .schemas import Chunk, DocumentMetadata


def normalize_search_text(text: str) -> str:
    """Normalize text for lexical / full-text token matching (Russian & English)."""
    cleaned = re.sub(r"[^\w\sа-яА-ЯёЁ0-9\.\-]", " ", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def compute_content_sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


class DocumentExtractor:
    """Extracts structured chunks with hierarchical breadcrumb provenance from Markdown regulations and Excel catalogs."""

    @staticmethod
    def extract_from_markdown(
        content: str,
        file_path: str | Path | None = None,
        default_equipment_class: str | None = None,
        override_metadata: dict[str, Any] | None = None,
    ) -> tuple[DocumentMetadata, list[Chunk]]:
        """Parses markdown document, extracts metadata, and chunks by full header hierarchy (H1 > H2 > H3)."""
        # Sanitize untrusted input before extraction
        sanitized_content = PromptInjectionDefense.sanitize_untrusted_text(content)
        lines = sanitized_content.splitlines()

        # 1. Parse Title (H1)
        title = "Утверждённый регламент ТО"
        for line in lines:
            line_s = line.strip()
            if line_s.startswith("# "):
                title = line_s[2:].strip()
                break

        # 2. Extract Document Metadata from bullet headers
        doc_id = "doc-unknown"
        revision = "rev-unknown"
        site_acl: list[str] = []
        role_acl: list[str] = ["chief_engineer", "executor"]

        for line in lines[:30]:
            line_s = line.strip()
            if "Идентификатор документа" in line_s or "document_id" in line_s:
                m = re.search(r"`([^`]+)`", line_s)
                if m:
                    doc_id = m.group(1).strip()
            elif "Ревизия" in line_s or "source_revision" in line_s:
                m = re.search(r"`([^`]+)`", line_s)
                if m:
                    revision = m.group(1).strip()
            elif "Объект (ACL)" in line_s or "site_acl" in line_s:
                matches = re.findall(r"`([^`]+)`", line_s)
                if matches:
                    site_acl = [x.strip() for x in matches]
                elif "любой" in line_s.lower() or "все" in line_s.lower() or "global" in line_s.lower():
                    site_acl = []
            elif "Ролевой доступ" in line_s or "role_acl" in line_s:
                matches = re.findall(r"`([^`]+)`", line_s)
                if matches:
                    role_acl = [x.strip() for x in matches]
                elif "chief_engineer" in line_s:
                    if "executor" in line_s:
                        role_acl = ["chief_engineer", "executor"]
                    else:
                        role_acl = ["chief_engineer"]

        # Apply override metadata if supplied from manifest
        expected_sha = None
        if override_metadata:
            doc_id = override_metadata.get("document_id", doc_id)
            title = override_metadata.get("title", title)
            revision = override_metadata.get("source_revision", revision)
            site_acl = override_metadata.get("site_acl", site_acl)
            role_acl = override_metadata.get("role_acl", role_acl)
            default_equipment_class = override_metadata.get("equipment_class", default_equipment_class)
            expected_sha = override_metadata.get("expected_sha256")

        # Infer equipment class if missing
        equipment_class = default_equipment_class
        if not equipment_class:
            lower_content = sanitized_content.lower()
            if "манометр" in lower_content:
                equipment_class = "pressure_gauge"
            elif "вкт-7" in lower_content or "тепловычислител" in lower_content:
                equipment_class = "heat_meter"
            elif "щит" in lower_content or "шкаф" in lower_content or "шау" in lower_content:
                equipment_class = "control_cabinet"
            elif "фильтр" in lower_content or "грязевик" in lower_content or "фсф" in lower_content:
                equipment_class = "mesh_filter"
            elif "коллектор" in lower_content or "гребенк" in lower_content or "опрессовк" in lower_content:
                equipment_class = "heating_manifold"

        doc_sha = compute_content_sha256(content)
        str_path = str(file_path) if file_path else None

        metadata = DocumentMetadata(
            document_id=doc_id,
            title=title,
            source_revision=revision,
            source_sha256=doc_sha,
            expected_sha256=expected_sha,
            equipment_class=equipment_class,
            site_acl=site_acl,
            role_acl=role_acl,
            file_path=str_path,
            is_archived=False,
            is_stale=False,
            status="active",
        )

        # 3. Chunk by sections with hierarchical heading breadcrumb (H1 > H2 > H3)
        chunks: list[Chunk] = []
        current_h1 = title
        current_h2 = ""
        current_h3 = ""
        current_lines: list[str] = []
        chunk_idx = 0

        def flush_chunk() -> None:
            nonlocal chunk_idx, current_lines
            if not current_lines:
                return
            section_content = "\n".join(current_lines).strip()
            if len(section_content) > 30:
                chunk_idx += 1
                breadcrumb = " > ".join(filter(None, [current_h1, current_h2, current_h3]))
                effective_sec = current_h3 or current_h2 or current_h1
                sec_slug = re.sub(r"[^\w]+", "-", effective_sec.lower()).strip("-")
                # Collision-proof unique chunk id including revision and index
                chunk_id = f"{doc_id}:{revision}#{sec_slug}#{chunk_idx}"
                source_ref = f"{str_path or doc_id}#{effective_sec}"
                chunk_sha = compute_content_sha256(section_content)

                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        document_title=title,
                        source_revision=revision,
                        section_title=effective_sec,
                        section_path=breadcrumb,
                        chunk_index=chunk_idx,
                        content=section_content,
                        clean_text=normalize_search_text(f"{breadcrumb} {section_content}"),
                        equipment_class=equipment_class,
                        site_acl=site_acl,
                        role_acl=role_acl,
                        source_ref=source_ref,
                        sha256=chunk_sha,
                        is_stale=False,
                    )
                )
            current_lines = []

        for line in lines:
            line_s = line.strip()
            if line_s.startswith("## "):
                flush_chunk()
                current_h2 = line_s[3:].strip()
                current_h3 = ""
                current_lines = [line]
            elif line_s.startswith("### "):
                flush_chunk()
                current_h3 = line_s[4:].strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        flush_chunk()
        return metadata, chunks

    @staticmethod
    def extract_from_catalog_rows(
        rows: list[dict[str, Any]],
        site_id: str,
        source_revision: int | str,
        catalog_sha256: str | None = None,
    ) -> tuple[DocumentMetadata, list[Chunk]]:
        """Chunks tabular Excel catalog rows into verifiable chunks with collision-proof IDs."""
        doc_id = f"catalog-import-rev{source_revision}"
        title = f"Каталог регламентных операций (Ревизия {source_revision})"
        rev_str = f"rev-{source_revision}"

        chunks: list[Chunk] = []
        for i, row in enumerate(rows):
            code = PromptInjectionDefense.sanitize_untrusted_text(str(row.get("code") or row.get("operation_code") or f"OP-{i+1}"))
            op_title = PromptInjectionDefense.sanitize_untrusted_text(str(row.get("title") or row.get("name") or "Регламентная операция"))
            eq_type = PromptInjectionDefense.sanitize_untrusted_text(str(row.get("equipment_type") or row.get("equipment_class") or ""))
            norm = PromptInjectionDefense.sanitize_untrusted_text(str(row.get("norm_hours") or row.get("norm_value") or ""))
            desc = PromptInjectionDefense.sanitize_untrusted_text(str(row.get("instructions") or row.get("description") or ""))

            content = (
                f"Операция {code}: {op_title}\n"
                f"Оборудование: {eq_type}\n"
                f"Норматив времени: {norm} чел.-ч\n"
                f"Инструкции: {desc}"
            )
            chunk_idx = i + 1
            chunk_id = f"{doc_id}:{rev_str}#{code.lower()}#{chunk_idx}"
            source_ref = f"source_catalog:rev{source_revision}:{code}"
            chunk_sha = compute_content_sha256(content)
            breadcrumb = f"{title} > Операция {code}: {op_title}"

            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    document_title=title,
                    source_revision=rev_str,
                    section_title=f"Операция {code}: {op_title}",
                    section_path=breadcrumb,
                    chunk_index=chunk_idx,
                    content=content,
                    clean_text=normalize_search_text(f"{breadcrumb} {eq_type} {desc}"),
                    equipment_class=eq_type if eq_type else None,
                    site_acl=[site_id] if site_id else [],
                    role_acl=["chief_engineer", "executor"],
                    source_ref=source_ref,
                    sha256=chunk_sha,
                    is_stale=False,
                )
            )

        metadata = DocumentMetadata(
            document_id=doc_id,
            title=title,
            source_revision=rev_str,
            source_sha256=catalog_sha256,
            equipment_class=None,
            site_acl=[site_id] if site_id else [],
            role_acl=["chief_engineer", "executor"],
            file_path=None,
            status="active",
        )

        return metadata, chunks
