"""Провайдеры векторных эмбеддингов для RAG-подсистемы FixRate AI.

Поддерживает:
1. GigaChatEmbeddingsProvider — боевые 1024-мерные эмбеддинги Сбера (модель Embeddings).
2. MockEmbeddingsProvider — детерминированный оффлайн-генератор векторов размерности 1024
   для герметичного тестирования и локальной разработки без платных API.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Optional, Protocol

from app.core.config import get_settings
from app.rag.lexical_search import tokenize

logger = logging.getLogger("fixrate.rag.embeddings")


class BaseEmbeddingsProvider(Protocol):
    """Интерфейс провайдера векторных эмбеддингов."""

    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Генерирует векторы для списка документов."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Генерирует вектор для поискового запроса."""
        ...

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Асинхронная генерация векторов для списка документов."""
        ...

    async def aembed_query(self, text: str) -> list[float]:
        """Асинхронная генерация вектора для поискового запроса."""
        ...


class MockEmbeddingsProvider:
    """Детерминированный офлайн-генератор 1024-мерных L2-нормализованных векторов.

    Обеспечивает строгое воспроизведение косинусного сходства для текстов
    с пересекающейся терминологией без вызова внешних сетевых сервисов.
    """

    def __init__(self, dimension: int = 1024, model_name: str = "mock-embeddings-1024"):
        self.dimension = dimension
        self.model_name = model_name

    def _embed_single(self, text: str) -> list[float]:
        tokens = tokenize(text)
        vec = [0.0] * self.dimension

        if not tokens:
            vec[0] = 1.0
            return vec

        for token in tokens:
            # 1. Хешируем сам стеммированный токен
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            vec[idx] += 1.0

            # 2. Хешируем символьные 3-граммы для улавливания морфологической близости
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    trigram = token[i : i + 3]
                    th = int(hashlib.md5(trigram.encode("utf-8")).hexdigest(), 16)
                    tidx = th % self.dimension
                    vec[tidx] += 0.3

        # L2-нормализация вектора
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-12:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0

        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_single(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


class GigaChatEmbeddingsProvider:
    """Боевой провайдер эмбеддингов через официальный SDK GigaChat (Сбер).

    Модель 'Embeddings' возвращает плотные 1024-мерные векторы, оптимизированные
    для семантического поиска по русскоязычной нормативной и деловой документации.
    """

    def __init__(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        model_name: str = "Embeddings",
        dimension: int = 1024,
        verify_ssl_certs: bool = False,
        fallback_to_mock: bool = True,
    ):
        settings = get_settings()
        self.credentials = credentials if credentials is not None else settings.gigachat_credentials
        self.scope = scope if scope is not None else settings.gigachat_scope
        self.model_name = model_name
        self.dimension = dimension
        self.verify_ssl_certs = verify_ssl_certs
        self.fallback_to_mock = fallback_to_mock
        self._mock_fallback = MockEmbeddingsProvider(dimension=dimension, model_name=f"fallback-{model_name}")

    def _get_client(self):
        if not self.credentials:
            return None
        try:
            from gigachat import GigaChat
            return GigaChat(
                credentials=self.credentials,
                scope=self.scope,
                verify_ssl_certs=self.verify_ssl_certs,
                model=self.model_name,
            )
        except Exception as e:
            logger.warning("Не удалось инициализировать клиент GigaChat: %s", e)
            return None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        client = self._get_client()
        if client is None:
            if self.fallback_to_mock:
                logger.debug("GigaChat credentials отсутствуют, используется MockEmbeddingsProvider")
                return self._mock_fallback.embed_documents(texts)
            raise RuntimeError("GigaChat credentials не заданы и fallback_to_mock=False")

        try:
            batch_size = 32
            results: list[list[float]] = []
            with client as giga:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    res = giga.embeddings(texts=batch, model=self.model_name)
                    for item in res.data:
                        results.append(item.embedding)
            return results
        except Exception as e:
            logger.warning("Ошибка при вызове GigaChat.embeddings: %s", e)
            if self.fallback_to_mock:
                logger.info("Выполняется безопасный переход на MockEmbeddingsProvider")
                return self._mock_fallback.embed_documents(texts)
            raise

    def embed_query(self, text: str) -> list[float]:
        res = self.embed_documents([text])
        return res[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        client = self._get_client()
        if client is None:
            if self.fallback_to_mock:
                return self._mock_fallback.embed_documents(texts)
            raise RuntimeError("GigaChat credentials не заданы и fallback_to_mock=False")

        try:
            batch_size = 32
            results: list[list[float]] = []
            async with client as giga:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    res = await giga.aembeddings(texts=batch, model=self.model_name)
                    for item in res.data:
                        results.append(item.embedding)
            return results
        except Exception as e:
            logger.warning("Ошибка при вызове GigaChat.aembeddings: %s", e)
            if self.fallback_to_mock:
                return self._mock_fallback.embed_documents(texts)
            raise

    async def aembed_query(self, text: str) -> list[float]:
        res = await self.aembed_documents([text])
        return res[0]
