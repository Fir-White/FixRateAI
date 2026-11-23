"""Retrieval index with Russian lexical stemming, bidirectional synonyms, and strict CR-17 ACL filters."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

from .extractor import normalize_search_text
from .guardrails import AntiHallucinationGuardrail, PromptInjectionDefense
from .schemas import Chunk, Citation, DocumentMetadata, RetrievalQuery, RetrievalResult


RUSSIAN_SYNONYMS: dict[str, list[str]] = {
    "грязевик": ["сетчатый", "фильтр", "сетка", "фсф", "чистка", "промывка"],
    "фильтр": ["сетчатый", "грязевик", "сетка", "фсф", "чистка", "промывка", "крышка"],
    "давление": ["бар", "манометр", "напор", "номинал", "шкала", "контур"],
    "манометр": ["давление", "бар", "напор", "номинал", "шкала", "стрелка", "прибор"],
    "показания": ["вкт-7", "счетчик", "вычислитель", "тепловая", "гкал", "протокол"],
    "опрессовка": ["гидравлические", "испытания", "коллектор", "гребенка", "выдержка"],
    "коллектор": ["опрессовка", "гребенка", "гидравлические", "испытания"],
    "шкаф": ["шау", "автоматизация", "щит", "индикация", "сеть"],
    "норма": ["номинал", "предел", "рабочий", "диапазон", "допустимый"],
    "чистка": ["промывка", "разборка", "очистка", "сборка", "шлам", "фильтр", "грязевик"],
    "очистка": ["чистка", "промывка", "разборка", "фильтр", "грязевик", "сетка", "крышка"],
}


def stem_russian_word(word: str) -> str:
    """Lightweight Russian stemmer stripping standard inflectional endings."""
    w = word.lower().strip()
    if len(w) <= 3:
        return w
    # Common Russian suffixes / endings
    for suffix in [
        "ому", "ему", "ыми", "ями", "ого", "его", "ых", "их", "ая", "яя", "ое", "ее",
        "ам", "ям", "ом", "ем", "ах", "ях", "ов", "ев", "ей", "ий", "ый", "ой", "ать",
        "ить", "еть", "ами", "ями", "ка", "ки", "ку", "ке", "ом", "ам", "а", "е", "и",
        "о", "у", "ы", "ь", "я"
    ]:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


# Precompute bidirectional synonym graph
EXPANDED_SYNONYMS: dict[str, set[str]] = defaultdict(set)
for _k, _syns in RUSSIAN_SYNONYMS.items():
    _k_stem = stem_russian_word(_k)
    EXPANDED_SYNONYMS[_k_stem].add(_k_stem)
    for _s in _syns:
        _s_stem = stem_russian_word(_s)
        EXPANDED_SYNONYMS[_k_stem].add(_s_stem)
        EXPANDED_SYNONYMS[_s_stem].add(_k_stem)
        EXPANDED_SYNONYMS[_s_stem].add(_s_stem)
        for _s2 in _syns:
            EXPANDED_SYNONYMS[_s_stem].add(stem_russian_word(_s2))


class RAGIndex:
    """In-memory and full-text index managing verifiable chunks under strict ACL."""

    def __init__(self) -> None:
        self.documents: dict[str, DocumentMetadata] = {}
        self.chunks: dict[str, Chunk] = {}
        # Document ID -> list of chunk IDs
        self.doc_to_chunks: dict[str, list[str]] = defaultdict(list)
        # Equipment class -> list of chunk IDs
        self.eq_to_chunks: dict[str, list[str]] = defaultdict(list)
        # Document ID -> latest active revision string
        self.latest_revisions: dict[str, str] = {}
        # History: (doc_id, revision) -> list of chunk IDs
        self.archived_revisions: dict[tuple[str, str], list[str]] = defaultdict(list)

    def add_document(self, metadata: DocumentMetadata, chunks: list[Chunk]) -> None:
        """Indexes or updates a document and its chunks, archiving previous revisions if updated."""
        doc_id = metadata.document_id
        new_rev = metadata.source_revision

        # If previous revision exists and is different -> archive old chunks
        old_meta = self.documents.get(doc_id)
        if old_meta and old_meta.source_revision != new_rev:
            old_rev = old_meta.source_revision
            old_chunk_ids = self.doc_to_chunks.get(doc_id, [])
            for cid in old_chunk_ids:
                old_chunk = self.chunks.get(cid)
                if old_chunk:
                    stale_chunk = old_chunk.model_copy(update={"is_stale": True})
                    self.chunks[cid] = stale_chunk
                    self.archived_revisions[(doc_id, old_rev)].append(cid)

            # Clear current active map for this doc
            self.doc_to_chunks[doc_id] = []

        self.documents[doc_id] = metadata
        self.latest_revisions[doc_id] = new_rev

        for chunk in chunks:
            self.chunks[chunk.chunk_id] = chunk
            self.doc_to_chunks[doc_id].append(chunk.chunk_id)
            if chunk.equipment_class:
                self.eq_to_chunks[chunk.equipment_class].append(chunk.chunk_id)

    def revoke_document(self, doc_id: str, reason: str = "Регламент отозван") -> bool:
        """Marks document and its chunks as stale / archived."""
        if doc_id not in self.documents:
            return False

        meta = self.documents[doc_id]
        updated_meta = meta.model_copy(update={"is_stale": True, "is_archived": True, "status": "stale"})
        self.documents[doc_id] = updated_meta

        for cid in self.doc_to_chunks.get(doc_id, []):
            chunk = self.chunks.get(cid)
            if chunk:
                self.chunks[cid] = chunk.model_copy(update={"is_stale": True})
        return True

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """Executes full-text / lexical retrieval with synonym expansions, ACL checks, and anti-hallucination."""
        # 1. Prompt Injection Defense on input
        is_safe, safety_err = PromptInjectionDefense.check_query_safety(query.query)
        if not is_safe:
            return RetrievalResult(
                status="ACCESS_DENIED",
                query=query.query,
                citations=[],
                context_text=f"ОШИБКА БЕЗОПАСНОСТИ: {safety_err}",
                error_code="UNAUTHORIZED_CAPABILITY_ESCALATION",
                limitations=["Входные данные содержат недопустимые императивные команды."],
                is_hallucination_blocked=True,
            )

        # 2. Strict Cross-Site ACL enforcement (RAG-NEG-02)
        site_pattern = re.findall(r"site-[a-z0-9\-]+", query.query.lower())
        for target_site in site_pattern:
            if query.site_id and target_site != query.site_id.lower():
                return AntiHallucinationGuardrail.evaluate(
                    query,
                    [],
                    is_acl_denied=True,
                    denied_reason=(
                        f"Запрос содержит указание на чужой объект '{target_site}', в то время как активный "
                        f"контекст сессии: '{query.site_id}'. Межобъектный доступ запрещён (CR-17 / TL04)."
                    ),
                )

        # 3. Detect stale/outdated revision request (RAG-NEG-03)
        stale_request_detected = False
        stale_rev_name = query.requested_revision
        if query.requested_revision:
            stale_request_detected = True
        elif re.search(r"редакци[иея]\s+202[0-5]|старо[йму]\s+регламент|прошлогодн", query.query.lower()):
            stale_request_detected = True
            m_rev = re.search(r"rev-202[0-5]\d{4}-\d+", query.query)
            if m_rev:
                stale_rev_name = m_rev.group(0)

        # 4. Tokenize and expand query with bidirectional synonyms
        q_norm = normalize_search_text(query.query)
        q_tokens = [w for w in q_norm.split() if len(w) >= 2]
        if not q_tokens:
            return AntiHallucinationGuardrail.evaluate(query, [])

        core_q_stems = {stem_russian_word(w) for w in q_tokens}
        all_q_stems: set[str] = set(core_q_stems)
        for st in core_q_stems:
            syn_stems = EXPANDED_SYNONYMS.get(st, set())
            all_q_stems.update(syn_stems)

        # 5. Score candidate chunks and track ACL denials
        candidates: list[tuple[float, Chunk, str | None]] = []
        is_acl_denied = False
        denied_reason = None
        max_denied_score = 0.0
        max_allowed_score = 0.0

        for cid, chunk in self.chunks.items():
            # Equipment class filter if specified
            if query.equipment_class and chunk.equipment_class and chunk.equipment_class != query.equipment_class:
                continue

            # Token overlap check
            chunk_tokens = chunk.clean_text.split()
            chunk_stems = [stem_russian_word(w) for w in chunk_tokens]
            chunk_stem_set = set(chunk_stems)

            overlap = all_q_stems.intersection(chunk_stem_set)
            if not overlap:
                continue

            # Scoring: TF with diminishing returns + overlap coverage
            tf = sum(chunk_stems.count(s) for s in overlap)
            base_score = (tf / (tf + 1.5)) * (len(overlap) / max(len(core_q_stems), 1))

            # Boosts
            sec_lower = chunk.section_title.lower()
            title_lower = chunk.document_title.lower()
            if any(s in sec_lower for s in all_q_stems):
                base_score *= 2.0
            if any(s in title_lower for s in all_q_stems):
                base_score *= 1.8
            if query.equipment_class and chunk.equipment_class == query.equipment_class:
                base_score *= 1.5
            if q_norm in chunk.clean_text:
                base_score *= 3.0

            # Role ACL check
            if query.user_role not in chunk.role_acl:
                if base_score > max_denied_score:
                    max_denied_score = base_score
                    is_acl_denied = True
                    denied_reason = (
                        f"Документ '{chunk.document_title}' предназначен исключительно для роли "
                        f"'{', '.join(chunk.role_acl)}'. Пользователь с ролью '{query.user_role}' не имеет допуска."
                    )
                continue

            # Site ACL check
            if chunk.site_acl and query.site_id:
                if query.site_id not in chunk.site_acl:
                    if base_score > max_denied_score:
                        max_denied_score = base_score
                        is_acl_denied = True
                        denied_reason = (
                            f"Документ '{chunk.document_title}' ограничен объектами: {', '.join(chunk.site_acl)}. "
                            f"Запрос от объекта '{query.site_id}' отклонён."
                        )
                    continue
            elif chunk.site_acl and not query.site_id:
                continue

            # Revision staleness check
            is_stale_chunk = chunk.is_stale
            stale_warning = None

            if stale_request_detected:
                latest_rev = self.latest_revisions.get(chunk.document_id, chunk.source_revision)
                if is_stale_chunk or (stale_rev_name and stale_rev_name != latest_rev) or (stale_rev_name is None):
                    stale_warning = (
                        f"Запрошена архивная/устаревшая редакция регламента ({stale_rev_name or 'предыдущих лет'}). "
                        f"В соответствии с регламентом CR-17 цитируется действующая редакция '{latest_rev}'. "
                        f"Предыдущие нормы утратили силу."
                    )
            else:
                if is_stale_chunk:
                    continue

            if base_score >= query.min_score:
                if base_score > max_allowed_score:
                    max_allowed_score = base_score
                candidates.append((base_score, chunk, stale_warning))

        # 6. ACL precedence: if primary matching document was denied by ACL, don't fall back to secondary generic chunks
        if is_acl_denied and (max_denied_score >= max_allowed_score or not candidates):
            return AntiHallucinationGuardrail.evaluate(
                query, [], is_acl_denied=True, denied_reason=denied_reason
            )

        # 7. Sort and select top_k citations
        candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = candidates[: query.top_k]

        citations: list[Citation] = []
        for score, chunk, warning in top_candidates:
            citations.append(
                Citation(
                    document_id=chunk.document_id,
                    document_title=chunk.document_title,
                    source_revision=chunk.source_revision,
                    section_title=chunk.section_title,
                    source_ref=chunk.source_ref,
                    snippet=chunk.content,
                    relevance_score=round(score, 4),
                    is_stale=chunk.is_stale or bool(warning),
                    warning=warning,
                )
            )

        return AntiHallucinationGuardrail.evaluate(query, citations)
