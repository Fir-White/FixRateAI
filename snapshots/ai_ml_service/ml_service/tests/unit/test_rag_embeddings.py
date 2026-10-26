"""Unit-тесты для провайдеров векторных эмбеддингов (MockEmbeddingsProvider, GigaChatEmbeddingsProvider)."""
import math
import pytest

from app.rag.embeddings import MockEmbeddingsProvider, GigaChatEmbeddingsProvider


def test_mock_embeddings_dimension_and_norm():
    provider = MockEmbeddingsProvider(dimension=1024)
    vec = provider.embed_query("заделка трещин штукатурного фасада")

    assert len(vec) == 1024
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-5


def test_mock_embeddings_empty_string():
    provider = MockEmbeddingsProvider(dimension=1024)
    vec = provider.embed_query("")

    assert len(vec) == 1024
    assert vec[0] == 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-5


def test_mock_embeddings_semantic_similarity():
    provider = MockEmbeddingsProvider(dimension=1024)

    v_crack = provider.embed_query("трещина на оштукатуренном фасаде здания")
    v_repair = provider.embed_query("ремонт и расшивка фасадных трещин герметиком")
    v_tile = provider.embed_query("укладка керамической плитки на клей в ванной")

    sim_crack_repair = sum(a * b for a, b in zip(v_crack, v_repair))
    sim_crack_tile = sum(a * b for a, b in zip(v_crack, v_tile))

    assert sim_crack_repair > 0.2
    assert sim_crack_repair > sim_crack_tile


def test_mock_embeddings_batch_documents():
    provider = MockEmbeddingsProvider(dimension=1024)
    texts = ["первый документ", "второй документ", "третий документ"]
    matrix = provider.embed_documents(texts)

    assert len(matrix) == 3
    for v in matrix:
        assert len(v) == 1024


@pytest.mark.anyio
async def test_mock_embeddings_async_methods():
    provider = MockEmbeddingsProvider(dimension=1024)
    v = await provider.aembed_query("асинхронный тест")
    assert len(v) == 1024

    docs = await provider.aembed_documents(["док 1", "док 2"])
    assert len(docs) == 2
    assert len(docs[0]) == 1024


def test_gigachat_provider_fallback_to_mock_when_no_credentials():
    provider = GigaChatEmbeddingsProvider(
        credentials="",
        model_name="Embeddings",
        fallback_to_mock=True,
    )
    vec = provider.embed_query("запрос при отсутствии ключа")

    assert len(vec) == 1024
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-5


def test_gigachat_provider_raises_when_no_credentials_and_fallback_false():
    provider = GigaChatEmbeddingsProvider(
        credentials="",
        model_name="Embeddings",
        fallback_to_mock=False,
    )
    with pytest.raises(RuntimeError, match="GigaChat credentials не заданы"):
        provider.embed_query("запрос без ключа")
