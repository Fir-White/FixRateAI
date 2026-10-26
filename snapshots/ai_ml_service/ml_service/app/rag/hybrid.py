"""Гибридный поисковый движок (BM25 + Vector Search) с RRF-слиянием."""
from typing import Sequence
from app.rag.applicability import ApplicabilityValidator, ApplicabilityResult
from app.rag.lexical_search import BM25SearchEngine
from app.rag.schemas import RateItem
from app.rag.vector_search import VectorSearchEngine

RRF_K = 60.0


class CandidateRateResult:
    """Кандидат расценки с объединённым score и результатом применимости."""

    def __init__(
        self,
        rate: RateItem,
        rrf_score: float,
        lexical_rank: int | None,
        vector_rank: int | None,
        applicability: ApplicabilityResult,
    ) -> None:
        self.rate = rate
        self.rrf_score = rrf_score
        self.lexical_rank = lexical_rank
        self.vector_rank = vector_rank
        self.applicability = applicability


class HybridRAGSearchEngine:
    """Гибридный поисковый движок по нормативно-справочной базе."""

    def __init__(self, rates: Sequence[RateItem]) -> None:
        self.rates = list(rates)
        self.bm25_engine = BM25SearchEngine(self.rates)
        self.vector_engine = VectorSearchEngine(self.rates)
        self.validator = ApplicabilityValidator()

    def search(
        self,
        query: str,
        defect_type: str | None = None,
        top_k: int = 5,
    ) -> list[CandidateRateResult]:
        """Выполняет гибридный поиск (BM25 + Вектор) и проверяет применимость."""
        if not query.strip() and defect_type:
            query = defect_type

        # 1. Лексический поиск BM25
        lexical_results = self.bm25_engine.search(query, top_k=top_k * 2)
        # 2. Векторный семантический поиск
        vector_results = self.vector_engine.search(query, top_k=top_k * 2)

        # Карта рангов
        lexical_ranks = {r.rate_code: rank for rank, (r, _) in enumerate(lexical_results, start=1)}
        vector_ranks = {r.rate_code: rank for rank, (r, _) in enumerate(vector_results, start=1)}

        # Множество всех уникальных расценок
        rates_by_code: dict[str, RateItem] = {}
        for r, _ in lexical_results:
            rates_by_code[r.rate_code] = r
        for r, _ in vector_results:
            rates_by_code[r.rate_code] = r

        # Расчёт RRF (Reciprocal Rank Fusion)
        candidates: list[CandidateRateResult] = []
        for code, rate in rates_by_code.items():
            l_rank = lexical_ranks.get(code)
            v_rank = vector_ranks.get(code)

            score = 0.0
            if l_rank is not None:
                score += 1.0 / (RRF_K + l_rank)
            if v_rank is not None:
                score += 1.0 / (RRF_K + v_rank)

            # Проверка применимости
            if defect_type:
                appl = self.validator.validate_rate(rate, defect_type)
            else:
                appl = ApplicabilityResult(is_applicable=True, requires_review=False, rejection_reason=None, warnings=[])

            candidates.append(
                CandidateRateResult(
                    rate=rate,
                    rrf_score=score,
                    lexical_rank=l_rank,
                    vector_rank=v_rank,
                    applicability=appl,
                )
            )

        # Сортировка: сначала применимые, затем по убыванию RRF score
        candidates.sort(
            key=lambda c: (c.applicability.is_applicable, c.rrf_score),
            reverse=True,
        )
        return candidates[:top_k]
