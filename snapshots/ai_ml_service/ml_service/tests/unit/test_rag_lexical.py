"""Unit-тесты лексического поиска Okapi BM25 по каталогу расценок."""
from pathlib import Path
import pytest
from app.rag.catalog import RatesCatalog
from app.rag.lexical_search import BM25SearchEngine, tokenize


@pytest.fixture
def search_engine():
    catalog_path = Path(__file__).resolve().parent.parent.parent / "data" / "demo_rates.json"
    catalog = RatesCatalog.from_json_file(catalog_path)
    return BM25SearchEngine(catalog.list_all())


def test_tokenize_russian():
    tokens = tokenize("Заделка глубоких трещин на кирпичном фасаде")
    assert "заделк" in tokens or "заделка" in tokens
    assert "трещин" in tokens
    assert "фасад" in tokens


def test_search_facade_crack(search_engine):
    results = search_engine.search("трещина на фасаде здания", top_k=3)
    assert len(results) > 0
    top_rate, score = results[0]
    assert top_rate.rate_code == "DEMO-FACADE-CRACK-01"
    assert score > 0.0


def test_search_tile_chip(search_engine):
    results = search_engine.search("откололся угол плитки на крыльце", top_k=3)
    assert len(results) > 0
    top_rate, score = results[0]
    assert top_rate.rate_code == "DEMO-TILE-CHIP-01"


def test_search_parking_leak(search_engine):
    results = search_engine.search("протечка воды в подземном паркинге", top_k=3)
    assert len(results) > 0
    top_rate, score = results[0]
    assert top_rate.rate_code == "DEMO-PARKING-LEAK-01"


def test_search_empty_query(search_engine):
    assert search_engine.search("") == []
    assert search_engine.search("   ") == []
