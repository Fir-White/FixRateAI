"""Unit-тесты векторного и гибридного поиска (Hybrid RAG) и применимости."""
from pathlib import Path
import pytest
from app.rag.catalog import RatesCatalog
from app.rag.hybrid import HybridRAGSearchEngine
from app.rag.vector_search import VectorSearchEngine, compute_deterministic_text_embedding, cosine_similarity
from app.rag.applicability import ApplicabilityValidator


@pytest.fixture
def catalog():
    path = Path(__file__).resolve().parent.parent.parent / "data" / "demo_rates.json"
    return RatesCatalog.from_json_file(path)


def test_deterministic_embedding_similarity():
    v1 = compute_deterministic_text_embedding("заделка трещин фасада")
    v2 = compute_deterministic_text_embedding("ремонт трещины на наружной стене")
    v3 = compute_deterministic_text_embedding("замена керамической плитки")

    sim_related = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert -1.0 <= sim_related <= 1.0
    assert -1.0 <= sim_unrelated <= 1.0
    # Словоформы «трещин»/«трещины» нормализуются в один признак,
    # а тексты про разные дефекты не должны быть похожи.
    assert sim_related > sim_unrelated
    assert sim_unrelated < 0.05


def test_vector_search_engine(catalog):
    engine = VectorSearchEngine(catalog.list_all())
    results = engine.search("заделка трещин на фасаде", top_k=2)
    assert len(results) > 0
    top_rate, sim = results[0]
    assert top_rate.rate_code == "DEMO-FACADE-CRACK-01"


def test_vector_search_pilot_scenarios_top1(catalog):
    engine = VectorSearchEngine(catalog.list_all())
    scenarios = [
        ("заделка трещин на фасаде", "DEMO-FACADE-CRACK-01"),
        ("скололась плитка", "DEMO-TILE-CHIP-01"),
        ("протечка воды в подземном паркинге", "DEMO-PARKING-LEAK-01"),
    ]
    for query, expected_code in scenarios:
        results = engine.search(query, top_k=3)
        assert results, f"Нет кандидатов для запроса: {query}"
        assert results[0][0].rate_code == expected_code, query


def test_vector_search_filters_irrelevant_candidates(catalog):
    engine = VectorSearchEngine(catalog.list_all())
    assert engine.search("покраска забора", top_k=5) == []


def test_vector_search_min_similarity_override(catalog):
    engine = VectorSearchEngine(catalog.list_all(), min_similarity=0.0)
    results = engine.search("покраска забора", top_k=5)
    assert len(results) == len(catalog.list_all())


def test_hybrid_rag_search_pilot_scenarios(catalog):
    hybrid = HybridRAGSearchEngine(catalog.list_all())

    # Сценарий facade_crack
    candidates = hybrid.search(query="трещина на фасаде здания", defect_type="facade_crack", top_k=2)
    assert len(candidates) > 0
    top = candidates[0]
    assert top.rate.rate_code == "DEMO-FACADE-CRACK-01"
    assert top.applicability.is_applicable is True
    assert top.rrf_score > 0.0

    # Сценарий tile_chip
    candidates_tile = hybrid.search(query="скололась плитка", defect_type="tile_chip", top_k=2)
    assert len(candidates_tile) > 0
    assert candidates_tile[0].rate.rate_code == "DEMO-TILE-CHIP-01"
    assert candidates_tile[0].applicability.is_applicable is True

    # Сценарий parking_leak с предупреждением ручной проверки
    candidates_leak = hybrid.search(query="протечка гидроизоляции", defect_type="parking_leak", top_k=2)
    assert len(candidates_leak) > 0
    assert candidates_leak[0].rate.rate_code == "DEMO-PARKING-LEAK-01"
    assert candidates_leak[0].applicability.requires_review is True
    assert len(candidates_leak[0].applicability.warnings) > 0


def test_applicability_validator_rejection(catalog):
    rate = catalog.get_by_code("DEMO-FACADE-CRACK-01")
    # Проверяем несовместимость: расценка на трещину применяется к протечке парковки
    res = ApplicabilityValidator.validate_rate(rate, defect_type="parking_leak")
    assert res.is_applicable is False
    assert res.requires_review is True
    assert "предназначена для дефектов" in res.rejection_reason
