"""Пакет подсистемы RAG и нормативно-справочной базы."""
from app.rag.schemas import NormSourceDTO, RateItem, NormativeChunkDTO
from app.rag.catalog import RatesCatalog
from app.rag.lexical_search import BM25SearchEngine
from app.rag.vector_search import VectorSearchEngine
from app.rag.applicability import ApplicabilityValidator, ApplicabilityResult
from app.rag.hybrid import HybridRAGSearchEngine, CandidateRateResult
from app.rag.chunker import NormativeChunker, ParsedChunk, ParsedDocument
from app.rag.embeddings import (
    BaseEmbeddingsProvider,
    MockEmbeddingsProvider,
    GigaChatEmbeddingsProvider,
)
from app.rag.ingestion import (
    NormativeIngestionPipeline,
    IngestionStats,
    IngestionReport,
)

__all__ = [
    "NormSourceDTO",
    "RateItem",
    "NormativeChunkDTO",
    "RatesCatalog",
    "BM25SearchEngine",
    "VectorSearchEngine",
    "ApplicabilityValidator",
    "ApplicabilityResult",
    "HybridRAGSearchEngine",
    "CandidateRateResult",
    "NormativeChunker",
    "ParsedChunk",
    "ParsedDocument",
    "BaseEmbeddingsProvider",
    "MockEmbeddingsProvider",
    "GigaChatEmbeddingsProvider",
    "NormativeIngestionPipeline",
    "IngestionStats",
    "IngestionReport",
]
