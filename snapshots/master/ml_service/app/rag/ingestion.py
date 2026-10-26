"""Ingestion Pipeline для загрузки и индексации строительных нормативов в PostgreSQL (pgvector).

Обеспечивает:
1. Семантический парсинг файлов СП и ГОСТ через NormativeChunker.
2. Векторизацию чанков через BaseEmbeddingsProvider (1024d модель Embeddings).
3. Идемпотентную запись в таблицу normative_chunks с проверкой SHA-256 хэшей.
4. Разрешение связей с расценками (rate_id) и источниками (source_id).
5. Экспорт в автономный SQL seed-файл для миграций и CI без доступа к внешним сервисам.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.rag.chunker import NormativeChunker, ParsedChunk, ParsedDocument
from app.rag.embeddings import BaseEmbeddingsProvider, MockEmbeddingsProvider

logger = logging.getLogger("fixrate.rag.ingestion")


class IngestionStats(BaseModel):
    """Статистика индексации отдельного документа."""

    document_title: str
    source_id: str
    total_chunks: int = 0
    inserted_chunks: int = 0
    updated_chunks: int = 0
    skipped_chunks: int = 0


class IngestionReport(BaseModel):
    """Итоговый отчет о результатах индексации корпуса документов."""

    total_documents: int = 0
    total_chunks: int = 0
    inserted_chunks: int = 0
    updated_chunks: int = 0
    skipped_chunks: int = 0
    documents: list[IngestionStats] = Field(default_factory=list)


class NormativeIngestionPipeline:
    """Конвейер загрузки, векторизации и индексации нормативов в pgvector."""

    def __init__(
        self,
        chunker: Optional[NormativeChunker] = None,
        embeddings_provider: Optional[BaseEmbeddingsProvider] = None,
        db_url: Optional[str] = None,
    ):
        settings = get_settings()
        self.chunker = chunker or NormativeChunker()
        self.embeddings = embeddings_provider or MockEmbeddingsProvider()
        self.db_url = db_url or settings.database_url or "postgresql://fixrate:ChangeMe-local-only@localhost:5432/fixrate"

    def _get_connection(self):
        """Создает psycopg соединение с регистрацией типа pgvector."""
        import psycopg
        from pgvector.psycopg import register_vector

        conn = psycopg.connect(self.db_url)
        register_vector(conn)
        return conn

    def resolve_rate_id(self, conn, rate_code: Optional[str], source_id: str) -> Optional[UUID]:
        """Находит rate_id по коду расценки и source_id с соблюдением внешнего ключа."""
        if not rate_code:
            return None
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rate_id FROM rates WHERE rate_code = %s AND source_id = %s",
                (rate_code, source_id),
            )
            row = cur.fetchone()
            if row:
                return row[0]
        return None

    def ensure_norm_source_exists(self, conn, doc: ParsedDocument) -> None:
        """Проверяет наличие записи в norm_sources; при отсутствии создает DEMO-источник."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_id FROM norm_sources WHERE source_id = %s",
                (doc.source_id,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO norm_sources (
                        source_id, source_type, title, edition, document_reference, is_verified
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id) DO NOTHING
                    """,
                    (
                        doc.source_id,
                        "DEMO",
                        doc.title,
                        doc.edition,
                        doc.document_reference or "Официальный строительный регламент РФ",
                        False,
                    ),
                )
                conn.commit()

    def ingest_document(
        self,
        doc: ParsedDocument,
        conn=None,
        dry_run: bool = False,
        start_chunk_index: Optional[int] = None,
    ) -> IngestionStats:
        """Векторизует и сохраняет чанки одного нормативного документа в базу."""
        stats = IngestionStats(
            document_title=doc.title,
            source_id=doc.source_id,
            total_chunks=len(doc.chunks),
        )

        if not doc.chunks:
            return stats

        # 1. Генерируем векторные эмбеддинги для всех чанков документа
        texts = [chunk.content for chunk in doc.chunks]
        embeddings = self.embeddings.embed_documents(texts)

        if dry_run or conn is None:
            stats.inserted_chunks = len(doc.chunks)
            return stats

        from psycopg.types.json import Jsonb

        self.ensure_norm_source_exists(conn, doc)
        rate_id = self.resolve_rate_id(conn, doc.rate_code, doc.source_id)

        with conn.cursor() as cur:
            # Определяем текущий максимальный chunk_index для данного source_id
            if start_chunk_index is not None:
                current_next_idx = start_chunk_index
            else:
                cur.execute(
                    "SELECT COALESCE(MAX(chunk_index), -1) + 1 FROM normative_chunks WHERE source_id = %s",
                    (doc.source_id,),
                )
                current_next_idx = cur.fetchone()[0]

            for idx, chunk in enumerate(doc.chunks):
                emb = embeddings[idx]

                # Проверяем, существует ли уже чанк с таким хэшем для данного source_id
                cur.execute(
                    """
                    SELECT chunk_index, content_hash FROM normative_chunks
                    WHERE source_id = %s AND content_hash = %s
                    """,
                    (doc.source_id, chunk.content_hash),
                )
                existing = cur.fetchone()

                if existing is not None:
                    # Чанк уже существует с таким же хэшем
                    target_chunk_index = existing[0]
                else:
                    target_chunk_index = current_next_idx
                    current_next_idx += 1

                cur.execute(
                    """
                    INSERT INTO normative_chunks (
                        source_id, rate_id, chunk_index, content, embedding,
                        embedding_model, source_locator, metadata, content_hash
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (source_id, chunk_index) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        embedding_model = EXCLUDED.embedding_model,
                        source_locator = EXCLUDED.source_locator,
                        metadata = EXCLUDED.metadata,
                        content_hash = EXCLUDED.content_hash,
                        rate_id = EXCLUDED.rate_id
                    RETURNING (xmax = 0) AS is_insert;
                    """,
                    (
                        doc.source_id,
                        rate_id,
                        target_chunk_index,
                        chunk.content,
                        emb,
                        self.embeddings.model_name,
                        Jsonb(chunk.source_locator),
                        Jsonb(chunk.metadata),
                        chunk.content_hash,
                    ),
                )
                res = cur.fetchone()
                is_insert = res[0] if res else True

                if is_insert:
                    stats.inserted_chunks += 1
                elif existing and existing[1] == chunk.content_hash:
                    stats.skipped_chunks += 1
                else:
                    stats.updated_chunks += 1

            conn.commit()

        return stats

    def ingest_directory(
        self,
        dir_path: Path | str,
        dry_run: bool = False,
    ) -> IngestionReport:
        """Парсит и индексирует все markdown-файлы нормативов из указанной директории."""
        path = Path(dir_path)
        if not path.is_dir():
            raise NotADirectoryError(f"Каталог нормативов не найден: {path}")

        files = sorted(list(path.glob("*.md")) + list(path.glob("*.txt")))
        report = IngestionReport(total_documents=len(files))

        conn = None if dry_run else self._get_connection()
        try:
            # Если перезаписываем чистый seed в тестовой базе, сначала определяем начальный chunk_index
            source_counters: dict[str, int] = {}
            if conn is not None:
                # Очищаем демонстрационные чанки перед полной переиндексацией директории
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM normative_chunks WHERE source_id = 'd0000000-0000-4000-8000-000000000001'")
                    conn.commit()

            for file_path in files:
                doc = self.chunker.parse_markdown_file(file_path)
                current_start = source_counters.get(doc.source_id, 0)
                stats = self.ingest_document(
                    doc, conn=conn, dry_run=dry_run, start_chunk_index=current_start
                )
                source_counters[doc.source_id] = current_start + len(doc.chunks)

                report.total_chunks += stats.total_chunks
                report.inserted_chunks += stats.inserted_chunks
                report.updated_chunks += stats.updated_chunks
                report.skipped_chunks += stats.skipped_chunks
                report.documents.append(stats)
        finally:
            if conn is not None:
                conn.close()

        return report

    def export_sql_seed(
        self,
        dir_path: Path | str,
        output_file: Path | str,
    ) -> int:
        """Генерирует готовый идемпотентный SQL-скрипт с INSERT-запросами всех чанков."""
        path = Path(dir_path)
        files = sorted(list(path.glob("*.md")) + list(path.glob("*.txt")))
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        total_chunks = 0
        sql_lines = [
            "-- FixRate AI · Normative Chunks Seed",
            "-- Auto-generated by NormativeIngestionPipeline",
            "BEGIN;",
            "",
            "-- Очистка старых демонстрационных чанков перед сидированием",
            "DELETE FROM normative_chunks WHERE source_id = 'd0000000-0000-4000-8000-000000000001';",
            "",
        ]

        source_chunk_counters: dict[str, int] = {}

        for file_path in files:
            doc = self.chunker.parse_markdown_file(file_path)
            if not doc.chunks:
                continue

            texts = [c.content for c in doc.chunks]
            embeddings = self.embeddings.embed_documents(texts)
            base_idx = source_chunk_counters.get(doc.source_id, 0)

            sql_lines.append(f"-- Document: {doc.title}")
            for idx, chunk in enumerate(doc.chunks):
                assigned_chunk_idx = base_idx + idx
                emb = embeddings[idx]
                emb_str = f"[{','.join(f'{x:.6f}' for x in emb)}]"
                content_escaped = chunk.content.replace("'", "''")
                locator_json = json.dumps(chunk.source_locator, ensure_ascii=False).replace("'", "''")
                meta_json = json.dumps(chunk.metadata, ensure_ascii=False).replace("'", "''")

                rate_subquery = "NULL"
                if doc.rate_code:
                    rate_subquery = f"(SELECT rate_id FROM rates WHERE rate_code = '{doc.rate_code}' AND source_id = '{doc.source_id}')"

                sql_lines.append(
                    f"INSERT INTO normative_chunks ("
                    f"source_id, rate_id, chunk_index, content, embedding, embedding_model, "
                    f"source_locator, metadata, content_hash"
                    f") VALUES ("
                    f"'{doc.source_id}', {rate_subquery}, {assigned_chunk_idx}, '{content_escaped}', "
                    f"'{emb_str}'::vector, '{self.embeddings.model_name}', "
                    f"'{locator_json}'::jsonb, '{meta_json}'::jsonb, '{chunk.content_hash}'"
                    f") ON CONFLICT (source_id, chunk_index) DO UPDATE SET "
                    f"content = EXCLUDED.content, embedding = EXCLUDED.embedding, "
                    f"source_locator = EXCLUDED.source_locator, metadata = EXCLUDED.metadata, "
                    f"content_hash = EXCLUDED.content_hash, rate_id = EXCLUDED.rate_id;"
                )
                total_chunks += 1

            source_chunk_counters[doc.source_id] = base_idx + len(doc.chunks)
            sql_lines.append("")

        sql_lines.append("COMMIT;")
        sql_lines.append("")
        out_path.write_text("\n".join(sql_lines), encoding="utf-8")
        return total_chunks
