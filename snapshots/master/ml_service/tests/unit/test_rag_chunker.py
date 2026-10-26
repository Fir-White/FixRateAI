"""Unit-тесты для семантического чанкера строительных нормативов (NormativeChunker)."""
import re
from pathlib import Path
import pytest

from app.rag.chunker import NormativeChunker, ParsedChunk, ParsedDocument


@pytest.fixture
def chunker() -> NormativeChunker:
    return NormativeChunker()


@pytest.fixture
def sample_markdown() -> str:
    return """# СП 71.13330.2017 Изоляционные и отделочные покрытия
**Редакция:** 2017 с Изменениями
**Идентификатор источника:** d0000000-0000-4000-8000-000000000001
**Связанный шифр расценки:** DEMO-FACADE-CRACK-01
**Применимые дефекты:** facade_crack, crack

---

### Пункт 7.2.1. Подготовка основания при ремонте штукатурки
Поверхности очищаются от пыли, грязи и отслаивающихся слоев старой штукатурки.

### Пункт 7.2.2. Технология разделки и заделки трещин
Трещины подлежат механической расшивке по всей длине с V-образной разделкой кромок.
"""


def test_chunker_parse_markdown_text(chunker: NormativeChunker, sample_markdown: str):
    doc = chunker.parse_markdown_text(sample_markdown)

    assert doc.title == "СП 71.13330.2017 Изоляционные и отделочные покрытия"
    assert doc.edition == "2017 с Изменениями"
    assert doc.source_id == "d0000000-0000-4000-8000-000000000001"
    assert doc.rate_code == "DEMO-FACADE-CRACK-01"
    assert "facade_crack" in doc.applicable_defects
    assert len(doc.chunks) == 2


def test_chunker_sha256_hash_validity(chunker: NormativeChunker, sample_markdown: str):
    doc = chunker.parse_markdown_text(sample_markdown)
    pattern = re.compile(r"^[0-9a-f]{64}$")

    for chunk in doc.chunks:
        assert len(chunk.content_hash) == 64
        assert pattern.match(chunk.content_hash)
        expected_hash = chunker.compute_content_hash(chunk.content)
        assert chunk.content_hash == expected_hash


def test_chunker_locator_and_metadata(chunker: NormativeChunker, sample_markdown: str):
    doc = chunker.parse_markdown_text(sample_markdown)

    chunk_1 = doc.chunks[0]
    assert chunk_1.chunk_index == 0
    assert chunk_1.source_locator["clause"] == "7.2.1"
    assert "Подготовка основания" in chunk_1.source_locator["title"]
    assert chunk_1.rate_code == "DEMO-FACADE-CRACK-01"
    assert chunk_1.metadata["applicable_defects"] == ["facade_crack", "crack"]
    assert chunk_1.metadata["hazard_level"] == "normal"


def test_chunker_structural_hazard_detection(chunker: NormativeChunker):
    hazard_text = """# ГОСТ 31937-2011 Обследование зданий
---
### Пункт 5.3.3. Признаки аварийности
К признакам аварийного состояния относятся: сквозные трещины наружных стен с раскрытием 2.0 мм и более.
"""
    doc = chunker.parse_markdown_text(hazard_text)
    assert len(doc.chunks) == 1
    chunk = doc.chunks[0]
    assert chunk.metadata["hazard_level"] == "structural_hazard"


def test_chunker_parse_file_not_found(chunker: NormativeChunker):
    with pytest.raises(FileNotFoundError):
        chunker.parse_markdown_file("non_existent_normative_file_12345.md")


def test_chunker_parse_all_real_data_files(chunker: NormativeChunker):
    normatives_dir = Path(__file__).resolve().parent.parent.parent / "data" / "normatives"
    files = list(normatives_dir.glob("*.md"))
    assert len(files) >= 4, f"Ожидалось не менее 4 нормативных документов, найдено {len(files)}"

    total_chunks = 0
    for f in files:
        doc = chunker.parse_markdown_file(f)
        assert len(doc.title) > 5
        assert len(doc.chunks) >= 2
        total_chunks += len(doc.chunks)

    assert total_chunks >= 16
