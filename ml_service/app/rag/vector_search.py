"""Модуль семантического векторного поиска по эмбеддингам."""
import hashlib
import math
from typing import Sequence
from app.rag.lexical_search import tokenize
from app.rag.schemas import RateItem

# Размерность хешированного пространства. Достаточно велика, чтобы коллизии
# между лексическими токенами пилотного каталога не искажали косинусное сходство.
DEFAULT_EMBEDDING_DIMS = 4096

# Минимальное косинусное сходство, ниже которого кандидат считается нерелевантным.
DEFAULT_MIN_SIMILARITY = 0.05


def compute_deterministic_text_embedding(
    text: str,
    dims: int = DEFAULT_EMBEDDING_DIMS,
) -> list[float]:
    """Генерирует детерминированный разреженный вектор по лексическим стемам.

    Не требует загрузки тяжёлых моделей (SentenceTransformers/PyTorch) и внешних
    сервисов эмбеддингов. Токены нормализуются тем же стеммером, что и BM25,
    поэтому словоформы («трещина»/«трещины») попадают в один признак.
    """
    if dims <= 0:
        raise ValueError("dims должен быть положительным")

    vec = [0.0] * dims
    for token in tokenize(text):
        index = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dims
        vec[index] += 1.0

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

    def __init__(
        self,
        rates: Sequence[RateItem],
        dims: int = DEFAULT_EMBEDDING_DIMS,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> None:
        if min_similarity < 0.0:
            raise ValueError("min_similarity не может быть отрицательным")

        self.rates = list(rates)
        self.dims = dims
        self.min_similarity = min_similarity
        self.embeddings: list[list[float]] = []

        # Построение индексных векторов документов
        for r in self.rates:
            doc_text = f"{r.work_name} {r.description} {' '.join(r.keywords)}"
            emb = compute_deterministic_text_embedding(doc_text, dims=self.dims)
            self.embeddings.append(emb)

    def search(self, query: str, top_k: int = 5) -> list[tuple[RateItem, float]]:
        """Ищет расценки по семантическому сходству вектора запроса.

        Кандидаты с косинусным сходством ниже ``min_similarity`` отбрасываются,
        чтобы нерелевантный запрос не возвращал весь каталог.
        """
        if not query.strip() or not self.rates:
            return []

        q_vec = compute_deterministic_text_embedding(query, dims=self.dims)
        scored: list[tuple[RateItem, float]] = []

        for idx, r in enumerate(self.rates):
            doc_vec = self.embeddings[idx]
            sim = cosine_similarity(q_vec, doc_vec)
            if sim >= self.min_similarity:
                scored.append((r, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
