"""Модуль семантического векторного поиска по эмбеддингам."""
import hashlib
import math
from typing import Sequence
from app.rag.schemas import RateItem


def compute_deterministic_text_embedding(text: str, dims: int = 64) -> list[float]:
    """Генерирует детерминированный нормализованный вектор для тестов и локального запуска.
    
    Не требует загрузки тяжёлых моделей (SentenceTransformers/PyTorch),
    но обеспечивает косинусное сходство схожих текстовых токенов.
    """
    words = text.lower().split()
    vec = [0.0] * dims
    for w in words:
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
        for i in range(dims):
            bit = (h >> (i % 32)) & 1
            vec[i] += 1.0 if bit else -0.5

    # L2-нормализация
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        vec = [x / norm for x in vec]
    return vec


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Вычисляет косинусное сходство двух нормализованных векторов."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


class VectorSearchEngine:
    """Векторный поисковый движок по каталогу расценок."""

    def __init__(self, rates: Sequence[RateItem], dims: int = 64) -> None:
        self.rates = list(rates)
        self.dims = dims
        self.embeddings: list[list[float]] = []

        # Построение индексных векторов документов
        for r in self.rates:
            doc_text = f"{r.work_name} {r.description} {' '.join(r.keywords)}"
            emb = compute_deterministic_text_embedding(doc_text, dims=self.dims)
            self.embeddings.append(emb)

    def search(self, query: str, top_k: int = 5) -> list[tuple[RateItem, float]]:
        """Ищет расценки по семантическому сходству вектора запроса."""
        if not query.strip() or not self.rates:
            return []

        q_vec = compute_deterministic_text_embedding(query, dims=self.dims)
        scored: list[tuple[RateItem, float]] = []

        for idx, r in enumerate(self.rates):
            doc_vec = self.embeddings[idx]
            sim = cosine_similarity(q_vec, doc_vec)
            scored.append((r, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
