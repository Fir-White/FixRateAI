"""Unit-тесты для Ingestion Pipeline нормативных документов (NormativeIngestionPipeline)."""
from pathlib import Path
import pytest

from app.rag.chunker import NormativeChunker, ParsedChunk, ParsedDocument
from app.rag.embeddings import MockEmbeddingsProvider
from app.rag.ingestion import NormativeIngestionPipeline, IngestionReport, IngestionStats


@pytest.fixture
def mock_pipeline() -> NormativeIngestionPipeline:
    return NormativeIngestionPipeline(
        chunker=NormativeChunker(),
        embeddings_provider=MockEmbeddingsProvider(dimension=1024),
    )


def test_ingestion_dry_run_document(mock_pipeline: NormativeIngestionPipeline):
    doc = ParsedDocument(
        title="СП 71.13330.2017",
        edition="2017",
        source_id="d0000000-0000-4000-8000-000000000001",
        chunks=[
            ParsedChunk(
                chunk_index=0,
                content="Текст первого чанка",
                content_hash=mock_pipeline.chunker.compute_content_hash("Текст первого чанка"),
                source_locator={"clause": "1.1"},
                metadata={},
            ),
            ParsedChunk(
                chunk_index=1,
                content="Текст второго чанка",
                content_hash=mock_pipeline.chunker.compute_content_hash("Текст второго чанка"),
                source_locator={"clause": "1.2"},
                metadata={},
            ),
        ],
    )

    stats = mock_pipeline.ingest_document(doc, dry_run=True)
    assert stats.total_chunks == 2
    assert stats.inserted_chunks == 2
    assert stats.updated_chunks == 0
    assert stats.skipped_chunks == 0


def test_ingestion_dry_run_directory(mock_pipeline: NormativeIngestionPipeline):
    normatives_dir = Path(__file__).resolve().parent.parent.parent / "data" / "normatives"
    report = mock_pipeline.ingest_directory(normatives_dir, dry_run=True)

    assert report.total_documents >= 4
    assert report.total_chunks >= 16
    assert report.inserted_chunks == report.total_chunks
    assert len(report.documents) == report.total_documents


def test_ingestion_directory_not_found(mock_pipeline: NormativeIngestionPipeline):
    with pytest.raises(NotADirectoryError):
        mock_pipeline.ingest_directory("non_existent_directory_99999")


def test_export_sql_seed_generation(mock_pipeline: NormativeIngestionPipeline, tmp_path: Path):
    normatives_dir = Path(__file__).resolve().parent.parent.parent / "data" / "normatives"
    sql_file = tmp_path / "test_seed_normative_chunks.sql"

    total_chunks = mock_pipeline.export_sql_seed(normatives_dir, sql_file)
    assert total_chunks >= 16
    assert sql_file.is_file()

    sql_content = sql_file.read_text(encoding="utf-8")
    assert "BEGIN;" in sql_content
    assert "COMMIT;" in sql_content
    assert "INSERT INTO normative_chunks" in sql_content
    assert "ON CONFLICT (source_id, chunk_index) DO UPDATE" in sql_content
    assert "'[0." in sql_content or "'[" in sql_content
    assert "d0000000-0000-4000-8000-000000000001" in sql_content
